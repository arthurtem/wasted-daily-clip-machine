import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";
import { decrypt } from "@/lib/crypto";
import {
  deleteYouTubeConnection,
  getYouTubeConnectionWithToken,
} from "@/lib/youtube-connections";
import {
  disconnectStoredConnection,
  revokeRefreshToken,
} from "@/lib/youtube-oauth";

export async function POST(request: Request) {
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

  try {
    await disconnectStoredConnection({
      getConnection: getYouTubeConnectionWithToken,
      deleteConnection: deleteYouTubeConnection,
      decrypt,
      revoke: revokeRefreshToken,
    });
  } catch (error) {
    console.error("Failed to disconnect YouTube", error);
    return NextResponse.json(
      { error: "Could not disconnect YouTube." },
      { status: 500 },
    );
  }

  return NextResponse.redirect(
    new URL("/settings?disconnected=1", request.url),
  );
}
