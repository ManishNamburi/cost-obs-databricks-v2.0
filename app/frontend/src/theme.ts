/** Dashboard tokens. Hex lives in index.css :root only. */

export const C = {
  oatPage: "var(--oat-page)",
  card: "var(--card-surface)",
  white: "var(--paper-white)",
  oatMed: "var(--oat-med)",
  hairline: "var(--hairline)",
  rowHover: "var(--row-hover)",
  gridLine: "var(--grid-line)",
  navy: "var(--navy)",
  inkDeep: "var(--ink-deep)",
  ink: "var(--ink)",
  body: "var(--body)",
  slate: "var(--slate)",
  muted: "var(--muted)",
  lava: "var(--lava)",
  lavaHover: "var(--lava-hover)",
  coral: "var(--coral)",
  coralTint: "var(--coral-tint)",
  coralBrd: "var(--coral-brd)",
  green: "var(--green)",
  greenInk: "var(--green-ink)",
  greenTint: "var(--green-tint)",
  amber: "var(--amber)",
  amberInk: "var(--amber-ink)",
  amberTint: "var(--amber-tint)",
  maroon: "var(--maroon)",
  maroonTint: "var(--maroon-tint)",
  s1: "var(--s1)",
  s2: "var(--s2)",
  s3: "var(--s3)",
  s4: "var(--s4)",
  s5: "var(--s5)",
  statusDot: "var(--status-dot)",
  baseline: "var(--baseline)",
  busy: "var(--busy)",
  calMid: "var(--cal-mid)",
  calOor: "var(--cal-oor)",
  deltaUp: "var(--coral)",
  deltaDown: "var(--status-dot)",
} as const;

export const SERIES = [C.s1, C.s2, C.s3, C.s4, C.s5] as const;

/** Product identity colors (spec §2 / §6). */
export function productColor(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("sql") || n.includes("dbsql") || n.includes("genie") || n.includes("warehouse")) return C.s2;
  if (n.includes("interactive") || n.includes("all-purpose") || n.includes("notebook")) return C.s4;
  if (n.includes("serverless")) return C.s3;
  if (n.includes("etl") || n.includes("job") || n.includes("pipeline")) return C.s3;
  return C.s5;
}

export function seriesColor(index: number): string {
  return SERIES[index % SERIES.length];
}

export function rankedBarColor(rank: number): string {
  return rank === 1 ? C.s1 : C.s2;
}

export const FONT_SANS = "var(--sans)";
export const FONT_MONO = "var(--mono)";

export const APP_VERSION = "v2.1";
export const APP_TITLE = "cost-obs — Cost observability for Databricks";
export const APP_NAME = "cost-obs";
