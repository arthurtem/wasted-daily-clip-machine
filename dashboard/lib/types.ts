export type ClipPrivacy = "public" | "unlisted" | "private";

export type ClipStatus =
  | "new"
  | "downloaded"
  | "rendered"
  | "approved"
  | "uploaded"
  | "rejected"
  | "failed";

export interface QueueClip {
  id: string;
  clip_title: string | null;
  clip_url: string;
  streamer_login: string;
  streamer_name: string;
  view_count: number | null;
  clip_created_at: string | null;
  reddit_score: number | null;
  reddit_url: string | null;
  thumbnail_url: string | null;
  blob_url: string | null;
  thumb_url: string | null;
  yt_title: string | null;
  yt_description: string | null;
  yt_privacy: ClipPrivacy;
}

export interface HistoryClip extends QueueClip {
  status: ClipStatus;
  youtube_video_id: string | null;
  error: string | null;
  updated_at: string | null;
  uploaded_at: string | null;
}

export interface ApprovedClip extends QueueClip {
  updated_at: string | null;
}

export interface ClipForUpdate {
  id: string;
  status: ClipStatus;
  streamer_login: string;
  yt_title: string | null;
  yt_description: string | null;
  yt_privacy: ClipPrivacy;
  blob_url: string | null;
  thumb_url: string | null;
}

export interface Counts {
  new: number;
  rendered: number;
  approved: number;
  uploadedToday: number;
  maxUploadsPerDay: number;
  nextUploadAt: string | null;
  pausedUntil: string | null;
  uploadWindowStart: string;
  uploadWindowEnd: string;
  failed: number;
}

export type UploadMode = "manual" | "api";
