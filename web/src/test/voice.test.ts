import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { micErrorFrom, sttErrorFrom } from "../lib/recorder";
import { pickVoice, splitSentences } from "../lib/tts";

const err = (name: string) => Object.assign(new Error(name), { name });

describe("microphone error mapping", () => {
  it("maps getUserMedia failures to stable codes", () => {
    expect(micErrorFrom(err("NotAllowedError")).code).toBe("denied");
    expect(micErrorFrom(err("SecurityError")).code).toBe("denied");
    expect(micErrorFrom(err("NotFoundError")).code).toBe("no_device");
    expect(micErrorFrom(err("OverconstrainedError")).code).toBe("no_device");
    expect(micErrorFrom(err("NotReadableError")).code).toBe("busy");
    expect(micErrorFrom(err("Weird")).code).toBe("busy");
  });

  it("maps server STT errors", () => {
    expect(sttErrorFrom(new ApiError(503, "stt_unavailable", "")).code).toBe("unavailable");
    expect(sttErrorFrom(new ApiError(400, "audio_empty", "")).code).toBe("too_short");
    expect(sttErrorFrom(new ApiError(0, "network", "")).code).toBe("network");
    const s = sttErrorFrom(new ApiError(502, "stt_failed", ""));
    expect(s.code).toBe("server");
    expect(s.detail).toBe("stt_failed");
  });
});

describe("read-aloud chunking", () => {
  it("groups sentences up to the limit and never splits mid-word", () => {
    const text = "One. Two is here. " + "Word ".repeat(80) + "end. Three.";
    const chunks = splitSentences(text, 60);
    expect(chunks.every((c) => c.length <= 61)).toBe(true);
    expect(chunks.join(" ").replace(/\s+/g, " ")).toBe(text.trim().replace(/\s+/g, " "));
    expect(chunks[0]).toBe("One. Two is here.");
  });

  it("splits Hindi on the danda", () => {
    expect(splitSentences("पहला वाक्य। दूसरा वाक्य।", 12)).toEqual(["पहला वाक्य।", "दूसरा वाक्य।"]);
  });
});

describe("voice selection", () => {
  const v = (lang: string, name = lang) => ({ lang, name }) as SpeechSynthesisVoice;
  it("prefers the exact locale, accepts the same language, never another language", () => {
    expect(pickVoice([v("en-US"), v("en-IN")], "en")?.lang).toBe("en-IN");
    expect(pickVoice([v("en-US")], "en")?.lang).toBe("en-US");
    expect(pickVoice([v("hi_IN")], "hi")?.lang).toBe("hi_IN");
    expect(pickVoice([v("en-IN"), v("hi-IN")], "kn")).toBeNull();
  });
});
