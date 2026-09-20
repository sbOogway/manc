// The overview's pure helpers: kind filter, ordering, the tile's texts.
import type { AssetSummary } from "../api/types";
import { bandLabel, formatDate, formatDelta, formatScore } from "./format";

const RISK_LABELS: [number, string][] = [
  [0.75, "heavy week"],
  [0.25, "busy week"],
  [0, "quiet"],
];

const KIND_ORDER = ["forex", "metal", "commodity", "equity_index", "crypto", "bond"];
const KIND_LABELS: Record<string, string> = {
  all: "all",
  forex: "forex",
  metal: "metals",
  commodity: "commodities",
  equity_index: "equity indices",
  crypto: "crypto",
  bond: "bonds",
};
export const KIND_KEY = "manc.kind";

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replaceAll("_", " ");
}

export function kindsOf(summaries: AssetSummary[]): string[] {
  const present = new Set(summaries.map((summary) => summary.kind));
  const known = KIND_ORDER.filter((kind) => present.has(kind));
  const others = [...present].filter((kind) => !KIND_ORDER.includes(kind)).sort();
  return [...known, ...others];
}

export function filterByKind(summaries: AssetSummary[], kind: string): AssetSummary[] {
  return kind === "all" ? summaries : summaries.filter((summary) => summary.kind === kind);
}

export function eventRiskLabel(risk: number): string {
  return RISK_LABELS.find(([floor]) => risk >= floor)?.[1] ?? "quiet";
}

export interface TileModel {
  symbol: string;
  kind: string;
  band: string;
  score: string;
  bandLabel: string;
  delta: string;
  deltaClass: "flat" | "up" | "down";
  date: string;
  risk: string;
}

export function tileModel(summary: AssetSummary): TileModel {
  const delta = summary.delta;
  return {
    symbol: summary.symbol,
    kind: summary.kind,
    band: summary.band,
    score: formatScore(summary.score),
    bandLabel: bandLabel(summary.band),
    delta: formatDelta(delta),
    deltaClass: !delta ? "flat" : delta > 0 ? "up" : "down",
    date: formatDate(summary.date),
    risk: eventRiskLabel(summary.event_risk),
  };
}
