export function formatAge(value: string | null): string {
  if (!value) {
    return "unknown";
  }
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) {
    return "unknown";
  }
  const minutes = Math.max(0, Math.floor((Date.now() - then) / 60_000));
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} min ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days} d ago`;
  }
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function formatCount(value: number | null): string {
  return value == null ? "—" : value.toLocaleString("en-US");
}
