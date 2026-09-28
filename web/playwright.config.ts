import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const FAKE_MIC = fileURLToPath(new URL("../server/tests/fixtures/audio/en_helmet.wav", import.meta.url));

// End-to-end tests run against the built app served by FastAPI with a deterministic FakeLLM
// (LLM_PROVIDER=fake) on port 8010, using the local index built by `npm run ingest`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8010", trace: "retain-on-failure" },
  projects: [
    // Chrome's fake microphone plays a real WAV recording (tests/fixtures/audio) into getUserMedia.
    {
      name: "voice",
      testMatch: /voice\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
        launchOptions: {
          args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${FAKE_MIC}`],
        },
      },
    },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }, testIgnore: /(mobile|voice)\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, isMobile: false, hasTouch: true }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: {
    command: "uv run uvicorn bisense.main:app --port 8010",
    cwd: "../server",
    url: "http://127.0.0.1:8010/api/health",
    timeout: 120_000,
    reuseExistingServer: false,
    // STT_PROVIDER is explicit so the fake-microphone test can reach real speech-to-text when a Groq key
    // is in .env (the voice test skips itself otherwise).
    env: { STT_PROVIDER: "openai_compatible", LLM_PROVIDER: "fake", RATE_LIMIT_ASK: "1000/minute", DEMO_MODE: "false", APP_ENV: "production", PYTHONIOENCODING: "utf-8" },
  },
});
