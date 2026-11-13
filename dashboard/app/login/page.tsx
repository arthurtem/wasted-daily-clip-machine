import type { Metadata } from "next";

import LoginForm from "./login-form";

export const metadata: Metadata = {
  title: "Sign in — Wasted Daily",
};

export default function LoginPage() {
  return (
    <main className="flex min-h-[70vh] items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm rounded-3xl border border-zinc-800 bg-zinc-900/60 p-6 shadow-2xl shadow-black/40 sm:p-8">
        <LoginForm />
      </div>
    </main>
  );
}
