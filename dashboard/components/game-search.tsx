"use client";

import { useEffect, useState } from "react";

interface GameResult {
  id: string;
  name: string;
}

export default function GameSearch({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [focused, setFocused] = useState(false);
  const [results, setResults] = useState<GameResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const search = value.trim();
    if (!focused || search.length < 2) {
      setResults([]);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/twitch/games?q=${encodeURIComponent(search)}`,
          { signal: controller.signal },
        );
        const data = (await response.json().catch(() => null)) as
          | { results?: GameResult[]; error?: string }
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
  }, [value, focused]);

  function select(game: GameResult) {
    onChange(game.name);
    setFocused(false);
    setResults([]);
  }

  return (
    <div className="relative">
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => window.setTimeout(() => setFocused(false), 150)}
        autoComplete="off"
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
      />
      {focused && value.trim().length >= 2 ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full space-y-1 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-1 shadow-xl">
          {loading ? (
            <p className="px-2 py-1.5 text-xs text-zinc-500">Searching…</p>
          ) : null}
          {error ? (
            <p className="px-2 py-1.5 text-xs text-red-300">{error}</p>
          ) : null}
          {!loading && !error && results.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-zinc-500">
              No games found.
            </p>
          ) : null}
          {results.map((game) => (
            <button
              key={game.id}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(game)}
              className="block w-full rounded-md px-2 py-1.5 text-left text-sm text-zinc-200 transition hover:bg-zinc-800"
            >
              {game.name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
