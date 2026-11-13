import { NextResponse } from "next/server";

import { isAuthenticated } from "@/lib/auth";
import { getClip, updateClip } from "@/lib/clips";
import { canTransition } from "@/lib/transitions";
import type { ClipPrivacy, ClipStatus } from "@/lib/types";

const ALLOWED_FIELDS = new Set([
  "status",
  "yt_title",
  "yt_description",
  "yt_privacy",
]);
const PRIVACY_VALUES = new Set<ClipPrivacy>([
  "public",
  "unlisted",
  "private",
]);

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!(await isAuthenticated())) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return badRequest("Invalid JSON.");
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    return badRequest("Expected a JSON object.");
  }

  const record = payload as Record<string, unknown>;
  if (Object.keys(record).some((key) => !ALLOWED_FIELDS.has(key))) {
    return badRequest("Unsupported field.");
  }

  const hasStatus = "status" in record;
  const hasTitle = "yt_title" in record;
  const hasDescription = "yt_description" in record;
  const hasPrivacy = "yt_privacy" in record;
  if (!hasStatus && !hasTitle && !hasDescription && !hasPrivacy) {
    return badRequest("Nothing to update.");
  }
  if (hasTitle) {
    if (typeof record.yt_title !== "string") {
      return badRequest("yt_title must be a string.");
    }
    if (record.yt_title.length > 100) {
      return badRequest("yt_title must be at most 100 characters.");
    }
  }
  if (hasDescription && typeof record.yt_description !== "string") {
    return badRequest("yt_description must be a string.");
  }
  if (hasStatus && typeof record.status !== "string") {
    return badRequest("status must be a string.");
  }
  if (hasPrivacy) {
    if (
      typeof record.yt_privacy !== "string" ||
      !PRIVACY_VALUES.has(record.yt_privacy as ClipPrivacy)
    ) {
      return badRequest(
        "yt_privacy must be public, unlisted, or private.",
      );
    }
  }

  let clip;
  try {
    clip = await getClip(id);
  } catch (error) {
    console.error("Failed to load clip", error);
    return NextResponse.json(
      { error: "Database error." },
      { status: 500 },
    );
  }
  if (!clip) {
    return NextResponse.json({ error: "Clip not found." }, { status: 404 });
  }

  let nextStatus: ClipStatus = clip.status;
  if (hasStatus) {
    const requested = record.status as string;
    if (!canTransition(clip.status, requested)) {
      return badRequest(
        `Illegal status change ${clip.status} -> ${requested}.`,
      );
    }
    nextStatus = requested as ClipStatus;
  } else {
    if (
      (hasTitle || hasDescription) &&
      clip.status !== "rendered"
    ) {
      return badRequest("Only rendered clips can be edited.");
    }
    if (
      hasPrivacy &&
      clip.status !== "rendered" &&
      clip.status !== "approved"
    ) {
      return badRequest(
        "Privacy can only be changed on rendered or approved clips.",
      );
    }
  }

  const nextTitle = hasTitle
    ? (record.yt_title as string)
    : clip.yt_title;
  const nextDescription = hasDescription
    ? (record.yt_description as string)
    : clip.yt_description;
  const nextPrivacy = hasPrivacy
    ? (record.yt_privacy as ClipPrivacy)
    : clip.yt_privacy;

  try {
    const updated = await updateClip(id, clip.status, {
      status: nextStatus,
      yt_title: nextTitle,
      yt_description: nextDescription,
      yt_privacy: nextPrivacy,
    });
    if (!updated) {
      return NextResponse.json(
        { error: "Clip changed; refresh and try again." },
        { status: 409 },
      );
    }
  } catch (error) {
    console.error("Failed to update clip", error);
    return NextResponse.json(
      { error: "Database error." },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    status: nextStatus,
    yt_privacy: nextPrivacy,
  });
}
