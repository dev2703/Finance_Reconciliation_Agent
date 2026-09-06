"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useState } from "react";

type ParseError = {
  row_number: number;
  sheet?: string;
  field?: string;
  original_value?: string;
  message: string;
};

type DocumentState = {
  document: { id: string; filename: string };
  status: string;
  progress: number;
  progress_message: string;
  record_count: number;
  error_count: number;
  duplicate?: boolean;
  records?: Array<Record<string, unknown>>;
  errors?: ParseError[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const terminalStatuses = new Set(["PARSED", "FAILED", "CONFIRMED"]);

function uploadWithProgress(
  url: string,
  formData: FormData,
  onProgress: (progress: number) => void,
): Promise<DocumentState> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      const payload = JSON.parse(request.responseText);
      if (request.status >= 400) reject(new Error(payload.detail ?? "Upload failed"));
      else resolve(payload);
    };
    request.onerror = () => reject(new Error("Upload failed"));
    request.send(formData);
  });
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [recordType, setRecordType] = useState("invoice");
  const [document, setDocument] = useState<DocumentState | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  useEffect(() => {
    if (!document || terminalStatuses.has(document.status)) return;
    let attempts = 0;
    let failures = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      if (attempts > 60) {
        setError("Ingestion polling timed out. You can retry the job.");
        window.clearInterval(timer);
        return;
      }
      try {
        const response = await fetch(`${API_URL}/documents/${document.document.id}`);
        if (!response.ok) throw new Error("status request failed");
        failures = 0;
        setDocument(await response.json());
      } catch {
        failures += 1;
        if (failures >= 3) {
          setError("Could not reach the ingestion service. You can retry the job.");
          window.clearInterval(timer);
        }
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [document]);

  useEffect(() => {
    if (!document || !terminalStatuses.has(document.status)) return;
    fetch(`${API_URL}/documents/${document.document.id}/preview`)
      .then((response) => response.json())
      .then(setPreview)
      .catch(() => setError("Could not load the document preview."));
  }, [document]);

  function chooseFile(nextFile: File | null) {
    setFile(nextFile);
    setDocument(null);
    setPreview(null);
    setError("");
    setUploadProgress(0);
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0] ?? null);
  }

  function dropFile(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    chooseFile(event.dataTransfer.files[0] ?? null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a CSV or XLSX file first.");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("record_type", recordType);
    setIsUploading(true);
    setError("");
    try {
      const result = await uploadWithProgress(`${API_URL}/documents/upload`, formData, setUploadProgress);
      setDocument(result);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function confirmImport() {
    if (!document) return;
    setIsConfirming(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/documents/${document.document.id}/confirm`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Confirmation failed");
      setDocument(payload);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "Confirmation failed");
    } finally {
      setIsConfirming(false);
    }
  }

  async function retryImport() {
    if (!document) return;
    setError("");
    try {
      const response = await fetch(`${API_URL}/documents/${document.document.id}/retry`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Retry failed");
      setDocument(payload);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Retry failed");
    }
  }

  const errors = (preview?.errors as ParseError[] | undefined) ?? [];
  const records = (preview?.records as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "48px 24px" }}>
      <h1>Finance Reconciliation</h1>
      <p>Upload a source file, review normalized records, and confirm the import.</p>
      <form onSubmit={upload} style={{ display: "grid", gap: 16, maxWidth: 520 }}>
        <label>
          Record type
          <select value={recordType} onChange={(event) => setRecordType(event.target.value)}>
            <option value="invoice">Invoice</option>
            <option value="payment">Payment</option>
            <option value="settlement">Settlement</option>
            <option value="bank">Bank transaction</option>
            <option value="ledger">Ledger entry</option>
          </select>
        </label>
        <label onDragOver={(event) => event.preventDefault()} onDrop={dropFile}>
          Source file (drop here or browse)
          <input type="file" accept=".csv,.xlsx" onChange={selectFile} />
          {file && <span>{file.name} ({Math.ceil(file.size / 1024)} KB)</span>}
        </label>
        <button type="submit" disabled={isUploading}>
          {isUploading ? `Uploading ${uploadProgress}%` : "Upload and preview"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {document && (
        <section aria-live="polite">
          <h2>{document.document.filename}</h2>
          {document.duplicate && <p>This file was already uploaded; showing the existing import.</p>}
          <p>
            Status: {document.status} · {document.progress}% · {document.progress_message}
          </p>
          <progress value={document.progress} max="100" />
          {document.status === "PARSED" && (
            <button type="button" onClick={confirmImport} disabled={isConfirming}>
              {isConfirming ? "Confirming..." : "Confirm import"}
            </button>
          )}
          {document.status === "FAILED" && <p>Resolve the row errors before confirming this import.</p>}
          {(document.status === "FAILED" || document.status === "UPLOADED") && (
            <button type="button" onClick={retryImport}>Retry ingestion</button>
          )}
        </section>
      )}
      {records.length > 0 && (
        <section>
          <h2>Normalized records ({records.length})</h2>
          <pre style={{ overflowX: "auto" }}>{JSON.stringify(records, null, 2)}</pre>
        </section>
      )}
      {errors.length > 0 && (
        <section>
          <h2>Row errors ({errors.length})</h2>
          <ul>
            {errors.map((rowError, index) => (
              <li key={`${rowError.row_number}-${index}`}>
                Row {rowError.row_number}{rowError.sheet ? `, ${rowError.sheet}` : ""}: {rowError.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
