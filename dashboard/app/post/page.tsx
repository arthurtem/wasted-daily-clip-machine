import Header from "@/components/header";
import PostCard from "@/components/post-card";
import RunButtons from "@/components/run-buttons";
import YouTubeNoticeBanner from "@/components/youtube-notice-banner";
import { getSessionRole } from "@/lib/auth";
import { getApprovedQueue, getCounts } from "@/lib/clips";
import { hasYouTubeConnection } from "@/lib/youtube-connections";

export const dynamic = "force-dynamic";

export default async function PostPage() {
  const [clips, counts, role] = await Promise.all([
    getApprovedQueue(),
    getCounts(),
    getSessionRole(),
  ]);
  const readOnly = role !== "owner";
  const uploadMode = process.env.UPLOAD_MODE === "api" ? "api" : "manual";
  const youtubeConnected = await hasYouTubeConnection();
  const channelName = process.env.CHANNEL_NAME?.trim() || "YouTube";

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header
        counts={counts}
        title="Post to YouTube"
        reviewOnly={readOnly}
      />

      <p className="text-sm text-zinc-400">
        {uploadMode === "api"
          ? "Approved clips can be uploaded to YouTube by the worker."
          : "Download the MP4, post it as a public Short, then paste the YouTube link and mark it posted."}
      </p>
      <RunButtons
        uploadMode={uploadMode}
        readOnly={readOnly}
        youtubeConnected={youtubeConnected}
        showPipeline={false}
      />
      {uploadMode === "api" && !youtubeConnected ? (
        <YouTubeNoticeBanner />
      ) : null}

      {clips.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-zinc-800 bg-zinc-900/40 px-6 py-16 text-center">
          <h2 className="text-lg font-semibold">Nothing to post</h2>
          <p className="mt-2 text-sm text-zinc-400">
            Approved clips will appear here, oldest approval first.
          </p>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {clips.map((clip) => (
            <PostCard
              key={clip.id}
              clip={clip}
              channelName={channelName}
              readOnly={readOnly}
            />
          ))}
        </section>
      )}
    </main>
  );
}
