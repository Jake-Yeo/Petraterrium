import type { VisualDslDocument } from './dsl-editor-model';
import type {
  CachedPipelineVersion,
  CachedPipelineVersionDiff,
} from './cached-pipeline-default-inspector';

interface EditableDslRevision {
  document_hash: string;
  document: VisualDslDocument;
}

interface EditableDslPreview {
  preview_hash: string;
  validation: { valid: boolean; issues: Array<{ message: string }> };
}

interface PipelineRunSummary {
  run_id: string;
  version: number;
  previous_run_id: string | null;
  active: boolean;
  run_hash: string;
}

interface PipelineRunList {
  active_run_id: string | null;
  runs: PipelineRunSummary[];
}

interface PipelineSource {
  source_id: string;
  title: string;
  publisher: string;
  source_kind: string;
  source_date: string;
  population: string;
  place_label: string;
  language: string;
  engine: string;
  url: string;
}

interface PipelineDuration {
  minimum_hours: number;
  median_hours: number;
  maximum_hours: number;
  shape: string;
}

interface PipelineRun {
  run_id: string;
  version: number;
  previous_run_id: string | null;
  created_at: string;
  completed_at: string;
  run_hash: string;
  search_log: Array<{
    sequence: number;
    action_ids: string[];
    place_label: string;
    language: string;
    engine: string;
    source_kind: string;
    query_or_source: string;
    searched_at: string;
    outcome: string;
    candidate_ids: string[];
    detail: string;
  }>;
  candidates: Array<{
    candidate_id: string;
    action_id: string;
    evidence_kind: 'measured' | 'estimated';
    duration: PipelineDuration;
    source_provenance: PipelineSource[];
    denominator: string;
    reasoning: string;
  }>;
  chosen_results: Array<{
    action_id: string;
    evidence_kind: 'measured' | 'estimated';
    duration: PipelineDuration;
    candidate_ids: string[];
    source_provenance: PipelineSource[];
    target_place_label: string;
    reasoning: string;
    assumptions: string[];
    uncertainty: { method: string; limitations: string[] };
  }>;
  snapshot: {
    content_hash: string;
    section_counts: Record<string, number>;
  };
}

interface PipelineDiff {
  researched_data: { added: string[]; removed: string[] };
  chosen_data: Array<{ action_id: string; reason: string }>;
  changed_snapshot_sections: string[];
}

async function requestJson<Value>(path: string, init?: RequestInit): Promise<Value> {
  const response = await fetch(`/api${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as Value;
}

export async function loadEditableDsl(): Promise<EditableDslRevision> {
  return requestJson<EditableDslRevision>('/simulation/editable-dsl');
}

export async function confirmEditableDsl(
  expectedActiveHash: string,
  document: VisualDslDocument,
): Promise<EditableDslRevision> {
  const preview = await requestJson<EditableDslPreview>('/simulation/editable-dsl/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_active_hash: expectedActiveHash, document }),
  });
  if (!preview.validation.valid) {
    throw new Error(preview.validation.issues.map((item) => item.message).join('; '));
  }
  return requestJson<EditableDslRevision>('/simulation/editable-dsl/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      expected_active_hash: expectedActiveHash,
      preview_hash: preview.preview_hash,
      document,
      user_confirmed: true,
    }),
  });
}

const durationValues = (duration: PipelineDuration) => [
  { value: 'Minimum', display: `${duration.minimum_hours.toFixed(2)} hours` },
  { value: 'Median', display: `${duration.median_hours.toFixed(2)} hours` },
  { value: 'Maximum', display: `${duration.maximum_hours.toFixed(2)} hours` },
  { value: 'Shape', display: duration.shape },
];

const pipelineDiff = (diff: PipelineDiff | null): CachedPipelineVersionDiff | null => {
  if (!diff) return null;
  return {
    researchedDataChanges: [
      ...diff.researched_data.added.map((item) => `Added ${item}`),
      ...diff.researched_data.removed.map((item) => `Removed ${item}`),
    ],
    chosenDataChanges: diff.chosen_data.map((item) => `${item.action_id}: ${item.reason}`),
    reason:
      diff.changed_snapshot_sections.length > 0
        ? `Changed default sections: ${diff.changed_snapshot_sections.join(', ')}`
        : 'The selected evidence changed without changing a default-state section.',
  };
};

async function pipelineVersion(
  summary: PipelineRunSummary,
  activeRunId: string | null,
): Promise<CachedPipelineVersion> {
  const run = await requestJson<PipelineRun>(`/simulation/default-pipeline/${summary.run_id}`);
  const diff = run.previous_run_id
    ? await requestJson<PipelineDiff>(
        `/simulation/default-pipeline/${run.previous_run_id}/diff/${run.run_id}`,
      )
    : null;
  const selectedCandidates = new Set(
    run.chosen_results.flatMap((result) => result.candidate_ids),
  );
  return {
    id: run.run_id,
    label: `Version ${run.version}`,
    createdAt: run.completed_at,
    isDefault: run.run_id === activeRunId,
    searchLog: run.search_log.map((row) => ({
      id: `${run.run_id}-${row.sequence}`,
      place: row.place_label,
      field: row.action_ids.join(', '),
      sourceTitle: row.query_or_source,
      sourceUrl: row.query_or_source.startsWith('http') ? row.query_or_source : null,
      sourceTier: row.source_kind,
      language: row.language,
      engine: row.engine,
      searchedAt: row.searched_at,
      result: `${row.outcome}: ${row.detail}`,
    })),
    candidates: run.candidates.map((candidate) => ({
      id: candidate.candidate_id,
      place: candidate.source_provenance[0]?.place_label ?? 'Unspecified',
      field: candidate.action_id,
      sourceTitle: candidate.source_provenance.map((source) => source.title).join('; '),
      sourceType: candidate.evidence_kind,
      summary: `${candidate.duration.minimum_hours.toFixed(2)}–${candidate.duration.maximum_hours.toFixed(2)} hours; ${candidate.reasoning}`,
      accepted: selectedCandidates.has(candidate.candidate_id),
      rejectionReason: selectedCandidates.has(candidate.candidate_id)
        ? null
        : 'Retained as a candidate but not selected for this default version.',
    })),
    chosenResults: run.chosen_results.map((result) => ({
      id: `${run.run_id}-${result.action_id}`,
      place: result.target_place_label,
      field: `${result.action_id} duration`,
      unit: 'hours per occurrence',
      denominator: result.source_provenance.map((source) => source.population).join('; '),
      sourceTitle: result.source_provenance.map((source) => source.title).join('; '),
      sourceType: result.evidence_kind,
      sourceDate: result.source_provenance.map((source) => source.source_date).sort().at(-1) ?? '',
      values: durationValues(result.duration),
      reasoning: result.reasoning,
      assumptions: result.assumptions,
      uncertainty: `${result.uncertainty.method}; ${result.uncertainty.limitations.join('; ')}`,
      provenance: result.source_provenance
        .map(
          (source) =>
            `${source.publisher} · ${source.place_label} · ${source.language} · ${source.engine} · ${source.source_id}`,
        )
        .join('; '),
    })),
    defaultSnapshot: {
      hash: run.snapshot.content_hash,
      distributionCount: run.chosen_results.length,
      stateCount: run.snapshot.section_counts.agent_states ?? 0,
      initialAgentCount: run.snapshot.section_counts.initial_population ?? 0,
    },
    diffFromPrevious: pipelineDiff(diff),
  };
}

export async function loadCachedPipelineVersions(): Promise<{
  versions: CachedPipelineVersion[];
  activeRunId: string | null;
}> {
  const listing = await requestJson<PipelineRunList>('/simulation/default-pipeline');
  const versions = await Promise.all(
    listing.runs.map((summary) => pipelineVersion(summary, listing.active_run_id)),
  );
  return { versions, activeRunId: listing.active_run_id };
}

export async function restoreCachedPipelineVersion(versionId: string): Promise<void> {
  const run = await requestJson<PipelineRun>(`/simulation/default-pipeline/${versionId}`);
  await requestJson('/simulation/default-pipeline/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      run_id: versionId,
      expected_run_hash: run.run_hash,
      user_confirmed: true,
    }),
  });
}

export async function activateCachedPipelineVersion(versionId: string): Promise<void> {
  const run = await requestJson<PipelineRun>(`/simulation/default-pipeline/${versionId}`);
  await requestJson(`/simulation/default-pipeline/${versionId}/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_run_hash: run.run_hash, user_confirmed: true }),
  });
  await restoreCachedPipelineVersion(versionId);
}

export async function runDefaultDurationResearch(): Promise<void> {
  await requestJson('/simulation/default-pipeline/duration-research', { method: 'POST' });
}
