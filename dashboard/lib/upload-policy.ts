export interface UploadPolicy {
  maxUploadsPerDay: number;
  windowStart: string;
  windowEnd: string;
  timezone: string;
  minGapMinutes: number;
  slotMinutes: number;
}

export const UPLOAD_POLICY: UploadPolicy = {
  maxUploadsPerDay: 100,
  windowStart: "00:00",
  windowEnd: "23:59",
  timezone: "Europe/Brussels",
  minGapMinutes: 0,
  slotMinutes: 10,
};

export function uploadPolicy(): UploadPolicy {
  return UPLOAD_POLICY;
}

function clock(value: string): { hour: number; minute: number } {
  const [hour, minute] = value.split(":").map(Number);
  return { hour, minute };
}

function zonedParts(date: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const read = (type: string) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0);
  return {
    year: read("year"),
    month: read("month"),
    day: read("day"),
    hour: read("hour"),
    minute: read("minute"),
    second: read("second"),
  };
}

function localDateToUtc(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  timezone: string,
): Date {
  let guess = Date.UTC(year, month - 1, day, hour, minute, 0, 0);
  for (let index = 0; index < 3; index += 1) {
    const parts = zonedParts(new Date(guess), timezone);
    const rendered = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    );
    guess += Date.UTC(year, month - 1, day, hour, minute, 0, 0) - rendered;
  }
  return new Date(guess);
}

export function insideWindow(date: Date, policy: UploadPolicy): boolean {
  const local = zonedParts(date, policy.timezone);
  const current = local.hour * 60 + local.minute;
  const start = clock(policy.windowStart);
  const end = clock(policy.windowEnd);
  const startMinutes = start.hour * 60 + start.minute;
  const endMinutes = end.hour * 60 + end.minute;
  if (startMinutes <= endMinutes) {
    return current >= startMinutes && current < endMinutes;
  }
  return current >= startMinutes || current < endMinutes;
}

export function nextWindowStart(date: Date, policy: UploadPolicy): Date {
  if (insideWindow(date, policy)) {
    return date;
  }
  const local = zonedParts(date, policy.timezone);
  const start = clock(policy.windowStart);
  let candidate = localDateToUtc(
    local.year,
    local.month,
    local.day,
    start.hour,
    start.minute,
    policy.timezone,
  );
  if (candidate.getTime() <= date.getTime()) {
    candidate = new Date(candidate.getTime() + 24 * 60 * 60 * 1000);
  }
  return candidate;
}

function roundToSlot(date: Date, slotMinutes: number): Date {
  if (slotMinutes <= 0) {
    return date;
  }
  const interval = slotMinutes * 60 * 1000;
  return new Date(Math.ceil(date.getTime() / interval) * interval);
}

export function nextAllowedUpload(
  now: Date,
  policy: UploadPolicy,
  latestUpload: Date | null,
  oldestUpload: Date | null,
  uploadedLast24h: number,
): Date {
  let candidate = now;
  if (latestUpload) {
    candidate = new Date(
      Math.max(
        candidate.getTime(),
        latestUpload.getTime() + policy.minGapMinutes * 60 * 1000,
      ),
    );
  }
  if (uploadedLast24h >= policy.maxUploadsPerDay && oldestUpload) {
    candidate = new Date(
      Math.max(
        candidate.getTime(),
        oldestUpload.getTime() + 24 * 60 * 60 * 1000,
      ),
    );
  }
  if (!insideWindow(candidate, policy)) {
    candidate = nextWindowStart(candidate, policy);
  }
  return roundToSlot(candidate, policy.slotMinutes);
}

export function formatBrussels(date: Date, policy: UploadPolicy): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: policy.timezone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
