import Link from "next/link";

export default function YouTubeNoticeBanner() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-900 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
      <p>YouTube is not connected</p>
      <Link
        href="/settings"
        className="rounded-lg border border-amber-800 px-3 py-1.5 text-xs font-semibold text-amber-100 transition hover:bg-amber-900/40"
      >
        Connect in Settings
      </Link>
    </div>
  );
}
