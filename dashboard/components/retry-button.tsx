"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function RetryButton({
  clipId,
  readOnly = false,
}: {
  clipId: string;
  readOnly?: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retry() {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/clips/${clipId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "new" }),
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      router.refresh();
    } catch (retryError) {
      setError(
        retryError instanceof Error ? retryError.message : "Request failed.",
      );
    } finally {
      setPending(false);
    }
  }

  if (readOnly) {
    return null;
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={retry}
        disabled={pending}
        className="rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Retrying…" : "Retry"}
      </button>
      {error ? (
        <p role="alert" className="text-xs text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}
