import type { Counts } from "@/lib/types";

export default function CountsRow({ counts }: { counts: Counts }) {
  const nextUpload = counts.nextUploadAt
    ? new Date(counts.nextUploadAt)
    : null;
  const pausedUntil = counts.pausedUntil ? new Date(counts.pausedUntil) : null;
  const paused = Boolean(pausedUntil && pausedUntil.getTime() > Date.now());
  const format = (value: Date) =>
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Brussels",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(value);
  const nextLabel = paused && pausedUntil
    ? format(pausedUntil)
    : nextUpload && nextUpload.getTime() <= Date.now() + 60_000
      ? "Now"
      : nextUpload
        ? format(nextUpload)
        : "—";
  const items = [
    { label: "Inbox", value: counts.new },
    { label: "Rendered", value: counts.rendered },
    { label: "Approved", value: counts.approved },
    {
      label: "Uploads today",
      value: `${counts.uploadedToday}/${counts.maxUploadsPerDay}`,
    },
    { label: paused ? "Paused until" : "Next upload", value: nextLabel },
    { label: "Failed", value: counts.failed },
  ];

  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
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
      <p className="text-[11px] text-zinc-500">
        Uploads reset at Brussels midnight · next slot every 10 minutes
      </p>
    </div>
  );
}
