"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SettingsDisconnect() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function disconnect() {
    if (
      !window.confirm(
        "Disconnect YouTube? This clears the stored channel and token reference. You still need to revoke Google access separately.",
      )
    ) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/disconnect", {
        method: "POST",
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      router.refresh();
    } catch (disconnectError) {
      setError(
        disconnectError instanceof Error
          ? disconnectError.message
          : "Request failed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={disconnect}
        disabled={pending}
        className="rounded-xl border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm font-semibold text-red-200 transition hover:bg-red-950/70 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Disconnecting…" : "Disconnect YouTube"}
      </button>
      {error ? (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}
