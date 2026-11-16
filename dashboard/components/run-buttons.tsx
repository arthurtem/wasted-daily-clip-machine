"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import GameSearch from "@/components/game-search";
import StreamerSearch from "@/components/streamer-search";
import {
  DEFAULT_GAME_NAME,
  STREAMER_OPTIONS,
  type StreamerOption,
} from "@/lib/streamer-options";
import type { UploadMode } from "@/lib/types";

interface RunMessage {
  text: string;
  url?: string;
}

export default function RunButtons({
  uploadMode,
  readOnly = false,
  youtubeConnected = false,
  showPipeline = true,
  defaultGame = DEFAULT_GAME_NAME,
  defaultMinViews = 150,
}: {
  uploadMode: UploadMode;
  readOnly?: boolean;
  youtubeConnected?: boolean;
  showPipeline?: boolean;
  defaultGame?: string;
  defaultMinViews?: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<RunMessage | null>(null);
  const [gameName, setGameName] = useState(defaultGame);
  const [minViews, setMinViews] = useState(defaultMinViews);
  const [selectedStreamers, setSelectedStreamers] = useState<StreamerOption[]>(
    () => [...STREAMER_OPTIONS],
  );

  if (readOnly) {
    return null;
  }

  async function run(workflow: "fetch" | "upload") {
    setBusy(workflow);
    setMessage(null);
    try {
      const payload =
        workflow === "fetch"
          ? {
              game_name: gameName.trim(),
              min_views: minViews,
              streamers: selectedStreamers.map(
                (streamer) => streamer.login,
              ),
            }
          : undefined;
      const response = await fetch(`/api/run/${workflow}`, {
        method: "POST",
        headers: payload ? { "Content-Type": "application/json" } : undefined,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      const data = (await response.json().catch(() => null)) as
        | {
            error?: string;
            run?: { html_url?: string; status?: string };
            workflow_url?: string;
          }
        | null;
      if (!response.ok) {
        throw new Error(data?.error ?? `Request failed (${response.status})`);
      }
      const status = data?.run?.status;
      const fetchSummary =
        workflow === "fetch"
          ? ` for ${gameName.trim()} / min ${minViews} views / ` +
            `${selectedStreamers.map((streamer) => streamer.login).join(", ")}`
          : "";
      setMessage({
        text:
          workflow === "fetch"
            ? `Fetch workflow queued${fetchSummary}${status ? ` (${status})` : ""}.`
            : `Upload workflow queued${status ? ` (${status})` : ""}.`,
        url: data?.run?.html_url ?? data?.workflow_url,
      });
      window.setTimeout(() => router.refresh(), 3000);
    } catch (error) {
      setMessage({
        text:
          error instanceof Error
            ? error.message
            : "Could not queue workflow.",
      });
    } finally {
      setBusy(null);
    }
  }

  const canFetch =
    selectedStreamers.length > 0 &&
    gameName.trim().length > 0 &&
    Number.isInteger(minViews) &&
    minViews >= 0;

  return (
    <div className="space-y-3">
      {showPipeline ? (
        <div className="space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem]">
            <div className="space-y-1.5">
              <label
                htmlFor="fetch-game"
                className="text-xs font-semibold uppercase tracking-wide text-zinc-500"
              >
                Game
              </label>
              <GameSearch
                id="fetch-game"
                value={gameName}
                onChange={setGameName}
              />
            </div>
            <div className="space-y-1.5">
              <label
                htmlFor="fetch-min-views"
                className="text-xs font-semibold uppercase tracking-wide text-zinc-500"
              >
                Min views
              </label>
              <input
                id="fetch-min-views"
                type="number"
                min={0}
                step={1}
                value={minViews}
                onChange={(event) => setMinViews(Number(event.target.value))}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
              />
            </div>
          </div>
          <p className="text-[11px] text-zinc-500">
            Until GTA VI launches on 19 November 2026, choose Grand Theft Auto
            V. Testing may need min views 0.
          </p>
          {gameName.trim().toLowerCase() === "grand theft auto v" &&
          minViews > 0 ? (
            <p className="text-xs text-amber-300">
              GTA V clips usually have under 200 views. Set min views to 0 to
              fetch them.
            </p>
          ) : null}

          <StreamerSearch
            selected={selectedStreamers}
            onChange={setSelectedStreamers}
          />

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => run("fetch")}
              disabled={busy !== null || !canFetch}
              className="rounded-xl bg-yellow-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "fetch" ? "Starting…" : "Fetch clips"}
            </button>
            {uploadMode === "api" && youtubeConnected ? (
              <button
                type="button"
                onClick={() => run("upload")}
                disabled={busy !== null}
                className="rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === "upload" ? "Starting…" : "Upload approved now"}
              </button>
            ) : null}
          </div>
          {!canFetch ? (
            <p className="text-xs text-amber-300">
              Select at least one streamer and a game.
            </p>
          ) : null}
        </div>
      ) : uploadMode === "api" && youtubeConnected ? (
        <button
          type="button"
          onClick={() => run("upload")}
          disabled={busy !== null}
          className="rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === "upload" ? "Starting…" : "Upload approved now"}
        </button>
      ) : null}

      {uploadMode === "manual" && youtubeConnected ? (
        <p className="text-xs text-zinc-500">
          Automatic upload is off. Set <code>UPLOAD_MODE=api</code> in the
          environment and restart/redeploy to show the upload button.
        </p>
      ) : null}

      {message ? (
        <p role="status" className="text-sm text-zinc-400">
          {message.text}{" "}
          {message.url ? (
            <a
              href={message.url}
              target="_blank"
              rel="noreferrer"
              className="text-zinc-200 underline decoration-zinc-600 underline-offset-4"
            >
              View run
            </a>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
