import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { decrypt } from "./crypto";
import {
  buildAuthorizationUrl,
  completeOAuthCallback,
  disconnectStoredConnection,
  stateMatches,
} from "./youtube-oauth";

const KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";
const CONFIG = {
  clientId: "client-id",
  clientSecret: "client-secret",
  appUrl: "https://example.com",
};

beforeEach(() => {
  vi.stubEnv("TOKEN_ENCRYPTION_KEY", KEY);
  vi.stubEnv("GOOGLE_OAUTH_CLIENT_ID", CONFIG.clientId);
  vi.stubEnv("GOOGLE_OAUTH_CLIENT_SECRET", CONFIG.clientSecret);
  vi.stubEnv("APP_URL", CONFIG.appUrl);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("OAuth URL and state", () => {
  it("builds the Google authorization URL", () => {
    const url = new URL(buildAuthorizationUrl("state-123", CONFIG));
    expect(url.searchParams.get("client_id")).toBe(CONFIG.clientId);
    expect(url.searchParams.get("redirect_uri")).toBe(
      "https://example.com/api/youtube/callback",
    );
    expect(url.searchParams.get("access_type")).toBe("offline");
    expect(url.searchParams.get("prompt")).toBe("consent");
    expect(url.searchParams.get("state")).toBe("state-123");
    expect(url.searchParams.get("scope")).toContain("youtube.upload");
  });

  it("compares states safely", () => {
    expect(stateMatches("abc", "abc")).toBe(true);
    expect(stateMatches("abc", "abd")).toBe(false);
    expect(stateMatches(null, "abc")).toBe(false);
  });
});

describe("completeOAuthCallback", () => {
  const tokenResponse = (refresh: string | null) =>
    new Response(
      JSON.stringify({
        access_token: "access",
        refresh_token: refresh ?? undefined,
        scope: "scope-a scope-b",
      }),
      { status: 200 },
    );

  const channelResponse = (title: string) =>
    new Response(
      JSON.stringify({
        items: [{ id: "channel-id", snippet: { title } }],
      }),
      { status: 200 },
    );

  it("does not save on a state mismatch", async () => {
    const save = vi.fn();
    const fetchImpl = vi.fn();

    const result = await completeOAuthCallback({
      code: "code",
      queryState: "wrong",
      stateCookie: "right",
      expectedChannel: "Wasted Daily",
      fetchImpl,
      save,
    });

    expect(result).toEqual({ kind: "bad_state" });
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it("revokes and does not save for the wrong channel", async () => {
    const save = vi.fn();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/token")) {
        return tokenResponse("refresh-token");
      }
      if (url.includes("/channels")) {
        return channelResponse("Personal Channel");
      }
      return new Response(null, { status: 200 });
    });

    const result = await completeOAuthCallback({
      code: "code",
      queryState: "state",
      stateCookie: "state",
      expectedChannel: "Wasted Daily",
      fetchImpl,
      save,
    });

    expect(result).toEqual({
      kind: "wrong_channel",
      picked: "Personal Channel",
    });
    expect(save).not.toHaveBeenCalled();
    expect(
      fetchImpl.mock.calls.some(([url]) =>
        String(url).includes("/revoke"),
      ),
    ).toBe(true);
  });

  it("saves an encrypted refresh token for the right channel", async () => {
    const save = vi.fn();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/token")) {
        return tokenResponse("refresh-token");
      }
      return channelResponse("Wasted Daily");
    });

    const result = await completeOAuthCallback({
      code: "code",
      queryState: "state",
      stateCookie: "state",
      expectedChannel: "Wasted Daily",
      fetchImpl,
      save,
    });

    expect(result).toEqual({ kind: "connected" });
    expect(save).toHaveBeenCalledOnce();
    const saved = save.mock.calls[0][0];
    expect(saved.channelId).toBe("channel-id");
    expect(saved.channelTitle).toBe("Wasted Daily");
    expect(decrypt(saved.refreshTokenEnc)).toBe("refresh-token");
  });

  it("does not save without a refresh token", async () => {
    const save = vi.fn();
    const fetchImpl = vi.fn(async () => tokenResponse(null));

    const result = await completeOAuthCallback({
      code: "code",
      queryState: "state",
      stateCookie: "state",
      expectedChannel: "Wasted Daily",
      fetchImpl,
      save,
    });

    expect(result).toEqual({ kind: "no_refresh_token" });
    expect(save).not.toHaveBeenCalled();
  });
});

describe("disconnectStoredConnection", () => {
  it("deletes the row even when revoke fails", async () => {
    const deleteConnection = vi.fn(async () => undefined);

    await disconnectStoredConnection({
      getConnection: async () => ({ refreshTokenEnc: "encrypted" }),
      deleteConnection,
      decrypt: () => "refresh-token",
      revoke: async () => {
        throw new Error("Google unavailable");
      },
    });

    expect(deleteConnection).toHaveBeenCalledOnce();
  });
});
