"use client";

import { useActionState } from "react";

import { login, type LoginState } from "./actions";

const initialState: LoginState = {};

export default function LoginForm() {
  const [state, formAction, pending] = useActionState(login, initialState);

  return (
    <form action={formAction} className="w-full max-w-sm space-y-5">
      <div className="space-y-2 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-yellow-400">
          Wasted Daily
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">Review dashboard</h1>
        <p className="text-sm text-zinc-400">
          Enter the dashboard password to review Shorts.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="password" className="block text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          className="w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-base outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30"
        />
      </div>

      {state.error ? (
        <p
          role="alert"
          className="rounded-xl border border-red-900 bg-red-950/60 px-4 py-3 text-sm text-red-200"
        >
          {state.error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-xl bg-yellow-400 px-4 py-3 text-base font-semibold text-zinc-950 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
