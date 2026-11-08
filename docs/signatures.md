# Electronic signatures (ЭЦП) with NCALayer

Migration `0012_signatures` adds `document_signatures`. Any user who may read a version's file may sign that version once.

## Flow

1. The browser downloads the version's stored bytes. It then asks **NCALayer** (`wss://127.0.0.1:13579`, on the signer's own machine) for a detached CMS signature with a *signing* certificate (EKU `1.3.6.1.5.5.7.3.4`). The private key never leaves NCALayer or the token.
2. The browser posts the CMS to `POST /api/v1/documents/{id}/versions/{version_id}/signatures`. This uses a signed retry key and CSRF.
3. With `SIGNATURE_VERIFIER=ncanode` the server **re-reads its own copy** of the version, after checking its size and SHA-256. It then calls NCANode `POST {NCANODE_URL}/cms/verify` with the CMS, those bytes and OCSP revocation checking. A signature counts only when all of these hold:
   - the verdict is `valid`;
   - the CMS has exactly one signer;
   - the signer's certificate is not marked invalid.
   
   Anything else is rejected with 422 `signature_invalid` and audited as `SIGNATURE_REJECTED`. An NCANode outage returns 503 `signature_verifier_unavailable` and stores nothing.
4. Accepted signatures are stored with status `VALID`. The name, IIN, BIN, serial and validity come **only from the verifier**, never from the client. The audit event is `DOCUMENT_SIGNED`.

## Development mode

`SIGNATURE_VERIFIER=none` (the default) stores signatures as `UNVERIFIED`. The UI labels them "stored, not verified by the server". Production refuses to store anything without a verifier.

## Evidence and privacy

- Rows are immutable. The runtime has `SELECT, INSERT` only, and a trigger refuses UPDATE and DELETE for every role.
- Lists show the IIN masked (`9001****23`).
- The original `.p7s` file contains the full certificate. It can be downloaded only by users who may read that version's file, for verification in external tools.

## Not verified here, and limits

- **The NCANode integration was tested only against a fake.** The request and response shapes follow the NCANode v3 `/cms/verify` API. Before a pilot:
  1. deploy NCANode;
  2. sign with a real key and with a test key from НУЦ РК;
  3. confirm that the verdict and certificate fields are parsed correctly.
  
  An unknown response shape fails closed: the signature is rejected.
- **Signing in NCALayer has not been run here**, because no NCALayer or keys were available. The unit tests cover the protocol with a fake socket. E2E covers only the "NCALayer not running" path.
- **The certificate's IIN is not matched to the NEXORA account.** User records have no IIN yet, so both the account name and the certificate subject are shown.
- **Not implemented:** timestamp policy checks, long-term validation (archived OCSP and CRL evidence), signing of workflow decisions, and multi-signer approval requirements.

## Configuration

```
SIGNATURE_VERIFIER=ncanode
NCANODE_URL=http://ncanode:14579
SIGNATURE_TIMEOUT_SECONDS=30
```

The browser must reach NCALayer on the user's machine; the CSP `connect-src` allows only `'self'` and `wss://127.0.0.1:13579`.
