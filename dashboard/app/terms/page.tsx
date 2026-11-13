import type { Metadata } from "next";

import {
  LAST_UPDATED,
  YOUTUBE_COMMUNITY_URL,
  YOUTUBE_TOS_URL,
  contactEmail,
  contactEmailHref,
  ownerName,
} from "@/lib/legal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Terms of Service — Wasted Daily Clip Machine",
};

const linkClass =
  "text-zinc-200 underline decoration-zinc-600 underline-offset-4";

function Email() {
  const email = contactEmail();
  const href = contactEmailHref();
  if (href) {
    return (
      <a href={href} className={linkClass}>
        {email}
      </a>
    );
  }
  return <span className="text-zinc-200">{email}</span>;
}

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-yellow-400">
        Wasted Daily Clip Machine
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">
        Terms of Service
      </h1>
      <p className="mt-2 text-sm text-zinc-500">Last updated: {LAST_UPDATED}</p>

      <div className="mt-8 space-y-7 text-sm leading-7 text-zinc-400">
        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            Who may use it
          </h2>
          <p className="mt-1">
            These terms apply between {ownerName()} and the owner of this
            private tool. It may be used only by its owner, to upload edited
            Shorts to the owner&apos;s own YouTube channel.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            YouTube rules
          </h2>
          <p className="mt-1">
            All uploads must follow the{" "}
            <a
              href={YOUTUBE_TOS_URL}
              target="_blank"
              rel="noreferrer"
              className={linkClass}
            >
              YouTube Terms of Service
            </a>{" "}
            and the{" "}
            <a
              href={YOUTUBE_COMMUNITY_URL}
              target="_blank"
              rel="noreferrer"
              className={linkClass}
            >
              YouTube Community Guidelines
            </a>
            .
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            Provided as-is
          </h2>
          <p className="mt-1">
            The tool is provided as-is, without warranties of any kind. The
            owner is responsible for reviewing every Short before it is posted.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            Content ownership
          </h2>
          <p className="mt-1">
            Content belongs to its original creators. Every Short credits and
            links the streamer whose Twitch clip is used.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">Contact</h2>
          <p className="mt-1">
            Questions about these terms can be sent to <Email />.
          </p>
        </section>
      </div>
    </main>
  );
}
