export interface StreamerOption {
  login: string;
  name: string;
}

// Keep in sync with config/streamers.yaml.
export const STREAMER_OPTIONS: StreamerOption[] = [
  { login: "kaicenat", name: "Kai Cenat" },
  { login: "xqc", name: "xQc" },
  { login: "stableronaldo", name: "StableRonaldo" },
];

export const GAME_OPTIONS = [
  "Grand Theft Auto VI",
  "Grand Theft Auto V",
];

export const DEFAULT_GAME_NAME = "Grand Theft Auto VI";
export const DEFAULT_MIN_VIEWS = 150;
