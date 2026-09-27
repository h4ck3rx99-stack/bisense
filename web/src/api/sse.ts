// POST + Server-Sent Events reader for /api/ask (EventSource only supports GET).
import type { AskContext, Answer, AskTrace, DoneEvent, ErrorEvent, EvidenceEvent, Lang, QueryInfo, StageEvent } from "./types";
import { ApiError } from "./client";

export interface AskHandlers {
  onStage?: (e: StageEvent) => void;
  onQuery?: (e: QueryInfo) => void;
  onEvidence?: (e: EvidenceEvent) => void;
  onAnswer?: (e: Answer) => void;
  onTrace?: (e: AskTrace) => void;
  onError?: (e: ErrorEvent) => void;
  onDone?: (e: DoneEvent) => void;
}

export function parseSSE(chunk: string): { event: string; data: string }[] {
  return chunk
    .split(/\n\n/)
    .filter((block) => block.trim().length > 0)
    .map((block) => {
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      return { event, data: data.join("\n") };
    });
}

export async function ask(query: string, lang: Lang, context: AskContext | undefined, handlers: AskHandlers, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ query, lang, context }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, "network", navigator.onLine ? "error.backend_down" : "error.offline");
  }
  if (!res.ok || !res.body) {
    let body: { code?: string; message_key?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, body.code ?? "http_error", body.message_key ?? "error.internal");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const cut = buffer.lastIndexOf("\n\n");
    if (cut === -1) continue;
    const complete = buffer.slice(0, cut + 2);
    buffer = buffer.slice(cut + 2);
    for (const { event, data } of parseSSE(complete)) dispatch(event, data, handlers);
  }
  if (buffer.trim()) for (const { event, data } of parseSSE(buffer)) dispatch(event, data, handlers);
}

function dispatch(event: string, data: string, h: AskHandlers) {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }
  switch (event) {
    case "stage":
      h.onStage?.(payload as StageEvent);
      break;
    case "query":
      h.onQuery?.(payload as QueryInfo);
      break;
    case "evidence":
      h.onEvidence?.(payload as EvidenceEvent);
      break;
    case "answer":
      h.onAnswer?.(payload as Answer);
      break;
    case "trace":
      h.onTrace?.(payload as AskTrace);
      break;
    case "error":
      h.onError?.(payload as ErrorEvent);
      break;
    case "done":
      h.onDone?.(payload as DoneEvent);
      break;
  }
}
