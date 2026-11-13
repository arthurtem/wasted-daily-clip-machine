import "server-only";

import { getSql } from "@/lib/db";
import type {
  ApprovedClip,
  ClipForUpdate,
  ClipStatus,
  Counts,
  HistoryClip,
  QueueClip,
} from "@/lib/types";

type Row = Record<string, unknown>;

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  if (value == null) {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asIso(value: unknown): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  return typeof value === "string" ? value : null;
}

function toQueueClip(row: Row): QueueClip {
  return {
    id: asString(row.id),
    clip_title: asNullableString(row.clip_title),
    clip_url: asString(row.clip_url),
    streamer_login: asString(row.streamer_login),
    streamer_name: asString(row.streamer_name),
    view_count: asNumber(row.view_count),
    clip_created_at: asIso(row.clip_created_at),
    reddit_score: asNumber(row.reddit_score),
    blob_url: asNullableString(row.blob_url),
    thumb_url: asNullableString(row.thumb_url),
    yt_title: asNullableString(row.yt_title),
    yt_description: asNullableString(row.yt_description),
  };
}

function toHistoryClip(row: Row): HistoryClip {
  return {
    ...toQueueClip(row),
    status: asString(row.status) as ClipStatus,
    youtube_video_id: asNullableString(row.youtube_video_id),
    error: asNullableString(row.error),
    updated_at: asIso(row.updated_at),
  };
}

function toApprovedClip(row: Row): ApprovedClip {
  return {
    ...toQueueClip(row),
    updated_at: asIso(row.updated_at),
  };
}

export async function getQueue(): Promise<QueueClip[]> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, clip_title, clip_url, streamer_login, streamer_name, view_count,
      clip_created_at, reddit_score, blob_url, thumb_url, yt_title,
      yt_description
    FROM clips
    WHERE status = 'rendered'
    ORDER BY
      reddit_score DESC NULLS LAST,
      view_count DESC NULLS LAST,
      clip_created_at DESC NULLS LAST
  `) as Row[];
  return rows.map(toQueueClip);
}


export async function getApprovedQueue(): Promise<ApprovedClip[]> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, clip_title, clip_url, streamer_login, streamer_name, view_count,
      clip_created_at, reddit_score, blob_url, thumb_url, yt_title,
      yt_description, updated_at
    FROM clips
    WHERE status = 'approved'
    ORDER BY updated_at ASC NULLS FIRST
  `) as Row[];
  return rows.map(toApprovedClip);
}

export async function getCounts(): Promise<Counts> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      count(*) FILTER (WHERE status = 'rendered')::int AS rendered,
      count(*) FILTER (WHERE status = 'approved')::int AS approved,
      count(*) FILTER (
        WHERE status = 'uploaded' AND updated_at >= date_trunc('day', now())
      )::int AS uploaded_today,
      count(*) FILTER (WHERE status = 'failed')::int AS failed
    FROM clips
  `) as Row[];
  const row = rows[0] ?? {};
  return {
    rendered: asNumber(row.rendered) ?? 0,
    approved: asNumber(row.approved) ?? 0,
    uploadedToday: asNumber(row.uploaded_today) ?? 0,
    failed: asNumber(row.failed) ?? 0,
  };
}

export async function getHistory(): Promise<HistoryClip[]> {  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, clip_title, clip_url, streamer_login, streamer_name, view_count,
      clip_created_at, reddit_score, blob_url, thumb_url, yt_title,
      yt_description, status, youtube_video_id, error, updated_at
    FROM clips
    WHERE status IN ('uploaded', 'rejected', 'failed')
    ORDER BY updated_at DESC NULLS LAST
    LIMIT 200
  `) as Row[];
  return rows.map(toHistoryClip);
}

export async function getClip(id: string): Promise<ClipForUpdate | null> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, status, streamer_login, yt_title, yt_description, blob_url,
      thumb_url
    FROM clips
    WHERE id = ${id}
    LIMIT 1
  `) as Row[];
  const row = rows[0];
  if (!row) {
    return null;
  }
  return {
    id: asString(row.id),
    status: asString(row.status) as ClipStatus,
    streamer_login: asString(row.streamer_login),
    yt_title: asNullableString(row.yt_title),
    yt_description: asNullableString(row.yt_description),
    blob_url: asNullableString(row.blob_url),
    thumb_url: asNullableString(row.thumb_url),
  };
}

export async function updateClip(
  id: string,
  expectedStatus: ClipStatus,
  values: {
    status: ClipStatus;
    yt_title: string | null;
    yt_description: string | null;
  },
): Promise<boolean> {
  const sql = getSql();
  const rows = (await sql`
    UPDATE clips
    SET
      status = ${values.status},
      yt_title = ${values.yt_title},
      yt_description = ${values.yt_description},
      updated_at = now()
    WHERE id = ${id} AND status = ${expectedStatus}
    RETURNING id
  `) as Row[];
  return rows.length === 1;
}

export async function markPosted(
  id: string,
  youtubeVideoId: string,
): Promise<boolean> {
  const sql = getSql();
  const rows = (await sql`
    UPDATE clips
    SET
      status = 'uploaded',
      youtube_video_id = ${youtubeVideoId},
      updated_at = now()
    WHERE id = ${id} AND status = 'approved'
    RETURNING id
  `) as Row[];
  return rows.length === 1;
}
