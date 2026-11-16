import type { ClipStatus } from "@/lib/types";

export const ALLOWED_TRANSITIONS: Record<string, readonly ClipStatus[]> = {
  new: ["rejected"],
  rendered: ["approved", "rejected"],
  failed: ["new"],
};

export function canTransition(from: string, to: string): boolean {
  return (ALLOWED_TRANSITIONS[from] ?? []).includes(to as ClipStatus);
}
