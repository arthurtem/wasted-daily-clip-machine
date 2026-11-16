import { NextResponse } from "next/server";

import { getSessionRole } from "@/lib/auth";

const WORKFLOWS = new Set(["fetch", "render", "upload"]);
const GITHUB_HEADERS = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
};

interface WorkflowRunInfo {
  id: number;
  run_number: number;
  status: string;
  conclusion: string | null;
  html_url: string;
  created_at: string | null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function findWorkflowRun(
  token: string,
  owner: string,
  repo: string,
  workflow: string,
  dispatchedAt: number,
): Promise<WorkflowRunInfo | null> {
  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}.yml/runs?per_page=10`;
  for (const delay of [400, 1000, 2000]) {
    await sleep(delay);
    try {
      const response = await fetch(url, {
        headers: { ...GITHUB_HEADERS, Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) {
        continue;
      }
      const payload = (await response.json().catch(() => null)) as
        | { workflow_runs?: WorkflowRunInfo[] }
        | null;
      const runs = payload?.workflow_runs ?? [];
      const match = runs.find((run) => {
        if (!run.created_at) {
          return false;
        }
        return Date.parse(run.created_at) >= dispatchedAt - 10_000;
      });
      if (match) {
        return match;
      }
    } catch (error) {
      console.error("Could not look up the workflow run", error);
    }
  }
  return null;
}

export async function POST(
  request: Request,
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
    (process.env.UPLOAD_MODE ?? "manual").trim() !== "api"
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

  let inputs: Record<string, string> | undefined;
  if (workflow === "fetch" || workflow === "render") {
    let raw: unknown = null;
    try {
      raw = await request.json();
    } catch {
      raw = null;
    }
    if (raw !== null) {
      if (typeof raw !== "object" || Array.isArray(raw)) {
        return NextResponse.json(
          { error: "Expected a JSON object." },
          { status: 400 },
        );
      }
      const record = raw as Record<string, unknown>;
      inputs = {};
      if (workflow === "fetch") {
        const game = record.game_name;
        if (game !== undefined) {
          if (typeof game !== "string" || game.length > 100) {
            return NextResponse.json(
              { error: "game_name must be a string of at most 100 chars." },
              { status: 400 },
            );
          }
        }
        const minViews = record.min_views;
        if (minViews !== undefined) {
          if (
            typeof minViews !== "number" ||
            !Number.isInteger(minViews) ||
            minViews < 0
          ) {
            return NextResponse.json(
              { error: "min_views must be a non-negative integer." },
              { status: 400 },
            );
          }
        }
        const streamers = record.streamers;
        if (streamers !== undefined) {
          if (
            !Array.isArray(streamers) ||
            streamers.some(
              (login) => typeof login !== "string" || login.length > 50,
            )
          ) {
            return NextResponse.json(
              { error: "streamers must be an array of Twitch logins." },
              { status: 400 },
            );
          }
        }
        if (typeof game === "string" && game.trim()) {
          inputs.game_name = game.trim();
        }
        if (typeof minViews === "number") {
          inputs.min_views = String(minViews);
        }
        if (Array.isArray(streamers)) {
          const selected = streamers
            .map((login) => String(login).trim())
            .filter(Boolean);
          if (selected.length > 0) {
            inputs.streamers = selected.join(",");
          }
        }
      } else {
        const clipIds = record.clip_ids;
        if (
          !Array.isArray(clipIds) ||
          clipIds.length === 0 ||
          clipIds.length > 25 ||
          clipIds.some(
            (id) => typeof id !== "string" || !id.trim() || id.length > 100,
          )
        ) {
          return NextResponse.json(
            { error: "clip_ids must be 1-25 clip ids." },
            { status: 400 },
          );
        }
        inputs.clip_ids = clipIds.map((id) => String(id).trim()).join(",");
      }
    }
  }

  const endpoint = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}.yml/dispatches`;
  const dispatchedAt = Date.now();

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {
        ...GITHUB_HEADERS,
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        ...(inputs && Object.keys(inputs).length > 0 ? { inputs } : {}),
      }),
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
    } else if (response.status === 422) {
      hint =
        "GitHub rejected the workflow inputs. Push the latest fetch.yml/render.yml to main. ";
    }
    return NextResponse.json(
      {
        error: `${hint}GitHub ${response.status}: ${detail.slice(0, 300)}`,
      },
      { status: 502 },
    );
  }

  const workflowUrl = `https://github.com/${owner}/${repo}/actions/workflows/${workflow}.yml`;
  const run = await findWorkflowRun(
    token,
    owner,
    repo,
    workflow,
    dispatchedAt,
  );

  return NextResponse.json({
    ok: true,
    workflow,
    inputs: inputs ?? {},
    workflow_url: workflowUrl,
    run: run
      ? {
          id: run.id,
          run_number: run.run_number,
          status: run.status,
          conclusion: run.conclusion,
          html_url: run.html_url,
          created_at: run.created_at,
        }
      : null,
  });
}
