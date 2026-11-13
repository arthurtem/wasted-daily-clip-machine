"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { formatCount } from "@/lib/format";
import type { QueueClip } from "@/lib/types";

export default function ClipCard({
  clip,
  age,
}: {
  clip: QueueClip;
  age: string;
}) {
  const router = useRouter();
  const [title, setTitle] = useState(clip.yt_title ?? "");
  const [description, setDescription] = useState(clip.yt_description ?? "");
  const [pending, setPending] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(status: "approved" | "rejected") {
    setPending(status);
    setError(null);
    try {
      const payload =
        status === "approved"
          ? { status, yt_title: title, yt_description: description }
          : { status };
      const response = await fetch(`/api/clips/${clip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await response.json().catch(() => null)) as
        | { error?: string }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Request failed.",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <article className="overflow-hidden rounded-3xl border border-zinc-800 bg-zinc-900/60">
      {clip.blob_url ? (
        <video
          src={clip.blob_url}
          poster={clip.thumb_url ?? undefined}
          controls
          playsInline
          preload="metadata"
          className="aspect-[9/16] w-full bg-black object-contain"
        />
      ) : (
        <div className="flex aspect-[9/16] items-center justify-center bg-black text-sm text-zinc-500">
          Video unavailable
        </div>
      )}

      <div className="space-y-4 p-4 sm:p-5">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{clip.streamer_name}</h2>
            {clip.reddit_score != null ? (
              <span className="rounded-full bg-orange-500/15 px-2.5 py-1 text-xs font-semibold text-orange-300">
                Trending on Reddit · {formatCount(clip.reddit_score)}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-zinc-400">
            {formatCount(clip.view_count)} views · {age}
            {" · "}
            <a
              href={clip.clip_url}
              target="_blank"
              rel="noreferrer"
              className="text-zinc-300 underline decoration-zinc-700 underline-offset-4 transition hover:text-white"
            >
              Original clip
            </a>
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <label
              htmlFor={`title-${clip.id}`}
              className="text-sm font-medium"
            >
              YouTube title
            </label>
            <span
              className={`text-xs tabular-nums ${
                title.length > 100 ? "text-red-400" : "text-zinc-500"
              }`}
            >
              {title.length}/100
            </span>
          </div>
          <input
            id={`title-${clip.id}`}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={100}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor={`description-${clip.id}`}
            className="text-sm font-medium"
          >
            YouTube description
          </label>
          <textarea
            id={`description-${clip.id}`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={5}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
          />
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-xl border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-200"
          >
            {error}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => submit("approved")}
            disabled={pending !== null}
            className="flex-1 rounded-xl bg-yellow-400 px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending === "approved" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            onClick={() => submit("rejected")}
            disabled={pending !== null}
            className="flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending === "rejected" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      </div>
    </article>
  );
}
