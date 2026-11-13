"use client";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="text-sm text-zinc-400">
        {error.message || "The dashboard could not load this data."}
      </p>
      <button
        type="button"
        onClick={reset}
        className="rounded-xl bg-yellow-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-yellow-300"
      >
        Try again
      </button>
    </main>
  );
}
