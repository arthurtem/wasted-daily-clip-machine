import { SignJWT, jwtVerify } from "jose";

export const SESSION_COOKIE = "wd_session";
export const SESSION_MAX_AGE = 60 * 60 * 24 * 7;

export type SessionRole = "owner" | "auditor";

function secretKey(): Uint8Array {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error("SESSION_SECRET is not set");
  }
  return new TextEncoder().encode(secret);
}

export async function createSessionToken(
  role: SessionRole = "owner",
): Promise<string> {
  return new SignJWT({ role })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_MAX_AGE}s`)
    .sign(secretKey());
}

export async function verifySessionToken(
  token: string | undefined | null,
): Promise<SessionRole | null> {
  if (!token) {
    return null;
  }
  try {
    const { payload } = await jwtVerify(token, secretKey(), {
      algorithms: ["HS256"],
    });
    if (payload.role === "auditor" || payload.role === "owner") {
      return payload.role;
    }
    // Sessions issued before reviewer roles existed used "reviewer" for the
    // owner; keep those working until they expire.
    if (payload.role === "reviewer") {
      return "owner";
    }
    return null;
  } catch {
    return null;
  }
}
