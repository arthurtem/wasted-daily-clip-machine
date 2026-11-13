"use server";

import { createHash, timingSafeEqual } from "node:crypto";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  SESSION_COOKIE,
  SESSION_MAX_AGE,
  createSessionToken,
} from "@/lib/session";

export interface LoginState {
  error?: string;
}

function passwordsMatch(input: string, expected: string): boolean {
  const inputHash = createHash("sha256").update(input).digest();
  const expectedHash = createHash("sha256").update(expected).digest();
  return timingSafeEqual(inputHash, expectedHash);
}

export async function login(
  _previous: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    return { error: "DASHBOARD_PASSWORD is not configured." };
  }

  const password = formData.get("password");
  if (typeof password !== "string" || !passwordsMatch(password, expected)) {
    return { error: "Wrong password." };
  }

  let token: string;
  try {
    token = await createSessionToken();
  } catch {
    return { error: "SESSION_SECRET is not configured." };
  }

  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });

  redirect("/");
}
