import Header from "@/components/header";
import { getSessionRole } from "@/lib/auth";
import { getPublishingPlan } from "@/lib/publishing";
import { formatCount } from "@/lib/format";

export const dynamic = "force-dynamic";

function when(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Brussels",
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function clipTitle(clip: { yt_title: string | null; clip_title: string | null; id: string }): string {
  return clip.yt_title ?? clip.clip_title ?? clip.id;
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-zinc-800 px-4 py-5 text-sm text-zinc-500">
      {children}
    </p>
  );
}

export default async function PostPage() {
  const [plan, role] = await Promise.all([
    getPublishingPlan(),
    getSessionRole(),
  ]);
  const readOnly = role !== "owner";

  return (
    <main className="mx-auto max-w-6xl space-y-7 px-4 py-6 sm:px-6 lg:py-8">
      <Header
        counts={plan.counts}
        title="Publishing schedule"
        reviewOnly={readOnly}
      />

      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 px-4 py-3 text-sm text-zinc-400">
        <span className="text-zinc-200">
          {plan.counts.uploadedToday} / {plan.counts.maxUploadsPerDay}
        </span>{" "}
        uploaded today · one clip every 10 minutes · next upload{" "}
        <span className="text-zinc-200">
          {when(plan.counts.nextUploadAt)}
        </span>
        . All clips are public.
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">Going live next</h2>
          <span className="text-xs text-zinc-500">
            {plan.approved.length} approved
          </span>
        </div>
        {plan.approved.length === 0 ? (
          <Empty>No approved clips waiting.</Empty>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-800">
            {plan.approved.map((clip, index) => (
              <div
                key={clip.id}
                className="flex items-center justify-between gap-4 border-b border-zinc-800/80 bg-zinc-900/40 px-4 py-3 last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {clip.streamer_name} · {clipTitle(clip)}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {clip.clip_title ?? clip.id}
                    {clip.reddit_score != null
                      ? ` · Reddit ${formatCount(clip.reddit_score)}`
                      : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs font-medium text-zinc-200">
                    {clip.after_cap
                      ? "After daily cap"
                      : when(clip.scheduled_at)}
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-500">
                    {clip.after_cap
                      ? "waiting for the 24h window"
                      : `slot ${index + 1}`}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">Already live</h2>
          <span className="text-xs text-zinc-500">
            {plan.live.length} recent
          </span>
        </div>
        {plan.live.length === 0 ? (
          <Empty>No uploads yet.</Empty>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-800">
            {plan.live.map((clip) => (
              <div
                key={clip.id}
                className="flex items-center justify-between gap-4 border-b border-zinc-800/80 bg-zinc-900/40 px-4 py-3 last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {clipTitle(clip)}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {clip.streamer_name}
                    {clip.youtube_video_id ? " · public Short" : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs font-medium text-zinc-200">
                    {when(clip.uploaded_at ?? clip.updated_at)}
                  </p>
                  {clip.youtube_video_id ? (
                    <a
                      href={`https://youtube.com/shorts/${clip.youtube_video_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 inline-block text-[11px] text-zinc-400 underline decoration-zinc-700 underline-offset-4 hover:text-white"
                    >
                      YouTube
                    </a>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">Coming in</h2>
          <span className="text-xs text-zinc-500">
            {plan.incoming.length} new · {plan.rendered.length} rendered
          </span>
        </div>
        {plan.incoming.length === 0 && plan.rendered.length === 0 ? (
          <Empty>Nothing waiting for the pipeline.</Empty>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-800">
            {[...plan.incoming, ...plan.rendered].map((clip) => (
              <div
                key={clip.id}
                className="flex items-center justify-between gap-4 border-b border-zinc-800/80 bg-zinc-900/40 px-4 py-3 last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {clip.streamer_name} · {clipTitle(clip)}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {formatCount(clip.view_count)} views ·{" "}
                    {clip.reddit_score != null
                      ? `Reddit ${formatCount(clip.reddit_score)}`
                      : "Twitch"}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs font-medium text-zinc-200">
                    {plan.incoming.some((item) => item.id === clip.id)
                      ? "Waiting for render"
                      : "Rendered"}
                  </p>
                  {clip.clip_url ? (
                    <a
                      href={clip.clip_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 inline-block text-[11px] text-zinc-400 underline decoration-zinc-700 underline-offset-4 hover:text-white"
                    >
                      Original
                    </a>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
