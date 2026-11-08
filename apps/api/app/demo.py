"""Realistic demo company for local presentations (development only).

People are created directly (there is no user-creation API, the same as app.seed). Everything
else -- documents, files, folders, workflows, decisions, comments -- goes through the real HTTP
API as those people, so audit, notifications and access rules are exactly what a live system
would produce. One overdue task is back-dated and escalated to show escalation.

Run after the API is up:  python -m app.demo --api http://api:8000
Idempotent: a second run detects the demo company and does nothing.
"""

import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.auth import password_hasher
from app.config import settings
from app.db import SessionLocal
from app.models import Approval, AuditEvent, Department, Document, Notification, User
from app.workflow_escalation import escalate

PEOPLE = [
    # key, email, display name, role, department code
    ("aigerim", "aigerim.nurlanova@nexora.local", "Айгерим Нурланова", "USER", "FINANCE"),
    ("olga", "olga.kim@nexora.local", "Ольга Ким", "MANAGER", "FINANCE"),
    ("daniyar", "daniyar.seitkali@nexora.local", "Данияр Сейткали", "LEGAL", "LEGAL"),
    ("gulnara", "gulnara.abdrakhmanova@nexora.local", "Гульнара Абдрахманова", "MANAGER", "LEGAL"),
    ("erlan", "erlan.zhumabekov@nexora.local", "Ерлан Жумабеков", "APPROVER", "MANAGEMENT"),
    ("asel", "asel.tuleuova@nexora.local", "Асель Тулеуова", "USER", "HR"),
]


class DemoError(RuntimeError):
    pass


class Api:
    """Minimal browser-like client: session cookie, CSRF, Origin and signed retry keys."""

    def __init__(self, base: str, email: str, password: str):
        self.base = base.rstrip("/") + "/api/v1"
        self.origin = settings().web_origin
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""
        self.csrf = self.request("POST", "/auth/login", {"email": email, "password": password})["csrf_token"]

    def request(self, method: str, path: str, body: Any = None, *, files: dict | None = None,
                keyed: bool = False) -> Any:
        headers = {"Origin": self.origin, "X-CSRF-Token": self.csrf}
        if keyed:
            headers["Idempotency-Key"] = self.key()
        data = None
        if files is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for name, value in files.items():
                if isinstance(value, tuple):
                    filename, content = value
                    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                                 f'filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + content + b"\r\n")
                else:
                    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                                 f"{value}\r\n".encode())
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        call = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(call, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise DemoError(f"{method} {path} -> {error.code} {error.read()[:300]!r}") from None

    def key(self) -> str:
        return self.request("POST", "/operation-keys")["key"]

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body, keyed=True)


def wait_for(base: str) -> None:
    for _ in range(90):
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/api/v1/ready", timeout=5):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    raise DemoError("API did not become ready")


def ensure_people(password: str) -> bool:
    """Create the demo staff; return False when the demo company already has documents."""
    with SessionLocal.begin() as db:
        first = db.scalar(select(User).where(User.email == PEOPLE[0][1]))
        if first and db.scalar(select(Document.id).where(Document.owner_id == first.id).limit(1)):
            return False
        departments = {d.code: d.id for d in db.scalars(select(Department))}
        missing = {p[4] for p in PEOPLE} - set(departments)
        if missing:
            raise DemoError(f"Run python -m app.seed first; missing departments {sorted(missing)}")
        for _, email, name, role, code in PEOPLE:
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, display_name=name, role=role, status="ACTIVE",
                            department_id=departments[code], password_hash=password_hasher.hash(password)))
    return True


def letter(title: str, *lines: str) -> bytes:
    return ("\n".join([title, "", *lines, "", "г. Алматы, 2026"]) + "\n").encode()


class Company:
    def __init__(self, base: str, password: str):
        self.users = {key: Api(base, email, password) for key, email, *_ in PEOPLE}
        self.admin = Api(base, "admin@nexora.local", password)
        with SessionLocal() as db:
            self.ids = {key: db.scalar(select(User.id).where(User.email == email)) for key, email, *_ in PEOPLE}
        self.types = {t["code"]: t["id"] for t in self.admin.request("GET", "/document-types")}
        self.templates: dict[str, str] = {}

    def template(self, code: str, name_ru: str, name_en: str, stages: list[tuple[str, str, str, int]]) -> None:
        self.templates[code] = self.admin.post("/workflow-templates", {
            "code": code, "name_ru": name_ru, "name_en": name_en,
            "stages": [{"name_ru": ru, "name_en": en, "selector": "user", "targets": [self.ids[who]],
                        "due_hours": hours} for ru, en, who, hours in stages],
        })["id"]

    def document(self, owner: str, kind: str, title: str, content: bytes, *, confidentiality: str = "INTERNAL",
                 description: str = "", tags: list[str] | None = None, amount: int | None = None,
                 folder: str | None = None, versions: list[tuple[bytes, str]] | None = None) -> str:
        api = self.users[owner]
        doc = api.post("/documents", {
            "title": title, "type_id": self.types[kind], "confidentiality": confidentiality,
            "description": description, "tags": tags or [],
            "business_metadata": {"amount": amount} if amount else {},
        })
        api.request("POST", f"/documents/{doc['id']}/versions", files={
            "file": (f"{kind.lower()}.txt", content), "change_note": "Первая редакция"}, keyed=True)
        for later, note in versions or []:
            api.request("POST", f"/documents/{doc['id']}/versions", files={
                "file": (f"{kind.lower()}.txt", later), "change_note": note}, keyed=True)
        if folder:
            api.post(f"/documents/{doc['id']}/move", {"folder_id": folder, "expected_revision": self.revision(owner, doc["id"])})
        return doc["id"]

    def revision(self, who: str, doc_id: str) -> int:
        return self.users[who].request("GET", f"/documents/{doc_id}")["revision"]

    def start(self, owner: str, doc_id: str, template: str) -> str:
        key = self.users[owner].key()
        return self.users[owner].request("POST", f"/documents/{doc_id}/workflows", {
            "template_id": self.templates[template], "expected_revision": self.revision(owner, doc_id),
            "idempotency_key": key,
        })["id"]

    def decide(self, who: str, instance: str, action: str, comment: str = "") -> None:
        key = self.users[who].key()
        self.users[who].request("POST", f"/workflows/{instance}/decisions",
                                {"action": action, "comment": comment, "idempotency_key": key})

    def comment(self, who: str, doc_id: str, text: str) -> None:
        self.users[who].post(f"/documents/{doc_id}/comments", {"body": text})


def build(base: str, password: str) -> dict:
    company = Company(base, password)
    company.template("CONTRACT_APPROVAL", "Согласование договора", "Contract approval", [
        ("Юридическая проверка", "Legal review", "daniyar", 48),
        ("Утверждение директором", "Director approval", "erlan", 24)])
    company.template("ORDER_APPROVAL", "Согласование приказа", "Order approval", [
        ("Юридическая проверка", "Legal review", "daniyar", 48),
        ("Подписание директором", "Director sign-off", "erlan", 24)])
    company.template("FINANCE_APPROVAL", "Финансовое согласование", "Finance approval", [
        ("Главный бухгалтер", "Chief accountant", "olga", 24),
        ("Утверждение директором", "Director approval", "erlan", 24)])

    aigerim = company.users["aigerim"]
    contracts = aigerim.post("/folders", {"name": "Договоры 2026"})["id"]
    accounting = aigerim.post("/folders", {"name": "Бухгалтерия"})["id"]

    supply = company.document(
        "aigerim", "CONTRACT", "Договор поставки № 15/2026 с ТОО «Алтын Дала»",
        letter("ДОГОВОР ПОСТАВКИ № 15/2026", "ТОО «Алтын Дала» (Поставщик) и ТОО «NEXORA Demo» (Покупатель)",
               "1. Предмет: поставка зерна 1-го класса, 120 тонн.", "2. Цена: 24 600 000 тенге с НДС.",
               "3. Срок поставки: до 30 ноября 2026 года."),
        confidentiality="CONFIDENTIAL", description="Годовой договор с основным поставщиком",
        tags=["поставка", "2026"], amount=24_600_000, folder=contracts)
    lease = company.document(
        "aigerim", "CONTRACT", "Договор аренды офиса, г. Алматы, пр. Абая 150",
        letter("ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ", "Площадь 240 кв. м, 5 этаж.", "Арендная плата: 3 100 000 тенге в месяц."),
        description="Продление аренды на 2027 год", tags=["аренда"], amount=37_200_000, folder=contracts)
    it_services = company.document(
        "aigerim", "CONTRACT", "Договор оказания IT-услуг с ТОО «Qazaq Soft»",
        letter("ДОГОВОР ОКАЗАНИЯ УСЛУГ", "Сопровождение учётной системы и рабочих мест, 12 месяцев."),
        tags=["IT", "услуги"], amount=8_400_000, folder=contracts)
    addendum = company.document(
        "aigerim", "CONTRACT", "Дополнительное соглашение № 2 к договору поставки",
        letter("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 2", "Изменение графика поставки: две партии вместо одной."),
        folder=contracts)
    invoice = company.document(
        "aigerim", "INVOICE", "Счёт на оплату № 482 от ТОО «KazLogistics»",
        letter("СЧЁТ НА ОПЛАТУ № 482", "Транспортные услуги за октябрь 2026: 1 850 000 тенге."),
        amount=1_850_000, folder=accounting)
    company.document(
        "aigerim", "ACT", "Акт выполненных работ за октябрь 2026",
        letter("АКТ ВЫПОЛНЕННЫХ РАБОТ", "Работы выполнены в полном объёме.", "Сумма: 2 300 000 тенге."),
        folder=accounting, versions=[(letter("АКТ ВЫПОЛНЕННЫХ РАБОТ", "Работы выполнены в полном объёме.",
                                             "Сумма: 2 150 000 тенге (скидка 150 000 тенге по претензии № 7)."),
                                      "Учтена скидка по претензии")])
    tax_letter = company.document(
        "aigerim", "LETTER", "Письмо в Департамент государственных доходов по г. Алматы",
        letter("ИСХОДЯЩЕЕ ПИСЬМО", "О предоставлении разъяснений по НДС за III квартал 2026 года."),
        folder=accounting)
    company.document(
        "aigerim", "MEMO", "Қызметтік жазба: кеңсе жабдықтарын сатып алу",
        letter("ҚЫЗМЕТТІК ЖАЗБА", "Бухгалтерия бөліміне 5 ноутбук сатып алу қажет.", "Болжамды құны: 2 500 000 теңге."),
        tags=["сатып алу"])

    hire = company.document(
        "asel", "ORDER", "Приказ о приёме на работу: Сапарова Д. К.",
        letter("ПРИКАЗ № 214-К", "Принять Сапарову Динару Кайратовну на должность бухгалтера с 1 декабря 2026 г."),
        confidentiality="CONFIDENTIAL")
    vacation = company.document(
        "asel", "ORDER", "Жыл сайынғы еңбек демалысы туралы бұйрық",
        letter("БҰЙРЫҚ № 215-Д", "Ким Ольгаға 2026 жылғы 15 желтоқсаннан бастап 14 күнтізбелік күн еңбек демалысы берілсін."))
    trips = company.document(
        "asel", "POLICY", "Положение о служебных командировках",
        letter("ПОЛОЖЕНИЕ О СЛУЖЕБНЫХ КОМАНДИРОВКАХ", "Суточные по Казахстану: 6 МРП.", "Авансовый отчёт — в течение 5 рабочих дней."))
    company.document(
        "asel", "APPLICATION", "Заявление на материальную помощь",
        letter("ЗАЯВЛЕНИЕ", "Прошу оказать материальную помощь в связи с рождением ребёнка."), confidentiality="CONFIDENTIAL")
    company.document(
        "asel", "POLICY", "Политика информационной безопасности",
        letter("ПОЛИТИКА ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ", "Доступ к конфиденциальным документам — по служебной необходимости."),
        confidentiality="RESTRICTED")

    company.comment("aigerim", supply, "Цены сверены с коммерческим предложением от 02.11.2026.")
    instance = company.start("aigerim", supply, "CONTRACT_APPROVAL")
    company.decide("daniyar", instance, "approve", "Замечаний нет, условия ответственности соответствуют практике.")
    company.decide("erlan", instance, "approve", "Утверждаю.")

    instance = company.start("aigerim", lease, "CONTRACT_APPROVAL")
    company.decide("daniyar", instance, "approve", "Согласовано. Проверьте реквизиты арендодателя перед подписанием.")

    overdue = company.start("aigerim", it_services, "CONTRACT_APPROVAL")

    instance = company.start("aigerim", addendum, "CONTRACT_APPROVAL")
    company.decide("daniyar", instance, "revision", "Уточните сроки поставки второй партии в п. 3.2.")

    company.start("aigerim", invoice, "FINANCE_APPROVAL")
    instance = company.start("aigerim", tax_letter, "FINANCE_APPROVAL")
    company.decide("olga", instance, "reject", "Письмо в ДГД подписывает директор. Переоформите от его имени.")

    instance = company.start("asel", hire, "ORDER_APPROVAL")
    company.decide("daniyar", instance, "approve", "")
    company.decide("erlan", instance, "approve", "Подписано.")
    company.start("asel", vacation, "ORDER_APPROVAL")
    instance = company.start("asel", trips, "ORDER_APPROVAL")
    company.decide("daniyar", instance, "approve", "")
    company.decide("erlan", instance, "approve", "")

    aigerim.request("PUT", f"/documents/{supply}/favorite")
    aigerim.request("PUT", f"/documents/{lease}/favorite")

    # Demo-only: make one legal review two days late, then escalate it like the scheduler would.
    with SessionLocal.begin() as db:
        db.execute(update(Approval).where(Approval.instance_id == overdue, Approval.status == "PENDING")
                   .values(due_at=datetime.now(UTC) - timedelta(days=2)))
    escalated = escalate(apply=True)
    with SessionLocal.begin() as db:
        # People have already read notices about tasks they have since decided.
        decided = select(Approval.id).where(Approval.status.not_in(["PENDING", "WAITING"]))
        db.execute(update(Notification).where(Notification.approval_id.in_(decided),
                                              Notification.kind == "TASK_ASSIGNED")
                   .values(read_at=datetime.now(UTC)))
        db.add(AuditEvent(actor_id=None, action="DEMO_DATA_LOADED", target_type="system", target_id=None,
                          safe_metadata={"people": len(PEOPLE), "documents": 13}, request_id=str(uuid.uuid4())))
    return {"people": len(PEOPLE), "documents": 13, "escalated": escalated["escalated"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    config = settings()
    if config.app_env != "development" or not config.seed_demo or len(config.demo_password) < 12:
        raise SystemExit("Demo data requires APP_ENV=development, SEED_DEMO=true and DEMO_PASSWORD (>= 12 chars)")
    wait_for(args.api)
    if not ensure_people(config.demo_password):
        print("Demo company already present; nothing changed.")
        return
    print("Demo company loaded:", build(args.api, config.demo_password))


if __name__ == "__main__":
    main()
