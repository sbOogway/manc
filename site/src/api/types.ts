// The API's types, generated from site/openapi.json by `npm run types` (scripts/openapi-schema.py
// writes that file from the FastAPI app, and a Python test fails when it drifts).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type AssetOut = Schemas["AssetOut"];
export type AssetSummary = Schemas["AssetSummary"];
export type AssetHistory = Schemas["AssetHistory"];
export type ScorePoint = Schemas["ScorePoint"];
export type Scale = Schemas["Scale"];
export type ReportOut = Schemas["ReportOut"];
export type HeadlineView = Schemas["HeadlineView"];
export type CalendarEvent = Schemas["CalendarEvent"];
export type ForecastPanel = Schemas["ForecastPanel"];
export type ForecastRow = Schemas["ForecastRow"];
export type MacroForecastRow = Schemas["MacroForecastRow"];
export type MedianRow = Schemas["MedianRow"];
export type SpotPrice = Schemas["SpotPrice"];
export type ChainSeries = Schemas["ChainSeries"];
export type ChainPoint = Schemas["ChainPoint"];
export type FormulasOut = Schemas["FormulasOut"];
export type HealthOut = Schemas["HealthOut"];

export type Params = Record<string, string | number | null | undefined>;
