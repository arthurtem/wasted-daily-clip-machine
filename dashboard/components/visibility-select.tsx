"use client";

import type { ClipPrivacy } from "@/lib/types";

const OPTIONS: Array<{ value: ClipPrivacy; label: string }> = [
  { value: "public", label: "Public" },
  { value: "unlisted", label: "Unlisted" },
  { value: "private", label: "Private" },
];

export default function VisibilitySelect({
  id,
  value,
  onChange,
  disabled = false,
}: {
  id: string;
  value: ClipPrivacy;
  onChange: (value: ClipPrivacy) => void;
  disabled?: boolean;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value as ClipPrivacy)}
      disabled={disabled}
      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-xs text-zinc-100 outline-none transition focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/30 disabled:opacity-60"
    >
      {OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
