import { describe, expect, it } from "vitest";

import { parseYouTubeVideoId } from "./youtube-url";

const ID = "dQw4w9WgXcQ";

describe("parseYouTubeVideoId", () => {
  it("parses a Shorts URL", () => {
    expect(
      parseYouTubeVideoId(`https://youtube.com/shorts/${ID}?feature=share`),
    ).toBe(ID);
  });

  it("parses a youtu.be URL", () => {
    expect(parseYouTubeVideoId(`https://youtu.be/${ID}?si=abc`)).toBe(ID);
  });

  it("parses a watch URL", () => {
    expect(
      parseYouTubeVideoId(`https://www.youtube.com/watch?v=${ID}&t=5`),
    ).toBe(ID);
  });

  it("rejects a non-YouTube URL", () => {
    expect(
      parseYouTubeVideoId(`https://example.com/shorts/${ID}`),
    ).toBeNull();
    expect(parseYouTubeVideoId("not a url")).toBeNull();
    expect(parseYouTubeVideoId("https://youtube.com/feed/trending")).toBeNull();
  });
});
