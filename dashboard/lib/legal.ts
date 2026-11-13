export {
  GOOGLE_PERMISSIONS_URL,
  GOOGLE_PRIVACY_URL,
  YOUTUBE_COMMUNITY_URL,
  YOUTUBE_TOS_URL,
} from "@/lib/links";

export const LAST_UPDATED = "November 13, 2026";

export function ownerName(): string {
  const value = process.env.OWNER_NAME?.trim();
  return value || "the app owner";
}

export function contactEmail(): string {
  const value = process.env.CONTACT_EMAIL?.trim();
  return value || "the contact email configured for this deployment";
}

export function contactEmailHref(): string | null {
  const value = process.env.CONTACT_EMAIL?.trim();
  if (!value || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
    return null;
  }
  return `mailto:${value}`;
}
