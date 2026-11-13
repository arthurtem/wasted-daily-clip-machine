import Header from "@/components/header";
import PostCard from "@/components/post-card";
import { getApprovedQueue, getCounts } from "@/lib/clips";

export const dynamic = "force-dynamic";

export default async function PostPage() {
  const [clips, counts] = await Promise.all([
    getApprovedQueue(),
    getCounts(),
  ]);

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} title="Post to YouTube" />

      <p className="text-sm text-zinc-400">
        Download the MP4, post it as a public Short, then paste the YouTube
        link and mark it posted.
      </p>

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
            <PostCard key={clip.id} clip={clip} />
          ))}
        </section>
      )}
    </main>
  );
}
