import { describe, expect, it } from "vitest";

import {
  dayStart,
  nextAllowedUpload,
  type UploadPolicy,
} from "./upload-policy";

const policy: UploadPolicy = {
  maxUploadsPerDay: 25,
  windowStart: "13:00",
  windowEnd: "05:00",
  timezone: "Europe/Brussels",
  minGapMinutes: 30,
  slotMinutes: 15,
};

describe("dayStart", () => {
  it("starts the day at Brussels midnight", () => {
    expect(dayStart(new Date("2026-11-16T12:05:00Z"), policy).toISOString()).toBe(
      "2026-11-15T23:00:00.000Z",
    );
  });
});

describe("nextAllowedUpload", () => {
  it("moves an outside-window time to 13:00 Brussels", () => {
    const result = nextAllowedUpload(
      new Date("2026-11-16T06:00:00Z"),
      policy,
      null,
      0,
    );
    expect(result.toISOString()).toBe("2026-11-16T12:00:00.000Z");
  });

  it("rounds the minimum gap up to a scheduler slot", () => {
    const result = nextAllowedUpload(
      new Date("2026-11-16T12:05:00Z"),
      policy,
      new Date("2026-11-16T12:00:00Z"),
      0,
    );
    expect(result.toISOString()).toBe("2026-11-16T12:30:00.000Z");
  });

  it("waits for the next local midnight once the day is full", () => {
    const result = nextAllowedUpload(
      new Date("2026-11-16T12:05:00Z"),
      policy,
      new Date("2026-11-16T12:00:00Z"),
      25,
    );
    expect(result.toISOString()).toBe("2026-11-16T23:00:00.000Z");
  });
});
