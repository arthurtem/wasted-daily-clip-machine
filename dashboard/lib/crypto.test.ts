import { afterEach, describe, expect, it, vi } from "vitest";

import { decrypt, encrypt } from "./crypto";

const KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("token crypto", () => {
  it("round-trips a token in the three-part format", () => {
    vi.stubEnv("TOKEN_ENCRYPTION_KEY", KEY);
    const encrypted = encrypt("refresh-token-value");

    expect(encrypted.split(".")).toHaveLength(3);
    expect(decrypt(encrypted)).toBe("refresh-token-value");
  });

  it("rejects a malformed payload", () => {
    vi.stubEnv("TOKEN_ENCRYPTION_KEY", KEY);
    expect(() => decrypt("nope")).toThrow(/Invalid encrypted token format/);
  });

  it("rejects a key that is not 32 bytes", () => {
    vi.stubEnv("TOKEN_ENCRYPTION_KEY", "c2hvcnQ=");
    expect(() => encrypt("value")).toThrow(/exactly 32 bytes/);
  });
});
