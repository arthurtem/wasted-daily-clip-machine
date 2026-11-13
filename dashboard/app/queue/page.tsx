import ClipCard from "@/components/clip-card";
import Header from "@/components/header";
import RunButtons from "@/components/run-buttons";
import WorkflowRuns from "@/components/workflow-runs";
import YouTubeNoticeBanner from "@/components/youtube-notice-banner";
import { getSessionRole } from "@/lib/auth";
import { getCounts, getQueue } from "@/lib/clips";
import { hasYouTubeConnection } from "@/lib/youtube-connections";
import { formatAge } from "@/lib/format";
import type { UploadMode } from "@/lib/types";
import { getRecentWorkflowRuns } from "@/lib/workflow-runs";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  const [clips, counts, role, youtubeConnected, runs] = await Promise.all([
    getQueue(),
    getCounts(),
    getSessionRole(),
    hasYouTubeConnection(),
    getRecentWorkflowRuns(),
  ]);
  const readOnly = role !== "owner";
  const uploadMode: UploadMode =
    process.env.UPLOAD_MODE === "api" ? "api" : "manual";
  const channelName = process.env.CHANNEL_NAME?.trim() || "YouTube";

  return (
    <main className="mx-auto max-w-[1700px] space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} reviewOnly={readOnly} />
      <RunButtons
        uploadMode={uploadMode}
        readOnly={readOnly}
        youtubeConnected={youtubeConnected}
      />
      {uploadMode === "api" && !youtubeConnected ? <YouTubeNoticeBanner /> : null}
      <WorkflowRuns runs={runs} />

      {clips.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-zinc-800 bg-zinc-900/40 px-6 py-16 text-center">
          <h2 className="text-lg font-semibold">No clips waiting</h2>
          <p className="mt-2 text-sm text-zinc-400">
            Rendered Shorts will appear here for review.
          </p>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {clips.map((clip) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              age={formatAge(clip.clip_created_at)}
              channelName={channelName}
              readOnly={readOnly}
            />
          ))}
        </section>
      )}
    </main>
  );
}
