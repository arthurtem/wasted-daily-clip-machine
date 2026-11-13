"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ApprovedClip } from "@/lib/types";

export default function PostCard({ clip }: { clip: ApprovedClip }) {
  const router = useRouter();
  const [copied, setCopied] = useState<"title" | "description" | null>(null);
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const title = clip.yt_title ?? "";
  const description = clip.yt_description ?? "";
  const filename = `${clip.streamer_login}-${clip.id}.mp4`;

  async function copy(kind: "title" | "description", value: string) {
    setError(null);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      setError("Could not copy to the clipboard.");
    }
  }

  async function markPosted(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/clips/${clip.id}/posted`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string; warning?: string }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      if (data?.warning) {
        window.alert(data.warning);
      }
      router.refresh();
    } catch (postError) {
      setError(
        postError instanceof Error ? postError.message : "Request failed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <article className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/60">
      {clip.blob_url ? (
        <video
          src={clip.blob_url}
          poster={clip.thumb_url ?? undefined}
          controls
          playsInline
          preload="metadata"
          className="mx-auto block max-h-[60vh] w-auto max-w-full bg-black object-contain"
        />
      ) : (
        <div className="flex aspect-[9/16] items-center justify-center bg-black text-sm text-zinc-500">
          Video unavailable
        </div>
      )}

      <div className="space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">{clip.streamer_name}</h2>
            <p className="text-xs text-zinc-500">{filename}</p>
          </div>
          <a
            href={`/api/clips/${clip.id}/download`}
            download={filename}
            className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs font-semibold text-zinc-100 transition hover:bg-zinc-800"
          >
            Download MP4
          </a>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Title
            </span>
            <div className="flex items-center gap-2">
              {copied === "title" ? (
                <span role="status" className="text-xs text-emerald-400">
                  Copied
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => copy("title", title)}
                className="rounded-lg border border-zinc-700 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
              >
                Copy title
              </button>
            </div>
          </div>
          <p className="rounded-lg bg-zinc-950 px-3 py-2 text-sm text-zinc-200">
            {title || "—"}
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Description
            </span>
            <div className="flex items-center gap-2">
              {copied === "description" ? (
                <span role="status" className="text-xs text-emerald-400">
                  Copied
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => copy("description", description)}
                className="rounded-lg border border-zinc-700 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
              >
                Copy description
              </button>
            </div>
          </div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-950 px-3 py-2 text-xs text-zinc-300">
            {description || "—"}
          </pre>
        </div>

        <form onSubmit={markPosted} className="space-y-2">
          <label
            htmlFor={`posted-${clip.id}`}
            className="text-xs font-semibold uppercase tracking-wide text-zinc-500"
          >
            YouTube Shorts link
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id={`posted-${clip.id}`}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              type="url"
              inputMode="url"
              autoCapitalize="none"
              autoCorrect="off"
              placeholder="https://youtube.com/shorts/…"
              className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
            />
            <button
              type="submit"
              disabled={pending || !url.trim()}
              className="rounded-lg bg-yellow-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? "Saving…" : "Mark as posted"}
            </button>
          </div>
        </form>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-200"
          >
            {error}
          </p>
        ) : null}

        <a
          href={clip.clip_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block text-xs text-zinc-400 underline decoration-zinc-700 underline-offset-4 transition hover:text-white"
        >
          Original Twitch clip
        </a>
      </div>
    </article>
  );
}
