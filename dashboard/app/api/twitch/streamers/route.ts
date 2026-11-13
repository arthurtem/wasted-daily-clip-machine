import { NextResponse, type NextRequest } from "next/server";

import { getSessionRole } from "@/lib/auth";
import { searchChannels, TwitchSearchError } from "@/lib/twitch";

export async function GET(request: NextRequest) {
  if (!(await getSessionRole())) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (query.length < 2) {
    return NextResponse.json(
      { error: "Search needs at least 2 characters." },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json({ results: await searchChannels(query) });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof TwitchSearchError
            ? error.message
            : "Twitch search failed.",
      },
      { status: 502 },
    );
  }
}
