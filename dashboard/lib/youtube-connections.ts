import "server-only";

import { getSql } from "@/lib/db";

export interface YouTubeConnection {
  channelId: string;
  channelTitle: string;
  scopes: string[];
  connectedAt: string | null;
}

export interface YouTubeConnectionWithToken extends YouTubeConnection {
  refreshTokenEnc: string;
}

type Row = Record<string, unknown>;

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asIso(value: unknown): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  return typeof value === "string" ? value : null;
}

function toConnection(row: Row): YouTubeConnection {
  const scopes = asString(row.scopes);
  return {
    channelId: asString(row.channel_id),
    channelTitle: asString(row.channel_title),
    scopes: scopes.split(/\s+/).filter(Boolean),
    connectedAt: asIso(row.connected_at),
  };
}

export async function getYouTubeConnection(): Promise<YouTubeConnection | null> {
  const sql = getSql();
  const rows = (await sql`
    SELECT channel_id, channel_title, scopes, connected_at
    FROM youtube_connection
    WHERE id = 1
    LIMIT 1
  `) as Row[];
  return rows[0] ? toConnection(rows[0]) : null;
}

export async function getYouTubeConnectionWithToken(): Promise<YouTubeConnectionWithToken | null> {
  const sql = getSql();
  const rows = (await sql`
    SELECT channel_id, channel_title, scopes, connected_at, refresh_token_enc
    FROM youtube_connection
    WHERE id = 1
    LIMIT 1
  `) as Row[];
  const row = rows[0];
  if (!row) {
    return null;
  }
  return {
    ...toConnection(row),
    refreshTokenEnc: asString(row.refresh_token_enc),
  };
}

export async function hasYouTubeConnection(): Promise<boolean> {
  const sql = getSql();
  const rows = (await sql`
    SELECT 1 FROM youtube_connection WHERE id = 1 LIMIT 1
  `) as Row[];
  return rows.length === 1;
}

export async function upsertYouTubeConnection(input: {
  channelId: string;
  channelTitle: string;
  refreshTokenEnc: string;
  scopes: string;
}): Promise<void> {
  const sql = getSql();
  await sql`
    INSERT INTO youtube_connection (
      id, channel_id, channel_title, refresh_token_enc, scopes, connected_at
    )
    VALUES (1, ${input.channelId}, ${input.channelTitle}, ${input.refreshTokenEnc}, ${input.scopes}, now())
    ON CONFLICT (id) DO UPDATE SET
      channel_id = EXCLUDED.channel_id,
      channel_title = EXCLUDED.channel_title,
      refresh_token_enc = EXCLUDED.refresh_token_enc,
      scopes = EXCLUDED.scopes,
      connected_at = now()
  `;
}

export async function deleteYouTubeConnection(): Promise<void> {
  const sql = getSql();
  await sql`DELETE FROM youtube_connection WHERE id = 1`;
}
