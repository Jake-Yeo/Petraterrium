import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  globalSetup: './tests/setup.ts',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5181',
    viewport: { width: 1440, height: 1100 },
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-webgl'] },
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'uv run --project ../backend uvicorn petraterrium.main:app --host 127.0.0.1 --port 8011',
      url: 'http://127.0.0.1:8011/health',
      reuseExistingServer: false,
      env: { PETRATERRIUM_ATLAS_PATH: resolve('.playwright/atlas.sqlite3') },
    },
    {
      command: 'npm run dev -- --port 5181',
      url: 'http://127.0.0.1:5181',
      reuseExistingServer: false,
      env: { PETRATERRIUM_API_URL: 'http://127.0.0.1:8011' },
    },
  ],
});
