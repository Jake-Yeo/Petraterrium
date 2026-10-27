import './auto-import.css';
import './auto-import-bulk.css';
import './auto-import-single.css';
import { autoImportClient } from './auto-import-api';
import { AutoImportBulkPanel } from './auto-import-bulk';
import type {
  AutoImportAttempt,
  AutoImportContext,
  AutoImportSurfaceOptions,
  AutoImportTarget,
} from './auto-import-model';
import { AutoImportSingleDialog } from './auto-import-single';

export type {
  AutoImportClient,
  AutoImportEvidencePage,
  AutoImportSurfaceOptions,
  AutoImportTarget,
} from './auto-import-model';
export { autoImportClient };

export class AutoImportSurface {
  private readonly dialog: HTMLDialogElement;
  private readonly single: AutoImportSingleDialog;
  private readonly bulk: AutoImportBulkPanel;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: AutoImportSurfaceOptions,
  ) {
    const client = options.client ?? autoImportClient;
    this.dialog = document.createElement('dialog');
    this.bulk = new AutoImportBulkPanel(host, {
      client,
      context: options.context,
      openTarget: (target) => this.openTarget(target),
      openAttempt: (attemptId) => this.openAttempt(attemptId),
      onBatchPromoted: options.onBatchPromoted,
      onError: options.onError,
      pollIntervalMs: options.pollIntervalMs ?? 1200,
    });
    host.append(this.dialog);
    this.single = new AutoImportSingleDialog(this.dialog, {
      client,
      context: options.context,
      onChanged: (attempt) => this.bulk.attemptChanged(attempt),
      onPromoted: async (attempt) => {
        await this.bulk.importCompleted(attempt);
        await options.onPromoted?.(attempt);
      },
      onError: options.onError,
    });
  }

  async load(): Promise<void> {
    await this.bulk.load();
  }

  async setContext(context?: AutoImportContext): Promise<void> {
    const next = context ?? this.options.context();
    await this.bulk.setContext(next.scope, next.asOf);
  }

  openTarget(target: AutoImportTarget): void {
    this.single.openTarget(target);
  }

  async openAttempt(attemptId: string): Promise<void> {
    await this.single.openAttempt(attemptId);
  }

  async importCompleted(attempt?: AutoImportAttempt): Promise<void> {
    await this.bulk.importCompleted(attempt);
    if (attempt) await this.options.onPromoted?.(attempt);
  }

  suspend(): void {
    this.bulk.suspend();
    this.single.close();
  }

  destroy(): void {
    this.single.destroy();
    this.bulk.destroy();
    this.dialog.remove();
    this.host.replaceChildren();
  }
}

export function mountAutoImport(
  host: HTMLElement,
  options: AutoImportSurfaceOptions,
): AutoImportSurface {
  return new AutoImportSurface(host, options);
}
