import "server-only";

import { getSql } from "@/lib/db";

export interface YouTubeSettings {
  channelTitle: string | null;
  tokenRef: string | null;
  tokenAddedAt: string | null;
}

type Row = Record<string, unknown>;

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asIso(value: unknown): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  return typeof value === "string" ? value : null;
}

export async function getYouTubeSettings(): Promise<YouTubeSettings | null> {
  const sql = getSql();
  const rows = (await sql`
    SELECT channel_title, token_ref, token_added_at
    FROM youtube_settings
    WHERE id = TRUE
    LIMIT 1
  `) as Row[];
  const row = rows[0];
  if (!row) {
    return null;
  }
  return {
    channelTitle: asNullableString(row.channel_title),
    tokenRef: asNullableString(row.token_ref),
    tokenAddedAt: asIso(row.token_added_at),
  };
}

export async function disconnectYouTube(): Promise<void> {
  const sql = getSql();
  await sql`
    UPDATE youtube_settings
    SET
      channel_title = NULL,
      token_ref = NULL,
      token_added_at = NULL,
      updated_at = now()
    WHERE id = TRUE
  `;
}
