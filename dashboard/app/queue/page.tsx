import ClipCard from "@/components/clip-card";
import Header from "@/components/header";
import RunButtons from "@/components/run-buttons";
import { getCounts, getQueue } from "@/lib/clips";
import { formatAge } from "@/lib/format";
import type { UploadMode } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  const [clips, counts] = await Promise.all([getQueue(), getCounts()]);
  const uploadMode: UploadMode =
    process.env.UPLOAD_MODE === "api" ? "api" : "manual";
  const channelName = process.env.CHANNEL_NAME?.trim() || "YouTube";

  return (
    <main className="mx-auto max-w-[1700px] space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} />
      <RunButtons uploadMode={uploadMode} />

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
            />
          ))}
        </section>
      )}
    </main>
  );
}
