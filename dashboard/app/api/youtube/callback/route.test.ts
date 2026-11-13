import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "yt_oauth_state" ? { value: "correct-state" } : undefined,
    delete: () => undefined,
  }),
}));

vi.mock("@/lib/auth", () => ({
  getSessionRole: async () => "owner",
}));

vi.mock("@/lib/youtube-connections", () => ({
  upsertYouTubeConnection: vi.fn(),
}));

import { upsertYouTubeConnection } from "@/lib/youtube-connections";

import { GET } from "./route";

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("GOOGLE_OAUTH_CLIENT_ID", "client-id");
  vi.stubEnv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret");
  vi.stubEnv("APP_URL", "https://example.com");
  vi.stubEnv("CHANNEL_NAME", "Wasted Daily");
  vi.stubEnv(
    "TOKEN_ENCRYPTION_KEY",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("YouTube OAuth callback", () => {
  it("returns 400 for a state mismatch", async () => {
    const request = new NextRequest(
      "https://example.com/api/youtube/callback?state=wrong&code=abc",
    );

    const response = await GET(request);

    expect(response.status).toBe(400);
    expect(upsertYouTubeConnection).not.toHaveBeenCalled();
  });

  it("revokes and saves nothing for the wrong channel", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("oauth2.googleapis.com/token")) {
        return new Response(
          JSON.stringify({
            access_token: "access",
            refresh_token: "refresh",
            scope: "scope",
          }),
          { status: 200 },
        );
      }
      if (url.includes("/youtube/v3/channels")) {
        return new Response(
          JSON.stringify({
            items: [{ id: "personal", snippet: { title: "Personal" } }],
          }),
          { status: 200 },
        );
      }
      return new Response(null, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest(
      "https://example.com/api/youtube/callback?state=correct-state&code=abc",
    );

    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("error=wrong_channel");
    expect(upsertYouTubeConnection).not.toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("oauth2.googleapis.com/revoke"),
      ),
    ).toBe(true);
  });
});
