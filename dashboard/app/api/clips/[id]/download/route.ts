import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";
import { getClip } from "@/lib/clips";

function safeFilename(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]/g, "-");
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!(await getSessionRole())) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const clip = await getClip(id);
  if (!clip) {
    return NextResponse.json({ error: "Clip not found." }, { status: 404 });
  }
  if (!clip.blob_url) {
    return NextResponse.json(
      { error: "Clip has no video file." },
      { status: 404 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(clip.blob_url, { cache: "no-store" });
  } catch (error) {
    console.error("Failed to fetch blob for download", error);
    return NextResponse.json(
      { error: "Could not fetch the video." },
      { status: 502 },
    );
  }
  if (!upstream.ok || !upstream.body) {
    return NextResponse.json(
      { error: `Blob returned ${upstream.status}.` },
      { status: 502 },
    );
  }

  const filename = safeFilename(
    `${clip.streamer_login}-${clip.id}.mp4`,
  );
  const headers = new Headers({
    "Content-Type": upstream.headers.get("content-type") ?? "video/mp4",
    "Content-Disposition": `attachment; filename="${filename}"`,
    "Cache-Control": "no-store",
  });
  const contentLength = upstream.headers.get("content-length");
  if (contentLength) {
    headers.set("Content-Length", contentLength);
  }

  return new Response(upstream.body, { status: 200, headers });
}
