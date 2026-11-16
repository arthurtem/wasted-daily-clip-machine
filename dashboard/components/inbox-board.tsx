"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { formatAge } from "@/lib/format";
import type { QueueClip } from "@/lib/types";

function Thumbnail({ clip }: { clip: QueueClip }) {
  const url = clip.thumbnail_url?.replace(
    /%\{width\}/,
    "480",
  ).replace(/%\{height\}/, "270");
  if (url) {
    return (
      <img
        src={url}
        alt=""
        className="aspect-video w-full bg-black object-cover"
      />
    );
  }
  return (
    <div className="flex aspect-video items-center justify-center bg-black text-xs text-zinc-500">
      No thumbnail
    </div>
  );
}

export default function InboxBoard({
  clips,
  readOnly,
}: {
  clips: QueueClip[];
  readOnly: boolean;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const allSelected = clips.length > 0 && selected.size === clips.length;
  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function render(ids: string[]) {
    if (readOnly || ids.length === 0) {
      return;
    }
    setBusy("render");
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/run/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clip_ids: ids }),
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string; run?: { html_url?: string; status?: string } }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      setMessage(
        `Render workflow queued for ${ids.length} clip(s)${
          data?.run?.status ? ` (${data.run.status})` : ""
        }.`,
      );
      if (data?.run?.html_url) {
        window.open(data.run.html_url, "_blank", "noopener,noreferrer");
      }
      window.setTimeout(() => router.refresh(), 3000);
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Request failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function reject(ids: string[]) {
    if (readOnly || ids.length === 0) {
      return;
    }
    setBusy("reject");
    setError(null);
    try {
      for (const id of ids) {
        const response = await fetch(`/api/clips/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "rejected" }),
        });
        if (!response.ok) {
          const data = (await response.json().catch(() => null)) as
            | { error?: string }
            | null;
          throw new Error(data?.error ?? `Request failed (${response.status})`);
        }
      }
      setSelected(new Set());
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Request failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  if (clips.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-zinc-800 bg-zinc-900/40 px-6 py-16 text-center">
        <h2 className="text-lg font-semibold">No imported clips waiting</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Run Fetch clips from the queue page to import Twitch clips here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-3">
        <button
          type="button"
          onClick={() =>
            setSelected(allSelected ? new Set() : new Set(clips.map((c) => c.id)))
          }
          disabled={readOnly}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-50"
        >
          {allSelected ? "Clear selection" : "Select all"}
        </button>
        <button
          type="button"
          onClick={() => render(selectedIds)}
          disabled={readOnly || busy !== null || selectedIds.length === 0}
          className="rounded-lg bg-yellow-400 px-3 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "render" ? "Starting…" : `Render selected (${selectedIds.length})`}
        </button>
        <button
          type="button"
          onClick={() => render(clips.slice(0, 25).map((clip) => clip.id))}
          disabled={readOnly || busy !== null}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-50"
        >
          Render all new
        </button>
        <button
          type="button"
          onClick={() => reject(selectedIds)}
          disabled={readOnly || busy !== null || selectedIds.length === 0}
          className="rounded-lg border border-red-900 px-3 py-2 text-xs font-semibold text-red-200 transition hover:bg-red-950/60 disabled:opacity-50"
        >
          Reject selected
        </button>
      </div>

      {message ? <p className="text-sm text-zinc-400">{message}</p> : null}
      {error ? (
        <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      {readOnly ? (
        <p className="text-xs text-amber-300">
          Review-only access: import actions are disabled.
        </p>
      ) : null}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {clips.map((clip) => (
          <article
            key={clip.id}
            className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/60"
          >
            <div className="relative">
              <Thumbnail clip={clip} />
              <label className="absolute left-2 top-2 flex items-center gap-2 rounded-lg bg-zinc-950/85 px-2 py-1 text-xs">
                <input
                  type="checkbox"
                  checked={selected.has(clip.id)}
                  onChange={() => toggle(clip.id)}
                  disabled={readOnly}
                />
                Select
              </label>
            </div>
            <div className="space-y-2 p-3">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-sm font-semibold">{clip.streamer_name}</h2>
                {clip.reddit_score != null ? (
                  <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-semibold text-orange-300">
                    Reddit {clip.reddit_score}
                  </span>
                ) : null}
              </div>
              <p className="line-clamp-2 text-xs text-zinc-400">
                {clip.clip_title ?? clip.id}
              </p>
              <p className="text-xs text-zinc-500">
                {clip.view_count?.toLocaleString() ?? 0} views ·{" "}
                {formatAge(clip.clip_created_at)}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <a
                  href={clip.clip_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-zinc-300 underline decoration-zinc-700 underline-offset-4"
                >
                  Original clip
                </a>
                {clip.reddit_url ? (
                  <a
                    href={clip.reddit_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-orange-300 underline decoration-orange-900 underline-offset-4"
                  >
                    Reddit post
                  </a>
                ) : null}
                <button
                  type="button"
                  onClick={() => render([clip.id])}
                  disabled={readOnly || busy !== null}
                  className="text-xs text-zinc-300 underline decoration-zinc-700 underline-offset-4 disabled:opacity-50"
                >
                  Render
                </button>
                <button
                  type="button"
                  onClick={() => reject([clip.id])}
                  disabled={readOnly || busy !== null}
                  className="text-xs text-red-300 underline decoration-red-900 underline-offset-4 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
