"""ЭЦП signatures over immutable versions; NCANode is replaced by a recording fake."""

import base64

import pytest
from sqlalchemy import select, text
from test_acl_contracts import uploaded
from test_api import client, create
from test_api import database as database  # noqa: F401

from app import signatures
from app.config import settings
from app.models import AuditEvent, DocumentSignature

CMS = base64.b64encode(b"synthetic-detached-cms-" * 4).decode()


def signed(owner, base, version, cms=CMS):
    return owner.post(f"{base}/versions/{version}/signatures", json={"cms": cms})


def setup_version():
    owner = client()
    base = "/api/v1/documents/" + create(owner)["id"]
    return owner, base, uploaded(owner, base, "contract.txt")


def test_development_signature_is_stored_as_unverified_once(database):
    owner, base, version = setup_version()
    response = signed(owner, base, version)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "UNVERIFIED" and data["subject_name"] is None and data["signer_name"] == "owner"
    assert signed(owner, base, version).json()["error"] == "already_signed"
    assert [s["id"] for s in owner.get(base + "/signatures").json()] == [data["id"]]
    cms = owner.get(f"{base}/signatures/{data['id']}/cms")
    assert cms.status_code == 200 and cms.content == base64.b64decode(CMS)
    assert cms.headers["content-type"] == "application/pkcs7-signature"


def test_signing_requires_file_access_and_valid_input(database):
    owner, base, version = setup_version()
    stranger = client("stranger")
    assert signed(stranger, base, version).status_code == 404
    assert stranger.get(base + "/signatures").status_code == 404
    assert signed(owner, base, "missing-version").status_code == 404
    assert signed(owner, base, version, "not base64 !!!!!!!!").json()["error"] == "invalid_signature"
    data = signed(owner, base, version).json()
    assert stranger.get(f"{base}/signatures/{data['id']}/cms").status_code == 404


@pytest.fixture
def ncanode(monkeypatch):
    calls = []
    verdict = {"value": None}

    def fake(cms, data):
        calls.append((cms, data))
        if verdict["value"] == "down":
            raise signatures.VerifierUnavailable
        return verdict["value"]

    monkeypatch.setattr(settings(), "signature_verifier", "ncanode")
    monkeypatch.setattr(signatures, "ncanode_verify", fake)
    return calls, verdict


def valid(**certificate):
    return {"valid": True, "signers": [{"certificates": [{
        "valid": True, "serialNumber": "5f3a", "notBefore": "2026-01-01T00:00:00Z", "notAfter": "2027-01-01T00:00:00Z",
        "subject": {"commonName": "ИВАНОВ ИВАН", "iin": "900101300123", "bin": None}, **certificate}]}]}


def test_ncanode_checks_the_stored_bytes_and_records_the_certificate(database, ncanode):
    calls, verdict = ncanode
    owner, base, version = setup_version()
    verdict["value"] = valid()
    data = signed(owner, base, version).json()
    assert data["status"] == "VALID" and data["subject_name"] == "ИВАНОВ ИВАН"
    assert data["subject_iin"] == "9001****23"  # personal data is masked in lists
    assert data["certificate_serial"] == "5f3a" and data["certificate_not_after"].startswith("2027-01-01")
    # The verifier saw the exact stored file, never bytes supplied by the client.
    assert calls == [(CMS, b"Private test content")]
    with database() as db:
        assert db.scalar(select(DocumentSignature.subject_iin).where(DocumentSignature.id == data["id"])) \
            == "900101300123"


@pytest.mark.parametrize("verdict_value", [
    {"valid": False},
    {"valid": True, "signers": []},
    {"valid": True, "signers": [{}, {}]},
    "revoked",
])
def test_invalid_verdicts_are_rejected_and_not_stored(database, ncanode, verdict_value):
    _, verdict = ncanode
    owner, base, version = setup_version()
    verdict["value"] = valid(valid=False) if verdict_value == "revoked" else verdict_value
    response = signed(owner, base, version)
    assert response.status_code == 422 and response.json()["error"] == "signature_invalid"
    assert owner.get(base + "/signatures").json() == []
    with database() as db:
        assert db.query(AuditEvent).filter_by(target_id=base.rsplit("/", 1)[1],
                                              action="SIGNATURE_REJECTED").count() == 1


def test_verifier_outage_and_production_without_verifier_fail_closed(database, ncanode, monkeypatch):
    _, verdict = ncanode
    owner, base, version = setup_version()
    verdict["value"] = "down"
    assert signed(owner, base, version).json()["error"] == "signature_verifier_unavailable"
    monkeypatch.setattr(settings(), "signature_verifier", "none")
    monkeypatch.setattr(settings(), "app_env", "production")
    monkeypatch.setattr(signatures, "require_scan", lambda version, db: None)
    assert signed(owner, base, version).json()["error"] == "signature_verifier_unavailable"
    assert owner.get(base + "/signatures").json() == []


def test_signatures_are_immutable_in_the_database(database):
    owner, base, version = setup_version()
    data = signed(owner, base, version).json()
    for statement in ("UPDATE document_signatures SET status='VALID' WHERE id=:id",
                      "DELETE FROM document_signatures WHERE id=:id"):
        with pytest.raises(Exception, match="immutable"), database.begin() as db:
            db.execute(text(statement), {"id": data["id"]})


def test_signer_details_fail_closed_on_unknown_shapes():
    assert signatures.signer_details({}) is None
    assert signatures.signer_details({"valid": "true", "signers": []}) is None
    assert signatures.signer_details({"valid": True, "signers": ["x"]}) is None
    assert signatures.signer_details(valid())["subject_iin"] == "900101300123"
    assert signatures.masked("123") is None
