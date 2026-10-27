import { execFileSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';

export default function setup(): void {
  rmSync(resolve('.playwright/simulation-registry.json'), { force: true });
  rmSync(resolve('.playwright/simulation-runs.sqlite3'), { force: true });
  rmSync(resolve('.playwright/simulation-runs.sqlite3-shm'), { force: true });
  rmSync(resolve('.playwright/simulation-runs.sqlite3-wal'), { force: true });
  rmSync(resolve('.playwright/ai-settings.json'), { force: true });
  execFileSync(
    'uv',
    [
      'run',
      '--project',
      resolve('../backend'),
      'python',
      resolve('../backend/tests/seed_browser_atlas.py'),
      resolve('.playwright/atlas.sqlite3'),
    ],
    { stdio: 'inherit' },
  );
}
