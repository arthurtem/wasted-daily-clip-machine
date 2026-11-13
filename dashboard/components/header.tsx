import Link from "next/link";

import CountsRow from "@/components/counts-row";
import type { Counts } from "@/lib/types";

export default function Header({ counts }: { counts?: Counts }) {
  return (
    <header className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-yellow-400">
            Wasted Daily
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Review queue
          </h1>
        </div>
        <nav className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-900/60 p-1 text-sm">
          <Link
            href="/"
            className="rounded-full px-4 py-2 font-medium text-zinc-200 transition hover:bg-zinc-800"
          >
            Queue
          </Link>
          <Link
            href="/history"
            className="rounded-full px-4 py-2 font-medium text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200"
          >
            History
          </Link>
        </nav>
      </div>
      {counts ? <CountsRow counts={counts} /> : null}
    </header>
  );
}
