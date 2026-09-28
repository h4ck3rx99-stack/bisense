// Friendly aliases over the generated OpenAPI types. Never hand-write API shapes: run `npm run gen:types`.
import type { components } from "./types.gen";

type S = components["schemas"];

export type Lang = "en" | "hi" | "kn";
export type Answer = S["Answer"];
export type Point = S["Point"];
export type Citation = S["Citation"];
export type StandardRef = S["StandardRef"];
export type QueryInfo = S["QueryInfo"];
export type AskTrace = S["AskTrace"];
export type Drop = S["Drop"];
export type StageEvent = S["StageEvent"];
export type EvidenceEvent = S["EvidenceEvent"];
export type DoneEvent = S["DoneEvent"];
export type ErrorEvent = S["ErrorEvent"];
export type AskContext = S["AskContext"];
export type SearchResponse = S["SearchResponse"];
export type HealthOut = S["HealthOut"];
export type LibraryOut = S["LibraryOut"];
export type StandardSummary = S["StandardSummary"];
export type StandardListOut = S["StandardListOut"];
export type StandardDetail = S["StandardDetail"];
export type ClauseNode = S["ClauseNode"];
export type ClauseOut = S["ClauseOut"];
export type RequirementsOut = S["RequirementsOut"];
export type RequirementOut = S["RequirementOut"];
export type SuggestItem = S["SuggestItem"];
export type SummaryOut = S["SummaryOut"];
export type CompareResponse = S["CompareResponse"];
export type CompareRow = S["CompareRow"];
export type NumericRow = S["NumericRow"];
export type StandardKind = StandardSummary["kind"];
export type STTOut = S["STTOut"];
export type TranslateOut = S["TranslateOut"];
export type VoiceStatus = S["VoiceStatus"];
export type CoverageNote = S["CoverageNote"];
