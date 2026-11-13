"use client";

import { useEffect, useState } from "react";

import type { StreamerOption } from "@/lib/streamer-options";

interface ChannelResult extends StreamerOption {
  isLive: boolean;
  gameName: string | null;
}

export default function StreamerSearch({
  selected,
  onChange,
}: {
  selected: StreamerOption[];
  onChange: (streamers: StreamerOption[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ChannelResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const search = query.trim();
    if (search.length < 2) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/twitch/streamers?q=${encodeURIComponent(search)}`,
          { signal: controller.signal },
        );
        const data = (await response.json().catch(() => null)) as
          | { results?: ChannelResult[]; error?: string }
          | null;
        if (!response.ok) {
          throw new Error(data?.error ?? `Search failed (${response.status})`);
        }
        setResults(data?.results ?? []);
      } catch (searchError) {
        if (
          searchError instanceof Error &&
          searchError.name !== "AbortError"
        ) {
          setError(searchError.message);
          setResults([]);
        }
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  function add(result: ChannelResult) {
    if (selected.some((streamer) => streamer.login === result.login)) {
      return;
    }
    onChange([
      ...selected,
      { login: result.login, name: result.name },
    ]);
    setQuery("");
    setResults([]);
  }

  function remove(login: string) {
    onChange(selected.filter((streamer) => streamer.login !== login));
  }

  return (
    <div className="space-y-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Streamers
      </span>
      <div className="flex flex-wrap gap-1.5">
        {selected.map((streamer) => (
          <span
            key={streamer.login}
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs text-zinc-200"
          >
            {streamer.name}
            <span className="text-zinc-500">@{streamer.login}</span>
            <button
              type="button"
              onClick={() => remove(streamer.login)}
              aria-label={`Remove ${streamer.name}`}
              className="text-zinc-500 transition hover:text-red-300"
            >
              ×
            </button>
          </span>
        ))}
        {selected.length === 0 ? (
          <span className="text-xs text-zinc-500">
            No streamers selected.
          </span>
        ) : null}
      </div>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search Twitch streamers…"
        autoComplete="off"
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
      />
      {query.trim().length >= 2 ? (
        <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-1">
          {loading ? (
            <p className="px-2 py-1.5 text-xs text-zinc-500">Searching…</p>
          ) : null}
          {error ? (
            <p className="px-2 py-1.5 text-xs text-red-300">{error}</p>
          ) : null}
          {!loading && !error && results.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-zinc-500">
              No streamers found.
            </p>
          ) : null}
          {results.map((result) => {
            const already = selected.some(
              (streamer) => streamer.login === result.login,
            );
            return (
              <button
                key={result.login}
                type="button"
                onClick={() => add(result)}
                disabled={already}
                className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-zinc-800 disabled:cursor-default disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-zinc-200">
                    {result.name}
                  </span>
                  <span className="text-xs text-zinc-500">
                    @{result.login}
                    {result.gameName ? ` · ${result.gameName}` : ""}
                  </span>
                </span>
                <span className="flex items-center gap-1.5 text-xs">
                  {result.isLive ? (
                    <span className="rounded-full bg-red-500/15 px-2 py-0.5 font-semibold text-red-300">
                      Live
                    </span>
                  ) : null}
                  <span className="text-zinc-500">
                    {already ? "Selected" : "Add"}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
