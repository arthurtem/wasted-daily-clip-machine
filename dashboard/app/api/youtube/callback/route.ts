import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { getSessionRole } from "@/lib/auth";
import {
  STATE_COOKIE,
  completeOAuthCallback,
  oauthConfig,
  stateMatches,
} from "@/lib/youtube-oauth";
import { upsertYouTubeConnection } from "@/lib/youtube-connections";

function settingsUrl(appUrl: string, params: Record<string, string>): URL {
  const url = new URL("/settings", appUrl);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return url;
}

export async function GET(request: NextRequest) {
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

  let appUrl: string;
  try {
    appUrl = oauthConfig().appUrl;
  } catch (error) {
    console.error("YouTube OAuth is not configured", error);
    return NextResponse.json(
      { error: "YouTube OAuth is not configured." },
      { status: 500 },
    );
  }

  const store = await cookies();
  const stateCookie = store.get(STATE_COOKIE)?.value ?? null;
  store.delete(STATE_COOKIE);

  const params = request.nextUrl.searchParams;
  const queryState = params.get("state");
  if (!stateMatches(queryState, stateCookie)) {
    return NextResponse.json(
      { error: "OAuth state mismatch." },
      { status: 400 },
    );
  }

  const googleError = params.get("error");
  if (googleError) {
    return NextResponse.redirect(
      settingsUrl(appUrl, { error: googleError }),
    );
  }

  const code = params.get("code");
  if (!code) {
    return NextResponse.redirect(
      settingsUrl(appUrl, { error: "missing_code" }),
    );
  }

  const result = await completeOAuthCallback({
    code,
    queryState,
    stateCookie,
    expectedChannel: process.env.CHANNEL_NAME?.trim() || null,
    save: upsertYouTubeConnection,
  });

  switch (result.kind) {
    case "bad_state":
      return NextResponse.json(
        { error: "OAuth state mismatch." },
        { status: 400 },
      );
    case "no_refresh_token":
      return NextResponse.redirect(
        settingsUrl(appUrl, { error: "no_refresh_token" }),
      );
    case "wrong_channel":
      return NextResponse.redirect(
        settingsUrl(appUrl, {
          error: "wrong_channel",
          picked: result.picked,
        }),
      );
    case "connected":
      return NextResponse.redirect(
        settingsUrl(appUrl, { connected: "1" }),
      );
    case "error":
      return NextResponse.redirect(
        settingsUrl(appUrl, {
          error: "oauth_failed",
          detail: result.detail,
        }),
      );
  }
}
