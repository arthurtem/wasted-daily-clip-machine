import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";
import { deleteClipBlobs } from "@/lib/blob";
import { getClip, markPosted } from "@/lib/clips";
import { parseYouTubeVideoId } from "@/lib/youtube-url";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
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

  const { id } = await context.params;

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON." }, { status: 400 });
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    return NextResponse.json(
      { error: "Expected a JSON object." },
      { status: 400 },
    );
  }

  const record = payload as Record<string, unknown>;
  if (Object.keys(record).some((key) => key !== "url")) {
    return NextResponse.json(
      { error: "Unsupported field." },
      { status: 400 },
    );
  }
  if (typeof record.url !== "string") {
    return NextResponse.json(
      { error: "url must be a string." },
      { status: 400 },
    );
  }

  const videoId = parseYouTubeVideoId(record.url);
  if (!videoId) {
    return NextResponse.json(
      { error: "Could not find a YouTube video id in that URL." },
      { status: 400 },
    );
  }

  let clip;
  try {
    clip = await getClip(id);
  } catch (error) {
    console.error("Failed to load clip for posting", error);
    return NextResponse.json(
      { error: "Database error." },
      { status: 500 },
    );
  }
  if (!clip) {
    return NextResponse.json({ error: "Clip not found." }, { status: 404 });
  }
  if (clip.status !== "approved") {
    return NextResponse.json(
      { error: `Clip is ${clip.status}, not approved.` },
      { status: 400 },
    );
  }

  try {
    const updated = await markPosted(id, videoId);
    if (!updated) {
      return NextResponse.json(
        { error: "Clip changed; refresh and try again." },
        { status: 409 },
      );
    }
  } catch (error) {
    console.error("Failed to mark clip posted", error);
    return NextResponse.json(
      { error: "Database error." },
      { status: 500 },
    );
  }

  const failures = await deleteClipBlobs([clip.blob_url, clip.thumb_url]);
  if (failures.length > 0) {
    console.error("Posted clip but could not delete blobs", failures);
    return NextResponse.json({
      ok: true,
      youtube_video_id: videoId,
      warning: "Posted, but Blob cleanup failed.",
    });
  }

  return NextResponse.json({ ok: true, youtube_video_id: videoId });
}
