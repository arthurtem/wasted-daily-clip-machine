import "server-only";

import { getSql } from "@/lib/db";

export interface AutomationState {
  uploadCap: number;
  fetchLimit: number;
  renderLimit: number;
  launchDate: string | null;
  lastUploadLimitAt: string | null;
  lastQuotaErrorAt: string | null;
  pausedUntil: string | null;
}

type Row = Record<string, unknown>;

function asNumber(value: unknown, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function asIso(value: unknown): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  return typeof value === "string" ? value : null;
}

export async function getAutomationState(): Promise<AutomationState> {
  try {
    const sql = getSql();
    const rows = (await sql`
      SELECT upload_cap, fetch_limit, render_limit, launch_date,
             last_upload_limit_at, last_quota_error_at, paused_until
      FROM automation_state
      WHERE id = TRUE
      LIMIT 1
    `) as Row[];
    const row = rows[0];
    if (row) {
      return {
        uploadCap: asNumber(row.upload_cap, 75),
        fetchLimit: asNumber(row.fetch_limit, 20),
        renderLimit: asNumber(row.render_limit, 20),
        launchDate: asIso(row.launch_date),
        lastUploadLimitAt: asIso(row.last_upload_limit_at),
        lastQuotaErrorAt: asIso(row.last_quota_error_at),
        pausedUntil: asIso(row.paused_until),
      };
    }
  } catch (error) {
    console.error("Could not load automation state", error);
  }
  return {
    uploadCap: 75,
    fetchLimit: 20,
    renderLimit: 20,
    launchDate: null,
    lastUploadLimitAt: null,
    lastQuotaErrorAt: null,
    pausedUntil: null,
  };
}
