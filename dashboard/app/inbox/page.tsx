import Header from "@/components/header";
import InboxBoard from "@/components/inbox-board";
import { getSessionRole } from "@/lib/auth";
import { getCounts, getNewClips } from "@/lib/clips";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const [clips, counts, role] = await Promise.all([
    getNewClips(),
    getCounts(),
    getSessionRole(),
  ]);
  const readOnly = role !== "owner";

  return (
    <main className="mx-auto max-w-[1700px] space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} title="Import inbox" reviewOnly={readOnly} />
      <InboxBoard clips={clips} readOnly={readOnly} />
    </main>
  );
}
