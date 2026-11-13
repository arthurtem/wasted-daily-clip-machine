import { randomBytes, timingSafeEqual } from "node:crypto";

import { encrypt } from "@/lib/crypto";

export const STATE_COOKIE = "yt_oauth_state";
export const STATE_MAX_AGE = 60 * 10;
export const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
export const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
export const GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke";
export const YOUTUBE_SCOPES =
  "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly";
export const CALLBACK_PATH = "/api/youtube/callback";

type FetchImpl = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface OAuthConfig {
  clientId: string;
  clientSecret: string;
  appUrl: string;
}

export interface TokenResult {
  accessToken: string;
  refreshToken: string | null;
  scopes: string;
}

export interface ChannelInfo {
  id: string;
  title: string;
}

export interface ConnectionSave {
  channelId: string;
  channelTitle: string;
  refreshTokenEnc: string;
  scopes: string;
}

export type CallbackResult =
  | { kind: "bad_state" }
  | { kind: "no_refresh_token" }
  | { kind: "wrong_channel"; picked: string }
  | { kind: "connected" }
  | { kind: "error"; detail: string };

export class OAuthError extends Error {}

export function oauthConfig(): OAuthConfig {
  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID?.trim();
  const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET?.trim();
  const appUrl = process.env.APP_URL?.trim().replace(/\/+$/, "");
  const missing: string[] = [];
  if (!clientId) {
    missing.push("GOOGLE_OAUTH_CLIENT_ID");
  }
  if (!clientSecret) {
    missing.push("GOOGLE_OAUTH_CLIENT_SECRET");
  }
  if (!appUrl) {
    missing.push("APP_URL");
  }
  if (missing.length > 0) {
    throw new OAuthError(
      `Missing environment variables: ${missing.join(", ")}`,
    );
  }
  return {
    clientId: clientId as string,
    clientSecret: clientSecret as string,
    appUrl: appUrl as string,
  };
}

export function callbackUrl(config: OAuthConfig): string {
  return `${config.appUrl}${CALLBACK_PATH}`;
}

export function createState(): string {
  return randomBytes(32).toString("base64url");
}

export function stateMatches(
  queryState: string | null,
  cookieState: string | null,
): boolean {
  if (!queryState || !cookieState) {
    return false;
  }
  const left = Buffer.from(queryState);
  const right = Buffer.from(cookieState);
  if (left.length !== right.length) {
    return false;
  }
  return timingSafeEqual(left, right);
}

export function buildAuthorizationUrl(
  state: string,
  config: OAuthConfig = oauthConfig(),
): string {
  const url = new URL(GOOGLE_AUTH_URL);
  url.search = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: callbackUrl(config),
    response_type: "code",
    scope: YOUTUBE_SCOPES,
    access_type: "offline",
    prompt: "consent",
    include_granted_scopes: "true",
    state,
  }).toString();
  return url.toString();
}

export async function exchangeCode(
  code: string,
  config: OAuthConfig = oauthConfig(),
  fetchImpl: FetchImpl = fetch,
): Promise<TokenResult> {
  const response = await fetchImpl(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code,
      grant_type: "authorization_code",
      redirect_uri: callbackUrl(config),
    }),
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as
    | Record<string, unknown>
    | null;
  if (!response.ok || !payload) {
    throw new OAuthError(
      `Google token exchange failed (${response.status})`,
    );
  }
  if (typeof payload.error === "string") {
    throw new OAuthError(`Google token exchange failed: ${payload.error}`);
  }
  if (typeof payload.access_token !== "string") {
    throw new OAuthError("Google token response had no access token");
  }
  return {
    accessToken: payload.access_token,
    refreshToken:
      typeof payload.refresh_token === "string"
        ? payload.refresh_token
        : null,
    scopes:
      typeof payload.scope === "string" ? payload.scope : YOUTUBE_SCOPES,
  };
}

export async function fetchChannel(
  accessToken: string,
  fetchImpl: FetchImpl = fetch,
): Promise<ChannelInfo> {
  const url = new URL("https://www.googleapis.com/youtube/v3/channels");
  url.search = new URLSearchParams({
    part: "snippet",
    mine: "true",
  }).toString();
  const response = await fetchImpl(url, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new OAuthError(
      `YouTube channel lookup failed (${response.status})`,
    );
  }
  const payload = (await response.json().catch(() => null)) as
    | { items?: Array<{ id?: string; snippet?: { title?: string } }> }
    | null;
  const item = payload?.items?.[0];
  if (!item?.id || !item.snippet?.title) {
    throw new OAuthError("YouTube returned no channel");
  }
  return { id: item.id, title: item.snippet.title };
}

export async function revokeRefreshToken(
  token: string,
  fetchImpl: FetchImpl = fetch,
): Promise<void> {
  const response = await fetchImpl(GOOGLE_REVOKE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ token }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new OAuthError(`Google revoke failed (${response.status})`);
  }
}

export async function completeOAuthCallback(input: {
  code: string;
  queryState: string | null;
  stateCookie: string | null;
  expectedChannel: string | null;
  fetchImpl?: FetchImpl;
  save: (connection: ConnectionSave) => Promise<void>;
}): Promise<CallbackResult> {
  if (!stateMatches(input.queryState, input.stateCookie)) {
    return { kind: "bad_state" };
  }
  const fetchImpl = input.fetchImpl ?? fetch;

  let token: TokenResult;
  try {
    token = await exchangeCode(input.code, oauthConfig(), fetchImpl);
  } catch (error) {
    return {
      kind: "error",
      detail: error instanceof Error ? error.message : "Token exchange failed",
    };
  }

  if (!token.refreshToken) {
    return { kind: "no_refresh_token" };
  }

  let channel: ChannelInfo;
  try {
    channel = await fetchChannel(token.accessToken, fetchImpl);
  } catch (error) {
    return {
      kind: "error",
      detail:
        error instanceof Error ? error.message : "Channel lookup failed",
    };
  }

  if (input.expectedChannel && channel.title !== input.expectedChannel) {
    try {
      await revokeRefreshToken(token.refreshToken, fetchImpl);
    } catch (error) {
      console.error("Failed to revoke token for wrong channel", error);
    }
    return { kind: "wrong_channel", picked: channel.title };
  }

  try {
    await input.save({
      channelId: channel.id,
      channelTitle: channel.title,
      refreshTokenEnc: encrypt(token.refreshToken),
      scopes: token.scopes,
    });
  } catch (error) {
    try {
      await revokeRefreshToken(token.refreshToken, fetchImpl);
    } catch (revokeError) {
      console.error("Failed to revoke token after save failure", revokeError);
    }
    return {
      kind: "error",
      detail: error instanceof Error ? error.message : "Could not save",
    };
  }

  return { kind: "connected" };
}

export async function disconnectStoredConnection(deps: {
  getConnection: () => Promise<{ refreshTokenEnc: string } | null>;
  deleteConnection: () => Promise<void>;
  decrypt: (value: string) => string;
  revoke: (token: string) => Promise<void>;
}): Promise<void> {
  const connection = await deps.getConnection();
  if (!connection) {
    return;
  }
  try {
    await deps.revoke(deps.decrypt(connection.refreshTokenEnc));
  } catch (error) {
    console.error("Failed to revoke Google token", error);
  }
  await deps.deleteConnection();
}
