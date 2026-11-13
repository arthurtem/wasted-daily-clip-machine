import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";
import {
  STATE_COOKIE,
  STATE_MAX_AGE,
  buildAuthorizationUrl,
  createState,
  oauthConfig,
} from "@/lib/youtube-oauth";

export async function GET() {
  const role = await getSessionRole();
  if (!role) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (role !== "owner") {
    return NextResponse.json(
      { error: "Review-only access." },
      { status: 403 },
    );
  }

  let url: string;
  try {
    url = buildAuthorizationUrl(createState());
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Unknown configuration error";
    console.error("YouTube OAuth is not configured", detail);
    return NextResponse.json(
      { error: `YouTube OAuth is not configured. ${detail}` },
      { status: 500 },
    );
  }

  const state = new URL(url).searchParams.get("state");
  if (!state) {
    return NextResponse.json(
      { error: "Could not create OAuth state." },
      { status: 500 },
    );
  }

  const store = await cookies();
  store.set(STATE_COOKIE, state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: STATE_MAX_AGE,
  });

  return NextResponse.redirect(url);
}
