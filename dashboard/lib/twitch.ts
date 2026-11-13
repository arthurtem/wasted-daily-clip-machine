import "server-only";

const TOKEN_URL = "https://id.twitch.tv/oauth2/token";
const HELIX_BASE = "https://api.twitch.tv/helix";

export interface TwitchChannelResult {
  login: string;
  name: string;
  isLive: boolean;
  gameName: string | null;
  thumbnailUrl: string | null;
}

export interface TwitchGameResult {
  id: string;
  name: string;
  boxArtUrl: string | null;
}

export class TwitchSearchError extends Error {}

let tokenCache: { token: string; expiresAt: number } | null = null;

function credentials(): { clientId: string; clientSecret: string } {
  const clientId = process.env.TWITCH_CLIENT_ID?.trim();
  const clientSecret = process.env.TWITCH_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) {
    throw new TwitchSearchError(
      "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET are not set",
    );
  }
  return { clientId, clientSecret };
}

async function getToken(): Promise<string> {
  const now = Date.now();
  if (tokenCache && now < tokenCache.expiresAt) {
    return tokenCache.token;
  }
  const config = credentials();
  let response: Response;
  try {
    response = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: config.clientId,
        client_secret: config.clientSecret,
        grant_type: "client_credentials",
      }),
      cache: "no-store",
    });
  } catch (error) {
    throw new TwitchSearchError("Could not reach Twitch token service");
  }
  const payload = (await response.json().catch(() => null)) as
    | { access_token?: string; expires_in?: number; message?: string }
    | null;
  if (!response.ok || !payload?.access_token) {
    throw new TwitchSearchError(
      `Twitch token request failed (${response.status})`,
    );
  }
  const expiresIn = Number(payload.expires_in ?? 3600);
  tokenCache = {
    token: payload.access_token,
    expiresAt: now + Math.max(0, expiresIn - 60) * 1000,
  };
  return tokenCache.token;
}

async function helix(
  path: string,
  params: Record<string, string>,
  retry = true,
): Promise<Record<string, unknown>> {
  const config = credentials();
  const token = await getToken();
  const url = new URL(`${HELIX_BASE}${path}`);
  url.search = new URLSearchParams(params).toString();
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        "Client-Id": config.clientId,
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });
  } catch (error) {
    throw new TwitchSearchError("Could not reach Twitch");
  }
  if (response.status === 401 && retry) {
    tokenCache = null;
    return helix(path, params, false);
  }
  const payload = (await response.json().catch(() => null)) as
    | Record<string, unknown>
    | null;
  if (!response.ok || !payload) {
    throw new TwitchSearchError(`Twitch request failed (${response.status})`);
  }
  return payload;
}

export async function searchChannels(
  query: string,
): Promise<TwitchChannelResult[]> {
  const payload = await helix("/search/channels", {
    query,
    first: "12",
  });
  const rows = Array.isArray(payload.data) ? payload.data : [];
  const seen = new Set<string>();
  const results: TwitchChannelResult[] = [];
  for (const row of rows) {
    const item = row as Record<string, unknown>;
    const login = typeof item.broadcaster_login === "string"
      ? item.broadcaster_login
      : "";
    if (!login || seen.has(login)) {
      continue;
    }
    seen.add(login);
    results.push({
      login,
      name:
        typeof item.display_name === "string" ? item.display_name : login,
      isLive: item.is_live === true,
      gameName:
        typeof item.game_name === "string" && item.game_name
          ? item.game_name
          : null,
      thumbnailUrl:
        typeof item.thumbnail_url === "string"
          ? item.thumbnail_url
          : null,
    });
  }
  return results;
}

export async function searchGames(query: string): Promise<TwitchGameResult[]> {
  const payload = await helix("/search/categories", {
    query,
    first: "12",
  });
  const rows = Array.isArray(payload.data) ? payload.data : [];
  const results: TwitchGameResult[] = [];
  for (const row of rows) {
    const item = row as Record<string, unknown>;
    const id = typeof item.id === "string" ? item.id : "";
    const name = typeof item.name === "string" ? item.name : "";
    if (!id || !name) {
      continue;
    }
    results.push({
      id,
      name,
      boxArtUrl:
        typeof item.box_art_url === "string" ? item.box_art_url : null,
    });
  }
  return results;
}
