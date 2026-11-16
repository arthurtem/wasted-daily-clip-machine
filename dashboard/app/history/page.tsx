import Link from "next/link";

import Header from "@/components/header";
import RetryButton from "@/components/retry-button";
import { getSessionRole } from "@/lib/auth";
import { getCounts, getHistory } from "@/lib/clips";
import { formatAge } from "@/lib/format";
import type { HistoryClip } from "@/lib/types";

export const dynamic = "force-dynamic";

function EmptyHistory({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-zinc-800 px-4 py-6 text-sm text-zinc-500">
      {children}
    </p>
  );
}

function UploadedItem({ clip }: { clip: HistoryClip }) {
  return (
    <article className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold">
          {clip.yt_title ?? clip.clip_title ?? clip.id}
        </p>
        <p className="text-xs text-zinc-500">
          {clip.streamer_name} · {formatAge(clip.updated_at)}
        </p>
      </div>
      {clip.youtube_video_id ? (
        <a
          href={`https://youtube.com/shorts/${clip.youtube_video_id}`}
          target="_blank"
          rel="noreferrer"
          className="rounded-xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:bg-zinc-800"
        >
          Open on YouTube
        </a>
      ) : (
        <span className="text-xs text-red-300">Missing video id</span>
      )}
    </article>
  );
}

function RejectedItem({ clip }: { clip: HistoryClip }) {
  return (
    <article className="rounded-2xl border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <p className="truncate text-sm font-semibold">
        {clip.yt_title ?? clip.clip_title ?? clip.id}
      </p>
      <p className="text-xs text-zinc-500">
        {clip.streamer_name} · rejected {formatAge(clip.updated_at)}
        {clip.error ? ` · ${clip.error}` : ""}
      </p>
    </article>
  );
}

function FailedItem({
  clip,
  readOnly,
}: {
  clip: HistoryClip;
  readOnly: boolean;
}) {
  return (
    <article className="space-y-3 rounded-2xl border border-red-950 bg-red-950/20 px-4 py-3">
      <div>
        <p className="truncate text-sm font-semibold">
          {clip.yt_title ?? clip.clip_title ?? clip.id}
        </p>
        <p className="text-xs text-zinc-500">
          {clip.streamer_name} · failed {formatAge(clip.updated_at)}
        </p>
      </div>
      {clip.error ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-black/30 p-3 text-xs text-red-200">
          {clip.error}
        </pre>
      ) : null}
      <RetryButton clipId={clip.id} readOnly={readOnly} />
    </article>
  );
}

export default async function HistoryPage() {
  const [clips, counts, role] = await Promise.all([
    getHistory(),
    getCounts(),
    getSessionRole(),
  ]);
  const readOnly = role !== "owner";
  const uploaded = clips.filter((clip) => clip.status === "uploaded");
  const rejected = clips.filter((clip) => clip.status === "rejected");
  const failed = clips.filter((clip) => clip.status === "failed");

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} title="History" reviewOnly={readOnly} />
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">History</h2>
        <Link
          href="/queue"
          className="text-sm text-zinc-400 underline decoration-zinc-700 underline-offset-4 transition hover:text-white"
        >
          Back to queue
        </Link>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
          Uploaded ({uploaded.length})
        </h3>
        {uploaded.length === 0 ? (
          <EmptyHistory>No uploads yet.</EmptyHistory>
        ) : (
          <div className="grid gap-2">
            {uploaded.map((clip) => (
              <UploadedItem key={clip.id} clip={clip} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
          Rejected ({rejected.length})
        </h3>
        {rejected.length === 0 ? (
          <EmptyHistory>Nothing rejected.</EmptyHistory>
        ) : (
          <div className="grid gap-2">
            {rejected.map((clip) => (
              <RejectedItem key={clip.id} clip={clip} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
          Failed ({failed.length})
        </h3>
        {failed.length === 0 ? (
          <EmptyHistory>No failures.</EmptyHistory>
        ) : (
          <div className="grid gap-2">
            {failed.map((clip) => (
              <FailedItem key={clip.id} clip={clip} readOnly={readOnly} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
