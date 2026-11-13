import Header from "@/components/header";
import SettingsDisconnect from "@/components/settings-disconnect";
import { getCounts } from "@/lib/clips";
import { GOOGLE_PERMISSIONS_URL } from "@/lib/legal";
import { getYouTubeSettings } from "@/lib/settings";

export const dynamic = "force-dynamic";

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown";
  }
  return date.toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function SettingsPage() {
  const [counts, settings] = await Promise.all([
    getCounts(),
    getYouTubeSettings(),
  ]);
  const connected = Boolean(settings?.channelTitle || settings?.tokenRef);

  return (
    <main className="mx-auto max-w-3xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} title="Settings" />

      <section className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div>
          <h2 className="text-base font-semibold">YouTube channel</h2>
          <p className="mt-1 text-sm text-zinc-400">
            The worker records the connected channel in the database when the
            YouTube API is set up.
          </p>
        </div>

        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-zinc-950 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-zinc-500">
              Connected channel
            </dt>
            <dd className="mt-1 text-sm text-zinc-100">
              {settings?.channelTitle ?? "Not connected"}
            </dd>
          </div>
          <div className="rounded-xl bg-zinc-950 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-zinc-500">
              Token added
            </dt>
            <dd className="mt-1 text-sm text-zinc-100">
              {settings?.tokenAddedAt
                ? formatTimestamp(settings.tokenAddedAt)
                : "—"}
            </dd>
          </div>
        </dl>

        {connected ? <SettingsDisconnect /> : null}

        <div className="space-y-2 border-t border-zinc-800 pt-4 text-sm leading-6 text-zinc-400">
          <p>
            Disconnecting clears the stored channel and token reference from
            the database. To fully revoke access, also visit{" "}
            <a
              href={GOOGLE_PERMISSIONS_URL}
              target="_blank"
              rel="noreferrer"
              className="text-zinc-200 underline decoration-zinc-600 underline-offset-4"
            >
              https://myaccount.google.com/permissions
            </a>{" "}
            and remove the <code>YT_REFRESH_TOKEN</code> GitHub secret.
          </p>
        </div>
      </section>
    </main>
  );
}
