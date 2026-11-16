import "server-only";

import { getSql } from "@/lib/db";
import { nextAllowedUpload, uploadPolicy } from "@/lib/upload-policy";
import { getAutomationState } from "@/lib/automation";
import type {
  ApprovedClip,
  ClipForUpdate,
  ClipPrivacy,
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

function asPrivacy(value: unknown): ClipPrivacy {
  return value === "unlisted" || value === "private" ? value : "public";
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
    reddit_url: asNullableString(row.reddit_url),
    thumbnail_url: asNullableString(row.thumbnail_url),
    blob_url: asNullableString(row.blob_url),
    thumb_url: asNullableString(row.thumb_url),
    yt_title: asNullableString(row.yt_title),
    yt_description: asNullableString(row.yt_description),
    yt_privacy: asPrivacy(row.yt_privacy),
  };
}

function toHistoryClip(row: Row): HistoryClip {
  return {
    ...toQueueClip(row),
    status: asString(row.status) as ClipStatus,
    youtube_video_id: asNullableString(row.youtube_video_id),
    error: asNullableString(row.error),
    updated_at: asIso(row.updated_at),
    uploaded_at: asIso(row.uploaded_at),
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
      yt_description, yt_privacy
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
      yt_description, yt_privacy, updated_at
    FROM clips
    WHERE status = 'approved'
    ORDER BY
      CASE
        WHEN reddit_score IS NOT NULL
         AND clip_created_at >= now() - make_interval(hours => 12)
        THEN 0
        ELSE 1
      END,
      clip_created_at DESC NULLS LAST,
      created_at DESC
  `) as Row[];
  return rows.map(toApprovedClip);
}

export async function getNewClips(): Promise<QueueClip[]> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, clip_title, clip_url, streamer_login, streamer_name, view_count,
      clip_created_at, reddit_score, reddit_url, thumbnail_url, blob_url,
      thumb_url, yt_title, yt_description, yt_privacy
    FROM clips
    WHERE status = 'new'
    ORDER BY clip_created_at DESC NULLS LAST, view_count DESC NULLS LAST
    LIMIT 100
  `) as Row[];
  return rows.map(toQueueClip);
}

export async function getCounts(): Promise<Counts> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      count(*) FILTER (WHERE status = 'new')::int AS new_count,
      count(*) FILTER (WHERE status = 'rendered')::int AS rendered,
      count(*) FILTER (WHERE status = 'approved')::int AS approved,
      count(*) FILTER (
        WHERE status = 'uploaded'
          AND COALESCE(uploaded_at, updated_at) >= now() - interval '24 hours'
      )::int AS uploaded_last_24h,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      max(COALESCE(uploaded_at, updated_at)) FILTER (WHERE status = 'uploaded') AS latest_upload,
      min(COALESCE(uploaded_at, updated_at)) FILTER (
        WHERE status = 'uploaded'
          AND COALESCE(uploaded_at, updated_at) >= now() - interval '24 hours'
      ) AS oldest_upload
    FROM clips
  `) as Row[];
  const row = rows[0] ?? {};
  const automation = await getAutomationState();
  const policy = {
    ...uploadPolicy(),
    maxUploadsPerDay: automation.uploadCap,
  };
  const uploadedLast24h = asNumber(row.uploaded_last_24h) ?? 0;
  const latest = row.latest_upload ? new Date(asIso(row.latest_upload) ?? "") : null;
  const oldest = row.oldest_upload ? new Date(asIso(row.oldest_upload) ?? "") : null;
  const next = nextAllowedUpload(
    new Date(),
    policy,
    latest && !Number.isNaN(latest.getTime()) ? latest : null,
    oldest && !Number.isNaN(oldest.getTime()) ? oldest : null,
    uploadedLast24h,
  );
  return {
    new: asNumber(row.new_count) ?? 0,
    rendered: asNumber(row.rendered) ?? 0,
    approved: asNumber(row.approved) ?? 0,
    uploadedLast24h,
    maxUploadsPerDay: policy.maxUploadsPerDay,
    nextUploadAt: next.toISOString(),
    uploadWindowStart: policy.windowStart,
    uploadWindowEnd: policy.windowEnd,
    failed: asNumber(row.failed) ?? 0,
  };
}

export async function getHistory(): Promise<HistoryClip[]> {  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, clip_title, clip_url, streamer_login, streamer_name, view_count,
      clip_created_at, reddit_score, blob_url, thumb_url, yt_title,
      yt_description, yt_privacy, status, youtube_video_id, error,
      updated_at, uploaded_at
    FROM clips
    WHERE status IN ('uploaded', 'rejected', 'failed')
    ORDER BY COALESCE(uploaded_at, updated_at) DESC NULLS LAST
    LIMIT 200
  `) as Row[];
  return rows.map(toHistoryClip);
}

export async function getClip(id: string): Promise<ClipForUpdate | null> {
  const sql = getSql();
  const rows = (await sql`
    SELECT
      id, status, streamer_login, yt_title, yt_description, yt_privacy,
      blob_url, thumb_url
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
    yt_privacy: asPrivacy(row.yt_privacy),
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
    yt_privacy: ClipPrivacy;
  },
): Promise<boolean> {
  const sql = getSql();
  const rows = (await sql`
    UPDATE clips
    SET
      status = ${values.status},
      yt_title = ${values.yt_title},
      yt_description = ${values.yt_description},
      yt_privacy = ${values.yt_privacy},
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
      uploaded_at = now(),
      updated_at = now()
    WHERE id = ${id} AND status = 'approved'
    RETURNING id
  `) as Row[];
  return rows.length === 1;
}
