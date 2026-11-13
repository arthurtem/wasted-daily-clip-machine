import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";

const WORKFLOWS = new Set(["pipeline", "upload"]);

export async function POST(
  _request: Request,
  context: { params: Promise<{ workflow: string }> },
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

  const { workflow } = await context.params;
  if (!WORKFLOWS.has(workflow)) {
    return NextResponse.json(
      { error: "Unknown workflow." },
      { status: 400 },
    );
  }

  if (
    workflow === "upload" &&
    (process.env.UPLOAD_MODE ?? "manual") !== "api"
  ) {
    return NextResponse.json(
      { error: "Uploads are in manual mode." },
      { status: 403 },
    );
  }

  const token = process.env.GITHUB_TOKEN?.trim();
  const owner = process.env.GITHUB_OWNER?.trim();
  const repo = process.env.GITHUB_REPO?.trim();
  if (!token || !owner || !repo) {
    return NextResponse.json(
      { error: "GitHub dispatch is not configured." },
      { status: 500 },
    );
  }

  const endpoint = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}.yml/dispatches`;

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch (error) {
    console.error("GitHub dispatch failed", error);
    return NextResponse.json(
      { error: "Could not reach GitHub." },
      { status: 502 },
    );
  }

  if (!response.ok) {
    const detail = await response.text();
    let hint = "";
    if (response.status === 401) {
      hint =
        "GitHub rejected GITHUB_TOKEN. Use a valid fine-grained token with Actions read/write on this repo. ";
    } else if (response.status === 403) {
      hint =
        "GitHub denied the request. Check the token has Actions read/write permission. ";
    } else if (response.status === 404) {
      hint =
        "GitHub could not find the repo or workflow. Check GITHUB_OWNER/GITHUB_REPO and that the workflow exists on main. ";
    }
    return NextResponse.json(
      {
        error: `${hint}GitHub ${response.status}: ${detail.slice(0, 300)}`,
      },
      { status: 502 },
    );
  }

  return NextResponse.json({ ok: true });
}
