// Voice end to end. Chrome's fake microphone plays tests/fixtures/audio/en_helmet.wav
// ("Which Indian Standard applies to helmets for two wheeler riders?").
//
//  - real path: microphone -> MediaRecorder -> /api/voice/stt (Groq Whisper) -> editable transcript -> ask
//    (skipped when the server has no speech-to-text key);
//  - failure paths use a stubbed getUserMedia / stubbed STT response (test-only mocks);
//  - read-aloud uses a speechSynthesis spy, because headless Chrome has no audio output to assert on.
import type { Page } from "@playwright/test";
import { expect, test, waitForAnswer } from "./fixtures";

const box = (page: Page) => page.getByRole("textbox", { name: /Ask about Indian Standards/ });
const mic = (page: Page) => page.getByRole("button", { name: /Speak your question|Stop recording/ });

test("microphone -> server speech-to-text -> transcript in the box -> answer", async ({ page, request }) => {
  const status = await (await request.get("/api/voice/status")).json();
  test.skip(!status.stt_available, "server speech-to-text is not configured (no key in .env)");
  await page.goto("/");
  await mic(page).click();
  const panel = page.getByTestId("voice-panel");
  await expect(panel).toContainText("Recording");
  // the level meter moves while the fixture plays
  await expect
    .poll(async () => Number(await page.getByTestId("voice-level").getAttribute("aria-valuenow")), { timeout: 10_000 })
    .toBeGreaterThan(5);
  await page.waitForTimeout(4500); // the fixture is 4.2 s long
  await page.getByRole("button", { name: "Done" }).click();
  await expect(box(page)).toHaveValue(/helmet/i, { timeout: 30_000 });
  await expect(box(page)).toHaveValue(/two.?wheeler/i);
  await expect(page.getByTestId("voice-message")).toContainText("Check the text");
  // the transcript is editable and nothing was asked automatically
  await expect(page).toHaveURL(/\/$/);
  await box(page).press("End");
  await box(page).pressSequentially(" ");
  await box(page).press("Enter");
  await expect(page).toHaveURL(/\/ask\?q=.*helmet/i);
  await waitForAnswer(page);
});

test("cancel discards the recording and releases the microphone", async ({ page }) => {
  let uploads = 0;
  await page.route("**/api/voice/stt", (route) => {
    uploads++;
    return route.fulfill({ json: { text: "should not appear", no_speech: false, language: "en", requested_language: "en", duration_s: 1, provider: "test", model: "test", ms: 1 } });
  });
  await page.route("**/api/voice/status", (route) =>
    route.fulfill({ json: { stt_available: true, stt_provider: "test", stt_model: "t", stt_languages: ["en", "hi", "kn"], tts_available: false, tts_provider: null, tts_languages: [], tts_problem: null, max_seconds: 60, max_bytes: 8000000 } }),
  );
  await page.addInitScript(() => {
    const streams: MediaStream[] = [];
    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (c) => {
      const s = await orig(c);
      streams.push(s);
      return s;
    };
    Object.defineProperty(window, "__liveTracks", { get: () => streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === "live").length });
  });
  await page.goto("/");
  await mic(page).click();
  await expect(page.getByTestId("voice-panel")).toContainText("Recording");
  expect(await page.evaluate(() => (window as unknown as { __liveTracks: number }).__liveTracks)).toBe(1);
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("voice-panel")).toHaveCount(0);
  await expect(box(page)).toHaveValue("");
  expect(uploads).toBe(0);
  // every microphone track is stopped
  expect(await page.evaluate(() => (window as unknown as { __liveTracks: number }).__liveTracks)).toBe(0);
});

for (const [name, code, message] of [
  ["NotAllowedError", "denied", "Microphone access is blocked"],
  ["NotFoundError", "no_device", "No microphone was found"],
  ["NotReadableError", "busy", "another app may be using it"],
] as const) {
  test(`getUserMedia ${name} -> "${code}" explained, typing still works`, async ({ page }) => {
    await page.addInitScript((errName) => {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("test", errName));
    }, name);
    await page.route("**/api/voice/status", (route) =>
      route.fulfill({ json: { stt_available: true, stt_provider: "test", stt_model: "t", stt_languages: ["en"], tts_available: false, tts_provider: null, tts_languages: [], tts_problem: null, max_seconds: 60, max_bytes: 8000000 } }),
    );
    await page.goto("/");
    await mic(page).click();
    await expect(page.getByTestId("voice-message")).toContainText(message);
    await box(page).fill("helmet standard");
    await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeEnabled();
  });
}

test.describe("server speech-to-text failure", () => {
  test.use({ allowedConsoleErrors: [/status of 503/] });
  test("is explained and nothing is inserted", async ({ page }) => {
    await page.route("**/api/voice/status", (route) =>
      route.fulfill({ json: { stt_available: true, stt_provider: "test", stt_model: "t", stt_languages: ["en"], tts_available: false, tts_provider: null, tts_languages: [], tts_problem: null, max_seconds: 60, max_bytes: 8000000 } }),
    );
    await page.route("**/api/voice/stt", (route) => route.fulfill({ status: 503, json: { code: "stt_busy", message_key: "error.stt_busy" } }));
    await page.goto("/");
    await mic(page).click();
    await expect(page.getByTestId("voice-panel")).toContainText("Recording");
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByTestId("voice-message")).toContainText("Speech recognition failed");
    await expect(box(page)).toHaveValue("");
  });
});

test("language switch while recording cancels it", async ({ page }) => {
  await page.route("**/api/voice/status", (route) =>
    route.fulfill({ json: { stt_available: true, stt_provider: "test", stt_model: "t", stt_languages: ["en", "hi", "kn"], tts_available: false, tts_provider: null, tts_languages: [], tts_problem: null, max_seconds: 60, max_bytes: 8000000 } }),
  );
  let uploads = 0;
  await page.route("**/api/voice/stt", (route) => {
    uploads++;
    return route.abort();
  });
  await page.goto("/");
  await mic(page).click();
  await expect(page.getByTestId("voice-panel")).toBeVisible();
  await page.getByRole("button", { name: "हिन्दी" }).click();
  await expect(page.getByTestId("voice-panel")).toHaveCount(0);
  expect(uploads).toBe(0);
});

test("read-aloud: chunks spoken in the answer language, stopped on navigation", async ({ page }) => {
  await page.addInitScript(() => {
    const spoken: { text: string; lang: string }[] = [];
    let cancels = 0;
    const synth = window.speechSynthesis;
    const voice = { lang: "en-IN", name: "Test English", default: true, localService: true, voiceURI: "t" } as SpeechSynthesisVoice;
    Object.defineProperty(synth, "getVoices", { value: () => [voice] });
    Object.defineProperty(synth, "speak", {
      value: (u: SpeechSynthesisUtterance) => {
        spoken.push({ text: u.text, lang: u.lang });
        setTimeout(() => u.onstart?.(new Event("start") as SpeechSynthesisEvent), 10);
        setTimeout(() => u.onend?.(new Event("end") as SpeechSynthesisEvent), 400);
      },
    });
    Object.defineProperty(synth, "cancel", { value: () => void cancels++ });
    (window as unknown as { __tts: () => unknown }).__tts = () => ({ spoken, cancels });
  });
  await page.goto("/ask?q=" + encodeURIComponent("Is BIS certification compulsory for two wheeler helmets?") + "&lang=en");
  await waitForAnswer(page);
  const listen = page.getByTestId("listen").first();
  await listen.click();
  await expect(listen).toHaveAttribute("data-tts-state", /speaking|idle/);
  await expect.poll(async () => ((await page.evaluate(() => (window as unknown as { __tts: () => { spoken: unknown[] } }).__tts())).spoken.length)).toBeGreaterThan(0);
  const { spoken } = (await page.evaluate(() => (window as unknown as { __tts: () => unknown }).__tts())) as { spoken: { text: string; lang: string }[] };
  expect(spoken.every((s) => s.lang === "en-IN" && s.text.length <= 221)).toBe(true);
  await page.getByRole("link", { name: /Library|Standards/ }).first().click();
  const after = (await page.evaluate(() => (window as unknown as { __tts: () => unknown }).__tts())) as { cancels: number };
  expect(after.cancels).toBeGreaterThan(0);
});

test("read-aloud is honestly unavailable when the device has no voice for the language", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window.speechSynthesis, "getVoices", { value: () => [{ lang: "en-US", name: "English only" }] });
  });
  await page.goto("/ask?q=" + encodeURIComponent("हेलमेट के लिए कौन सा मानक है?") + "&lang=kn");
  await waitForAnswer(page).catch(() => undefined);
  await expect(page.getByTestId("tts-unavailable").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("tts-unavailable").first()).toContainText(/ಕನ್ನಡ|Kannada/);
});
