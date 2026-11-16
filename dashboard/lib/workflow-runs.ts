import "server-only";

export interface WorkflowRun {
  id: number;
  name: string;
  displayTitle: string;
  status: string;
  conclusion: string | null;
  htmlUrl: string;
  runNumber: number;
  createdAt: string | null;
  event: string;
}

type Row = Record<string, unknown>;

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

export async function getRecentWorkflowRuns(
  limit = 6,
): Promise<WorkflowRun[]> {
  const token = process.env.GITHUB_TOKEN?.trim();
  const owner = process.env.GITHUB_OWNER?.trim();
  const repo = process.env.GITHUB_REPO?.trim();
  if (!token || !owner || !repo) {
    return [];
  }

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/runs?per_page=50`;
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      next: { revalidate: 15 },
    });
  } catch (error) {
    console.error("Could not load GitHub workflow runs", error);
    return [];
  }
  if (!response.ok) {
    return [];
  }

  const payload = (await response.json().catch(() => null)) as
    | { workflow_runs?: Row[] }
    | null;
  const rows = payload?.workflow_runs ?? [];
  const runs = rows.map((row) => ({
    id: asNumber(row.id),
    name: asString(row.name),
    displayTitle: asString(row.display_title),
    status: asString(row.status),
    conclusion:
      typeof row.conclusion === "string" ? row.conclusion : null,
    htmlUrl: asString(row.html_url),
    runNumber: asNumber(row.run_number),
    createdAt:
      typeof row.created_at === "string" ? row.created_at : null,
    event: asString(row.event),
  }));

  const perWorkflow = new Map<string, number>();
  return runs
    .filter((run) => {
      const seen = perWorkflow.get(run.name) ?? 0;
      if (seen >= 2) {
        return false;
      }
      perWorkflow.set(run.name, seen + 1);
      return true;
    })
    .slice(0, limit);
}
