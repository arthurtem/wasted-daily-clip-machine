import Link from "next/link";

import { YOUTUBE_TOS_URL } from "@/lib/legal";

export default function Footer() {
  return (
    <footer className="border-t border-zinc-800 px-4 py-8 text-xs text-zinc-500">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 text-center sm:flex-row sm:justify-between sm:text-left">
        <p className="font-medium text-zinc-400">Wasted Daily Clip Machine</p>
        <nav className="flex items-center gap-4">
          <Link
            href="/privacy"
            className="underline decoration-zinc-700 underline-offset-4 transition hover:text-zinc-300"
          >
            Privacy Policy
          </Link>
          <Link
            href="/terms"
            className="underline decoration-zinc-700 underline-offset-4 transition hover:text-zinc-300"
          >
            Terms of Service
          </Link>
        </nav>
        <p>
          This app uses YouTube API Services{" "}
          <a
            href={YOUTUBE_TOS_URL}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-zinc-700 underline-offset-4 transition hover:text-zinc-300"
          >
            (YouTube Terms of Service)
          </a>
        </p>
      </div>
    </footer>
  );
}
