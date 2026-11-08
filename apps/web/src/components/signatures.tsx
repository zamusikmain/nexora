"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { NcaLayerError, signWithNcaLayer, toBase64 } from "@/lib/ncalayer";
import { Signature } from "@/lib/types";
import { useI18n } from "./provider";

export function VersionSignatures({
  documentId,
  versionId,
  signatures,
  canSign,
  onSigned,
}: {
  documentId: string;
  versionId: string;
  signatures: Signature[];
  canSign: boolean;
  onSigned: () => Promise<void>;
}) {
  const { t, lang } = useI18n();
  const [state, setState] = useState("");
  const [error, setError] = useState("");
  const mine = signatures.some((s) => s.mine);
  async function sign() {
    setError("");
    try {
      setState("signatureReading");
      // The exact stored bytes are signed; the server verifies against its own copy.
      const response = await fetch(`/api/v1/documents/${documentId}/versions/${versionId}/download`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new ApiError("file_unavailable", response.status);
      const data = toBase64(new Uint8Array(await response.arrayBuffer()));
      setState("signatureWaiting");
      const cms = await signWithNcaLayer(data, lang);
      setState("signatureSending");
      await api(`/documents/${documentId}/versions/${versionId}/signatures`, {
        method: "POST",
        body: JSON.stringify({ cms }),
      });
      await onSigned();
    } catch (e) {
      setError(e instanceof NcaLayerError || e instanceof ApiError ? e.code : "error");
    } finally {
      setState("");
    }
  }
  return (
    <div className="signatures">
      {signatures.map((s) => (
        <p key={s.id} className={`signature ${s.status === "VALID" ? "valid" : "unverified"}`}>
          <strong>{t(s.status === "VALID" ? "signatureValid" : "signatureUnverified")}</strong>{" "}
          {s.subject_name || s.signer_name}
          {s.subject_iin && <> · {t("iin")} {s.subject_iin}</>}
          {s.subject_bin && <> · {t("bin")} {s.subject_bin}</>}
          {" · "}
          {new Date(s.created_at).toLocaleString(lang)}{" "}
          <a href={`/api/v1/documents/${documentId}/signatures/${s.id}/cms`}>{t("signatureFile")}</a>
        </p>
      ))}
      {canSign && !mine && (
        <button type="button" disabled={!!state} onClick={sign}>
          {t(state || "signWithEds")}
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {t(error)}
        </p>
      )}
    </div>
  );
}
