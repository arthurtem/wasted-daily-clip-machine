import Header from "@/components/header";
import { getSessionRole } from "@/lib/auth";
import { getCounts } from "@/lib/clips";
import { GOOGLE_PERMISSIONS_URL } from "@/lib/links";
import { getYouTubeConnection } from "@/lib/youtube-connections";

export const dynamic = "force-dynamic";

type SearchParams = Promise<
  Record<string, string | string[] | undefined>
>;

function param(
  params: Record<string, string | string[] | undefined>,
  key: string,
): string | null {
  const value = params[key];
  if (typeof value === "string") {
    return value;
  }
  return Array.isArray(value) ? (value[0] ?? null) : null;
}

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

function SettingsMessage({
  tone,
  children,
}: {
  tone: "success" | "error";
  children: React.ReactNode;
}) {
  const classes =
    tone === "success"
      ? "border-emerald-900 bg-emerald-950/40 text-emerald-200"
      : "border-red-900 bg-red-950/40 text-red-200";
  return (
    <p role={tone === "error" ? "alert" : "status"} className={`rounded-xl border px-4 py-3 text-sm ${classes}`}>
      {children}
    </p>
  );
}

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const [counts, connection, role, params] = await Promise.all([
    getCounts(),
    getYouTubeConnection(),
    getSessionRole(),
    searchParams,
  ]);
  const readOnly = role !== "owner";

  const error = param(params, "error");
  const picked = param(params, "picked");
  const detail = param(params, "detail");
  const justConnected = param(params, "connected") === "1";
  const justDisconnected = param(params, "disconnected") === "1";

  return (
    <main className="mx-auto max-w-3xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <Header counts={counts} title="Settings" reviewOnly={readOnly} />

      {justConnected ? (
        <SettingsMessage tone="success">
          YouTube is connected.
        </SettingsMessage>
      ) : null}
      {justDisconnected ? (
        <SettingsMessage tone="success">
          YouTube was disconnected.
        </SettingsMessage>
      ) : null}
      {error === "wrong_channel" ? (
        <SettingsMessage tone="error">
          You picked {picked ?? "another channel"}. Please connect the Wasted
          Daily channel.
        </SettingsMessage>
      ) : null}
      {error === "no_refresh_token" ? (
        <SettingsMessage tone="error">
          Remove the app at{" "}
          <a
            href={GOOGLE_PERMISSIONS_URL}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-4"
          >
            myaccount.google.com/permissions
          </a>{" "}
          and connect again.
        </SettingsMessage>
      ) : null}
      {error && error !== "wrong_channel" && error !== "no_refresh_token" ? (
        <SettingsMessage tone="error">
          YouTube connection failed
          {detail ? `: ${detail}` : error === "access_denied" ? ": access denied." : "."}
        </SettingsMessage>
      ) : null}

      <section className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div>
          <h2 className="text-base font-semibold">YouTube channel</h2>
          <p className="mt-1 text-sm text-zinc-400">
            This app uploads only to the connected channel.
          </p>
        </div>

        {connection ? (
          <>
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-zinc-950 px-4 py-3">
                <dt className="text-xs uppercase tracking-wide text-zinc-500">
                  Channel
                </dt>
                <dd className="mt-1 text-sm text-zinc-100">
                  {connection.channelTitle}
                </dd>
              </div>
              <div className="rounded-xl bg-zinc-950 px-4 py-3">
                <dt className="text-xs uppercase tracking-wide text-zinc-500">
                  Channel ID
                </dt>
                <dd className="mt-1 break-all text-sm text-zinc-100">
                  {connection.channelId}
                </dd>
              </div>
              <div className="rounded-xl bg-zinc-950 px-4 py-3">
                <dt className="text-xs uppercase tracking-wide text-zinc-500">
                  Connected
                </dt>
                <dd className="mt-1 text-sm text-zinc-100">
                  {formatTimestamp(connection.connectedAt)}
                </dd>
              </div>
              <div className="rounded-xl bg-zinc-950 px-4 py-3">
                <dt className="text-xs uppercase tracking-wide text-zinc-500">
                  Scopes
                </dt>
                <dd className="mt-1 text-xs text-zinc-300">
                  {connection.scopes.join(" ")}
                </dd>
              </div>
            </dl>

            {readOnly ? (
              <p className="text-[11px] text-amber-300">
                Review-only access: disconnecting is disabled.
              </p>
            ) : (
              <form action="/api/youtube/disconnect" method="post">
                <button
                  type="submit"
                  className="rounded-xl border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm font-semibold text-red-200 transition hover:bg-red-950/70"
                >
                  Disconnect
                </button>
              </form>
            )}

            <p className="border-t border-zinc-800 pt-4 text-sm leading-6 text-zinc-400">
              To revoke access outside the app, visit{" "}
              <a
                href={GOOGLE_PERMISSIONS_URL}
                target="_blank"
                rel="noreferrer"
                className="text-zinc-200 underline decoration-zinc-600 underline-offset-4"
              >
                https://myaccount.google.com/permissions
              </a>
              .
            </p>
          </>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-zinc-400">
              Asks permission to upload videos and read your channel name. Pick
              the Wasted Daily channel when Google asks.
            </p>
            {readOnly ? (
              <p className="text-[11px] text-amber-300">
                Review-only access: connecting is disabled.
              </p>
            ) : (
              <a
                href="/api/youtube/connect"
                className="inline-flex rounded-xl bg-yellow-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300"
              >
                Connect YouTube channel
              </a>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
