"use client";

import { useState } from "react";

import type { UploadMode } from "@/lib/types";

export default function RunButtons({
  uploadMode,
  readOnly = false,
}: {
  uploadMode: UploadMode;
  readOnly?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (readOnly) {
    return null;
  }

  async function run(workflow: "pipeline" | "upload") {
    setBusy(workflow);
    setMessage(null);
    try {
      const response = await fetch(`/api/run/${workflow}`, {
        method: "POST",
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      setMessage("Workflow queued.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not queue workflow.",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => run("pipeline")}
          disabled={busy !== null}
          className="rounded-xl bg-yellow-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === "pipeline" ? "Starting…" : "Fetch new clips now"}
        </button>
        {uploadMode === "api" ? (
          <button
            type="button"
            onClick={() => run("upload")}
            disabled={busy !== null}
            className="rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "upload" ? "Starting…" : "Upload approved now"}
          </button>
        ) : null}
      </div>
      {message ? (
        <p role="status" className="text-sm text-zinc-400">
          {message}
        </p>
      ) : null}
    </div>
  );
}
