import { NextResponse } from "next/server";

import { isAuthenticated } from "@/lib/auth";
import { disconnectYouTube } from "@/lib/settings";

export async function POST() {
  if (!(await isAuthenticated())) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  try {
    await disconnectYouTube();
  } catch (error) {
    console.error("Failed to disconnect YouTube", error);
    return NextResponse.json(
      { error: "Database error." },
      { status: 500 },
    );
  }

  return NextResponse.json({ ok: true });
}
