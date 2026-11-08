"""Electronic signatures (ЭЦП) made in the browser with NCALayer, over one immutable version.

The browser signs the exact file bytes (detached CMS). The server never trusts what the client
says about the signer: with SIGNATURE_VERIFIER=ncanode it re-reads the stored file, and NCANode
(Kalkan) checks the CMS against those bytes, the certificate chain to НУЦ РК and revocation
(OCSP). Signer name/IIN/BIN shown in the UI come only from that verification. Without a
verifier (development) a signature is stored as UNVERIFIED and labelled so; production refuses.
"""

import base64
import binascii
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import select

from app.audit import audit
from app.auth import Actor, Db
from app.config import settings
from app.documents import get_document, require_scan
from app.idempotency import begin, finish
from app.models import DocumentSignature, DocumentVersion, User
from app.schemas import Input
from app.storage import storage

router = APIRouter(tags=["signatures"])


class SignatureInput(Input):
    cms: str = Field(min_length=16, max_length=300_000)


class VerifierUnavailable(Exception):
    pass


def stored_bytes(version: DocumentVersion) -> bytes:
    """Exact stored bytes of the version, checked against its recorded size and SHA-256."""
    try:
        with storage().open(version.storage_key) as file:
            data = file.read(version.size + 1)
    except FileNotFoundError:
        raise HTTPException(503, "file_unavailable") from None
    if len(data) != version.size or hashlib.sha256(data).hexdigest() != version.sha256:
        raise HTTPException(503, "file_unavailable")
    return data


def ncanode_verify(cms: str, data: bytes) -> dict[str, Any]:
    body = json.dumps({"revocationCheck": ["OCSP"], "cms": cms, "data": base64.b64encode(data).decode()}).encode()
    request = urllib.request.Request(
        settings().ncanode_url.rstrip("/") + "/cms/verify", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings().signature_timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        # NCANode answers 4xx for malformed or invalid CMS; that is a verdict, not an outage.
        if 400 <= error.code < 500:
            return {"valid": False}
        raise VerifierUnavailable from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise VerifierUnavailable from None


def instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def signer_details(result: dict[str, Any]) -> dict[str, Any] | None:
    """Exactly one signer with a valid certificate, or None. Unknown shapes fail closed."""
    signers = result.get("signers")
    if result.get("valid") is not True or not isinstance(signers, list) or len(signers) != 1:
        return None
    certificates = signers[0].get("certificates") if isinstance(signers[0], dict) else None
    if not isinstance(certificates, list) or not certificates or not isinstance(certificates[0], dict):
        return None
    certificate = certificates[0]
    if certificate.get("valid") is False:
        return None
    raw_subject = certificate.get("subject")
    subject: dict[str, Any] = raw_subject if isinstance(raw_subject, dict) else {}

    def text(key: str, size: int) -> str | None:
        return str(subject[key])[:size] if subject.get(key) else None
    return {
        "subject_name": text("commonName", 300),
        "subject_iin": text("iin", 12),
        "subject_bin": text("bin", 12),
        "certificate_serial": str(certificate.get("serialNumber"))[:80] if certificate.get("serialNumber") else None,
        "certificate_not_before": instant(certificate.get("notBefore")),
        "certificate_not_after": instant(certificate.get("notAfter")),
    }


def masked(iin: str | None) -> str | None:
    # IIN is personal data; the full value stays inside the CMS for those who may download it.
    return iin[:4] + "****" + iin[-2:] if iin and len(iin) == 12 else None


def signature_data(row: DocumentSignature, name: str, user: User) -> dict:
    return {
        "id": row.id,
        "mine": row.signer_id == user.id,
        "version_id": row.version_id,
        "signer_name": name,
        "status": row.status,
        "subject_name": row.subject_name,
        "subject_iin": masked(row.subject_iin),
        "subject_bin": row.subject_bin,
        "certificate_serial": row.certificate_serial,
        "certificate_not_after": row.certificate_not_after,
        "created_at": row.created_at,
    }


@router.get("/documents/{doc_id}/signatures")
def list_signatures(doc_id: str, db: Db, user: Actor) -> list[dict]:
    get_document(db, user, doc_id)
    rows = db.execute(
        select(DocumentSignature, User.display_name).join(User, User.id == DocumentSignature.signer_id)
        .where(DocumentSignature.document_id == doc_id).order_by(DocumentSignature.created_at).limit(500)
    ).all()
    return [signature_data(row, name, user) for row, name in rows]


@router.post("/documents/{doc_id}/versions/{version_id}/signatures", status_code=201)
def sign(doc_id: str, version_id: str, body: SignatureInput, request: Request, db: Db, user: Actor) -> dict:
    replay = begin(db, user, request, body.model_dump(mode="json"))
    doc = get_document(db, user, doc_id, action="file", version_id=version_id)
    if replay is not None:
        return replay
    version = db.scalar(select(DocumentVersion).where(
        DocumentVersion.id == version_id, DocumentVersion.document_id == doc_id))
    if version is None:
        raise HTTPException(404, "not_found")
    if doc.deleted_at is not None:
        raise HTTPException(409, "document_in_trash")
    require_scan(version, db)
    try:
        raw = base64.b64decode(body.cms, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "invalid_signature") from None
    if db.scalar(select(DocumentSignature.id).where(
            DocumentSignature.version_id == version_id, DocumentSignature.signer_id == user.id)):
        raise HTTPException(409, "already_signed")
    details: dict[str, Any] = {}
    if settings().signature_verifier == "ncanode":
        try:
            verdict = signer_details(ncanode_verify(body.cms, stored_bytes(version)))
        except VerifierUnavailable:
            raise HTTPException(503, "signature_verifier_unavailable") from None
        if verdict is None:
            db.info.pop("operation", None)
            audit(db, request, user.id, "SIGNATURE_REJECTED", "document", doc_id, {"version_id": version_id})
            db.commit()
            raise HTTPException(422, "signature_invalid")
        details, status = verdict, "VALID"
    elif settings().app_env == "production":
        raise HTTPException(503, "signature_verifier_unavailable")
    else:
        status = "UNVERIFIED"
    row = DocumentSignature(
        document_id=doc_id, version_id=version_id, signer_id=user.id, cms=body.cms,
        cms_sha256=hashlib.sha256(raw).hexdigest(), status=status, verifier=settings().signature_verifier,
        **details,
    )
    db.add(row)
    db.flush()
    audit(db, request, user.id, "DOCUMENT_SIGNED", "document", doc_id,
          {"version_id": version_id, "signature_id": row.id, "status": status})
    db.refresh(row)
    return finish(db, signature_data(row, user.display_name, user))


@router.get("/documents/{doc_id}/signatures/{signature_id}/cms")
def download_cms(doc_id: str, signature_id: str, db: Db, user: Actor) -> Response:
    row = db.scalar(select(DocumentSignature).where(
        DocumentSignature.id == signature_id, DocumentSignature.document_id == doc_id))
    # The CMS carries the full certificate (name, IIN): only readers of that version's file get it.
    get_document(db, user, doc_id, action="file", version_id=row.version_id if row else None)
    if row is None:
        raise HTTPException(404, "not_found")
    return Response(
        base64.b64decode(row.cms), media_type="application/pkcs7-signature",
        headers={"Content-Disposition": f'attachment; filename="signature-{row.id}.p7s"'},
    )
