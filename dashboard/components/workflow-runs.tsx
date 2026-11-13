import { formatAge } from "@/lib/format";
import type { WorkflowRun } from "@/lib/workflow-runs";

function statusClasses(run: WorkflowRun): string {
  if (run.status !== "completed") {
    return "border-amber-900 bg-amber-950/30 text-amber-200";
  }
  if (run.conclusion === "success") {
    return "border-emerald-900 bg-emerald-950/30 text-emerald-200";
  }
  if (run.conclusion === "cancelled") {
    return "border-zinc-700 bg-zinc-900 text-zinc-300";
  }
  return "border-red-900 bg-red-950/30 text-red-200";
}

function statusLabel(run: WorkflowRun): string {
  if (run.status === "completed") {
    return run.conclusion ?? "completed";
  }
  return run.status.replace("_", " ");
}

export default function WorkflowRuns({ runs }: { runs: WorkflowRun[] }) {
  if (runs.length === 0) {
    return null;
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Recent workflows
        </h2>
        <span className="text-xs text-zinc-600">
          refreshes on page reload
        </span>
      </div>
      <div className="grid gap-2">
        {runs.map((run) => (
          <a
            key={run.id}
            href={run.htmlUrl}
            target="_blank"
            rel="noreferrer"
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/50 px-3 py-2.5 transition hover:bg-zinc-900"
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-zinc-200">
                {run.name} #{run.runNumber}
              </span>
              <span className="text-xs text-zinc-500">
                {run.displayTitle || run.event} · {formatAge(run.createdAt)}
              </span>
            </span>
            <span
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${statusClasses(run)}`}
            >
              {statusLabel(run)}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
