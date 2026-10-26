import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

export default function setup(): void {
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
