from sqlalchemy import select

from app.auth import password_hasher
from app.config import settings
from app.db import SessionLocal
from app.models import Department, DocumentType, User

DEPARTMENTS = [
    ("IT", "Информационные технологии", "Information Technology"),
    ("LEGAL", "Юридический отдел", "Legal"),
    ("FINANCE", "Финансы", "Finance"),
    ("HR", "Персонал", "Human Resources"),
    ("OPERATIONS", "Операции", "Operations"),
    ("MANAGEMENT", "Руководство", "Management"),
]
TYPES = [
    ("CONTRACT", "Договор", "Contract"),
    ("INVOICE", "Счёт", "Invoice"),
    ("ORDER", "Приказ", "Order"),
    ("MEMO", "Служебная записка", "Memo"),
    ("POLICY", "Политика", "Policy"),
    ("ACT", "Акт", "Act"),
    ("APPLICATION", "Заявление", "Application"),
    ("LETTER", "Письмо", "Letter"),
    ("OTHER", "Другое", "Other"),
]


def seed() -> None:
    cfg = settings()
    if not cfg.seed_demo:
        return
    if cfg.app_env != "development" or len(cfg.demo_password) < 12:
        raise RuntimeError("Demo seed requires development environment and DEMO_PASSWORD >= 12 chars")
    with SessionLocal.begin() as db:
        for code, ru, en in DEPARTMENTS:
            if not db.scalar(select(Department).where(Department.code == code)):
                db.add(Department(code=code, name_ru=ru, name_en=en))
        for code, ru, en in TYPES:
            if not db.scalar(select(DocumentType).where(DocumentType.code == code)):
                db.add(DocumentType(code=code, name_ru=ru, name_en=en))
        db.flush()
        department = db.scalar(select(Department).where(Department.code == "IT"))
        legal = db.scalar(select(Department).where(Department.code == "LEGAL"))
        assert department and legal
        for role in ["USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"]:
            email = role.lower() + "@nexora.local"
            if not db.scalar(select(User).where(User.email == email)):
                db.add(
                    User(
                        email=email,
                        display_name=role.title() + " Demo",
                        role=role,
                        status="ACTIVE",
                        password_hash=password_hasher.hash(cfg.demo_password),
                        department_id=legal.id if role == "LEGAL" else department.id,
                    )
                )
        if not db.scalar(select(User).where(User.email == "other@nexora.local")):
            db.add(
                User(
                    email="other@nexora.local",
                    display_name="Other Demo",
                    role="USER",
                    password_hash=password_hasher.hash(cfg.demo_password),
                    department_id=legal.id,
                )
            )
    print("Development seed complete; no document or production data seeded.")


if __name__ == "__main__":
    seed()
