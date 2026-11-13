import Link from "next/link";
import { redirect } from "next/navigation";

import { isAuthenticated } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function LandingPage() {
  if (await isAuthenticated()) {
    redirect("/queue");
  }

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center px-6 py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-yellow-400">
        Wasted Daily
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
        Wasted Daily Clip Machine
      </h1>
      <p className="mt-5 max-w-2xl text-base leading-7 text-zinc-400">
        Wasted Daily Clip Machine is an internal tool that turns Twitch clips
        into YouTube Shorts for the Wasted Daily YouTube channel. Every upload
        is reviewed and approved by a human before it is posted.
      </p>
      <div className="mt-8">
        <Link
          href="/login"
          className="inline-flex rounded-xl bg-yellow-400 px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300"
        >
          Log in
        </Link>
      </div>
    </main>
  );
}
