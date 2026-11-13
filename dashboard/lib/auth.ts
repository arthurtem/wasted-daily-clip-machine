import "server-only";

import { cookies } from "next/headers";

import {
  SESSION_COOKIE,
  type SessionRole,
  verifySessionToken,
} from "@/lib/session";

export async function getSessionRole(): Promise<SessionRole | null> {
  const store = await cookies();
  return verifySessionToken(store.get(SESSION_COOKIE)?.value);
}

export async function isAuthenticated(): Promise<boolean> {
  return (await getSessionRole()) !== null;
}
