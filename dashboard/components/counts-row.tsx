import type { Counts } from "@/lib/types";

export default function CountsRow({ counts }: { counts: Counts }) {
  const items = [
    { label: "Rendered", value: counts.rendered },
    { label: "Approved", value: counts.approved },
    { label: "Uploaded today", value: counts.uploadedToday },
    { label: "Failed", value: counts.failed },
  ];

  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-2xl border border-zinc-800 bg-zinc-900/60 px-4 py-3"
        >
          <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            {item.label}
          </dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
