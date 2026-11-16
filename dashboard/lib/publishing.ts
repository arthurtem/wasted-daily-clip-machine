import "server-only";

import { getApprovedQueue, getCounts, getHistory, getNewClips, getQueue } from "@/lib/clips";
import type { ApprovedClip, Counts, HistoryClip, QueueClip } from "@/lib/types";

export interface ScheduledClip extends ApprovedClip {
  scheduled_at: string | null;
  after_cap: boolean;
}

export interface PublishingPlan {
  approved: ScheduledClip[];
  live: HistoryClip[];
  incoming: QueueClip[];
  rendered: QueueClip[];
  counts: Counts;
}

const SLOT_MS = 10 * 60 * 1000;

export async function getPublishingPlan(): Promise<PublishingPlan> {
  const [approved, counts, history, incoming, rendered] = await Promise.all([
    getApprovedQueue(),
    getCounts(),
    getHistory(),
    getNewClips(),
    getQueue(),
  ]);

  const next = counts.nextUploadAt ? new Date(counts.nextUploadAt) : null;
  const remaining = Math.max(
    0,
    counts.maxUploadsPerDay - counts.uploadedLast24h,
  );
  const scheduled = approved.map<ScheduledClip>((clip, index) => {
    const afterCap = index >= remaining;
    return {
      ...clip,
      after_cap: afterCap,
      scheduled_at:
        afterCap || !next
          ? null
          : new Date(next.getTime() + index * SLOT_MS).toISOString(),
    };
  });

  return {
    approved: scheduled,
    live: history.filter((clip) => clip.status === "uploaded").slice(0, 20),
    incoming: incoming.slice(0, 20),
    rendered: rendered.slice(0, 20),
    counts,
  };
}
