"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import VisibilitySelect from "@/components/visibility-select";
import UploadCompliance from "@/components/upload-compliance";
import { formatCount } from "@/lib/format";
import type { ClipPrivacy, QueueClip } from "@/lib/types";

export default function ClipCard({
  clip,
  age,
  channelName,
  readOnly = false,
}: {
  clip: QueueClip;
  age: string;
  channelName: string;
  readOnly?: boolean;
}) {
  const router = useRouter();
  const [title, setTitle] = useState(clip.yt_title ?? "");
  const [description, setDescription] = useState(clip.yt_description ?? "");
  const [privacy, setPrivacy] = useState<ClipPrivacy>(clip.yt_privacy);
  const [pending, setPending] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(status: "approved" | "rejected") {
    if (readOnly) {
      return;
    }
    setPending(status);
    setError(null);
    try {
      const payload =
        status === "approved"
          ? {
              status,
              yt_title: title,
              yt_description: description,
              yt_privacy: privacy,
            }
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

      <div className="space-y-3 p-3 sm:p-4">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <h2 className="text-base font-semibold">{clip.streamer_name}</h2>
            {clip.reddit_score != null ? (
              <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[11px] font-semibold text-orange-300">
                Trending on Reddit · {formatCount(clip.reddit_score)}
              </span>
            ) : null}
          </div>
          <p className="text-xs text-zinc-400">
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

        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <label
              htmlFor={`title-${clip.id}`}
              className="text-xs font-medium"
            >
              YouTube title
            </label>
            <span
              className={`text-[11px] tabular-nums ${
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
            readOnly={readOnly}
            maxLength={100}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-xs outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor={`description-${clip.id}`}
            className="text-xs font-medium"
          >
            YouTube description
          </label>
          <textarea
            id={`description-${clip.id}`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            readOnly={readOnly}
            rows={3}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-xs outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor={`privacy-${clip.id}`}
            className="text-xs font-medium"
          >
            YouTube visibility
          </label>
          <VisibilitySelect
            id={`privacy-${clip.id}`}
            value={privacy}
            onChange={setPrivacy}
            disabled={readOnly || pending !== null}
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

        <UploadCompliance channelName={channelName} />

        {readOnly ? (
          <p className="text-[11px] text-amber-300">
            Review-only access: approval is disabled.
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => submit("approved")}
            disabled={readOnly || pending !== null}
            className="flex-1 rounded-lg bg-yellow-400 px-3 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending === "approved" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            onClick={() => submit("rejected")}
            disabled={readOnly || pending !== null}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending === "rejected" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      </div>
    </article>
  );
}
