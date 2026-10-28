import type { ValidateFunction } from 'ajv';
import { parseContract, validator } from '../api';
import type {
  AutoImportAttempt,
  AutoImportBatch,
  AutoImportBatchRequest,
  AutoImportClient,
  AutoImportEvidencePage,
  AutoImportQueuePage,
  AutoImportQueueQuery,
  AutoImportSourceInput,
  AutoImportTarget,
  BatchPromotionRequest,
  MappingConfirmation,
  PromotionRequest,
} from './auto-import-model';

const validators = {
  queue: validator<AutoImportQueuePage>('AutoImportQueuePageView'),
  attempt: validator<AutoImportAttempt>('AutoImportAttemptView'),
  batch: validator<AutoImportBatch>('AutoImportBatchView'),
  evidence: validator<AutoImportEvidencePage>('AutoImportEvidenceView'),
};

async function responseError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail
      .map((entry) =>
        typeof entry === 'object' && entry && 'msg' in entry ? String(entry.msg) : String(entry),
      )
      .join('; ');
  }
  return `Request failed (${response.status})`;
}

async function requestJson<T>(
  path: string,
  validate: ValidateFunction<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  if (!response.ok) throw new Error(await responseError(response));
  return parseContract(await response.json(), validate);
}

async function requestNullableJson<T>(
  path: string,
  validate: ValidateFunction<T>,
  init?: RequestInit,
): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  if (!response.ok) throw new Error(await responseError(response));
  const data: unknown = await response.json();
  return data === null ? null : parseContract(data, validate);
}

function jsonPost(value?: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value ?? {}),
  };
}

function queueParameters(query: AutoImportQueueQuery): URLSearchParams {
  return new URLSearchParams({
    scope: query.scope,
    as_of: query.as_of,
    level: query.level,
    feature_id: query.feature_id,
    search: query.search,
    sort: query.sort,
    priority: query.priority,
    city_population_threshold: String(query.city_population_threshold),
    page: String(query.page),
    page_size: String(query.page_size),
  });
}

function sourceForm(
  target: AutoImportTarget,
  input: AutoImportSourceInput,
  scope: string,
): FormData {
  const body = new FormData();
  body.append('target', JSON.stringify(target));
  body.append('scope', scope);
  body.append('urls', JSON.stringify(input.urls));
  body.append('pasted_text', input.pasted_text);
  input.files.forEach((file) => body.append('files', file));
  return body;
}

export const autoImportClient: AutoImportClient = {
  queue: (query, signal) =>
    requestJson<AutoImportQueuePage>(
      `/api/atlas/auto-import/queue?${queueParameters(query)}`,
      validators.queue,
      { signal },
    ),
  start: (target, input, scope) =>
    requestJson<AutoImportAttempt>(
      '/api/atlas/auto-import/attempts',
      validators.attempt,
      {
        method: 'POST',
        body: sourceForm(target, input, scope),
      },
    ),
  attempt: (attemptId, signal) =>
    requestJson<AutoImportAttempt>(
      `/api/atlas/auto-import/attempts/${encodeURIComponent(attemptId)}`,
      validators.attempt,
      { signal },
    ),
  confirmMapping: (attemptId: string, confirmation: MappingConfirmation) =>
    requestJson<AutoImportAttempt>(
      `/api/atlas/auto-import/attempts/${encodeURIComponent(attemptId)}/mapping`,
      validators.attempt,
      jsonPost(confirmation),
    ),
  continueResearch: (attemptId: string) =>
    requestJson<AutoImportAttempt>(
      `/api/atlas/auto-import/attempts/${encodeURIComponent(attemptId)}/research`,
      validators.attempt,
      jsonPost(),
    ),
  rerun: (attemptId, request) =>
    requestJson<AutoImportAttempt>(
      `/api/atlas/auto-import/attempts/${encodeURIComponent(attemptId)}/rerun`,
      validators.attempt,
      jsonPost(request),
    ),
  promote: (attemptId: string, request: PromotionRequest) =>
    requestJson<AutoImportAttempt>(
      `/api/atlas/auto-import/attempts/${encodeURIComponent(attemptId)}/promote`,
      validators.attempt,
      jsonPost(request),
    ),
  createBatch: (request: AutoImportBatchRequest) =>
    requestJson<AutoImportBatch>(
      '/api/atlas/auto-import/batches',
      validators.batch,
      jsonPost(request),
    ),
  batch: (batchId, signal) =>
    requestJson<AutoImportBatch>(
      `/api/atlas/auto-import/batches/${encodeURIComponent(batchId)}`,
      validators.batch,
      { signal },
    ),
  retryBatch: (batchId: string) =>
    requestJson<AutoImportBatch>(
      `/api/atlas/auto-import/batches/${encodeURIComponent(batchId)}/retry`,
      validators.batch,
      jsonPost(),
    ),
  latestBatch: (scope, signal) => {
    const parameters = new URLSearchParams({ scope });
    return requestNullableJson<AutoImportBatch>(
      `/api/atlas/auto-import/batches/latest?${parameters}`,
      validators.batch,
      { signal },
    );
  },
  promoteBatch: (batchId: string, request: BatchPromotionRequest) =>
    requestJson<AutoImportBatch>(
      `/api/atlas/auto-import/batches/${encodeURIComponent(batchId)}/promote`,
      validators.batch,
      jsonPost(request),
    ),
  featureEvidence: (featureId, scope, asOf, signal) => {
    const parameters = new URLSearchParams({ scope, as_of: asOf });
    return requestJson<AutoImportEvidencePage>(
      `/api/atlas/auto-import/evidence/${encodeURIComponent(featureId)}?${parameters}`,
      validators.evidence,
      { signal },
    );
  },
};
