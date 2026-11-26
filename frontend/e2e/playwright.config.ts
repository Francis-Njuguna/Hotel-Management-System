import { defineConfig } from '@playwright/test';
import { origin } from './target';

const channel = process.env.PLAYWRIGHT_CHANNEL?.trim() || undefined;
if (channel && channel !== 'msedge') {
  throw new Error('Leave PLAYWRIGHT_CHANNEL unset for bundled Chromium, or set it to msedge for installed Microsoft Edge.');
}

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  projects: [{ name: 'chromium', use: { browserName: 'chromium', channel } }],
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 8_000 },
  reporter: 'list',
  outputDir: './test-results',
  preserveOutput: 'never',
  use: {
    baseURL: origin,
    viewport: { width: 1366, height: 900 },
    locale: 'en-GB',
    timezoneId: 'Africa/Nairobi',
    actionTimeout: 10_000,
    navigationTimeout: 25_000,
    serviceWorkers: 'block',
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
});
