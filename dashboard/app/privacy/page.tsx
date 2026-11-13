import type { Metadata } from "next";

import {
  GOOGLE_PERMISSIONS_URL,
  GOOGLE_PRIVACY_URL,
  LAST_UPDATED,
  YOUTUBE_TOS_URL,
  contactEmail,
  contactEmailHref,
  ownerName,
} from "@/lib/legal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Privacy Policy — Wasted Daily Clip Machine",
};

function Email() {
  const email = contactEmail();
  const href = contactEmailHref();
  if (href) {
    return (
      <a
        href={href}
        className="text-zinc-200 underline decoration-zinc-600 underline-offset-4"
      >
        {email}
      </a>
    );
  }
  return <span className="text-zinc-200">{email}</span>;
}

const linkClass =
  "text-zinc-200 underline decoration-zinc-600 underline-offset-4";

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-yellow-400">
        Wasted Daily Clip Machine
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">
        Privacy Policy
      </h1>
      <p className="mt-2 text-sm text-zinc-500">Last updated: {LAST_UPDATED}</p>

      <div className="mt-8 space-y-7 text-sm leading-7 text-zinc-400">
        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            Who runs this app
          </h2>
          <p className="mt-1">
            Wasted Daily Clip Machine is run by {ownerName()}. You can contact
            the owner at <Email />.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            What this app is
          </h2>
          <p className="mt-1">
            It is a private tool used by its owner to upload edited Shorts to
            the owner&apos;s own YouTube channel. It is not a public video
            platform and does not accept accounts from other people.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            YouTube API Services
          </h2>
          <p className="mt-1">
            This app uses YouTube API Services. By using it, the owner agrees
            to the{" "}
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
              href={GOOGLE_PRIVACY_URL}
              target="_blank"
              rel="noreferrer"
              className={linkClass}
            >
              Google Privacy Policy
            </a>
            .
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            What data it accesses
          </h2>
          <p className="mt-1">
            Through the YouTube API, it requests only permission to upload
            videos and to read the channel name of the owner&apos;s own
            channel. It does not read viewer data, comments, subscribers, or
            analytics.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            What it stores
          </h2>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            <li>
              Public Twitch clip information: title, URL, view count, and
              streamer name.
            </li>
            <li>Rendered video files until they are posted.</li>
            <li>The YouTube video ID of each posted Short.</li>
            <li>
              An OAuth refresh token, stored as an encrypted secret in the
              services that run the app.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            How long data is kept
          </h2>
          <p className="mt-1">
            Video files are deleted from storage right after posting. Rejected
            or failed video files are deleted within 3 days. Clip records are
            kept for the channel&apos;s history and can be deleted on request.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">Sharing</h2>
          <p className="mt-1">
            Data is not sold or shared, except with the service providers that
            run the app: Vercel, Neon, GitHub, and Google.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">
            Revoking access and deletion
          </h2>
          <p className="mt-1">
            You can revoke this app&apos;s Google access at{" "}
            <a
              href={GOOGLE_PERMISSIONS_URL}
              target="_blank"
              rel="noreferrer"
              className={linkClass}
            >
              https://myaccount.google.com/permissions
            </a>
            . To request deletion of stored clip records, contact <Email />.
            When access is revoked, the stored refresh token is deleted.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-100">Cookies</h2>
          <p className="mt-1">
            The app uses one login session cookie. It does not use tracking or
            analytics cookies.
          </p>
        </section>
      </div>
    </main>
  );
}
