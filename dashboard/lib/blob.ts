import "server-only";

import { del } from "@vercel/blob";

export async function deleteClipBlobs(
  urls: Array<string | null>,
): Promise<string[]> {
  const failures: string[] = [];
  for (const url of urls) {
    if (!url) {
      continue;
    }
    try {
      await del(url);
    } catch (error) {
      console.error("Failed to delete blob", url, error);
      failures.push(url);
    }
  }
  return failures;
}
