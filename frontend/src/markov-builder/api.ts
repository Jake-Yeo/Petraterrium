import type {
  ChainDraft,
  ChainProposalResult,
  ChainValidationResult,
  ConfirmationResult,
  MarkovBuilderApi,
  PipelineTransitionEstimate,
  TransitionProbabilityResearchRequest,
} from './types';

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function errorMessage(body: unknown, status: number): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null && 'issues' in detail) {
      const issues = (detail as { issues: unknown }).issues;
      if (Array.isArray(issues) && issues.length) {
        const first = issues[0] as { message?: unknown };
        if (typeof first.message === 'string') return first.message;
      }
    }
  }
  return `Markov builder request failed (${status})`;
}

async function request<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/markov-builder${path}`, json(body));
  } catch {
    throw new Error('Cannot reach the simulation API. Start the backend, then retry.');
  }
  const responseBody: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(responseBody, response.status));
  return responseBody as T;
}

export const markovBuilderApi: MarkovBuilderApi = {
  propose: (text, useLlm) =>
    request<ChainProposalResult>('/proposals', { text, use_llm: useLlm }),
  validate: (draft: ChainDraft) => request<ChainValidationResult>('/validation', draft),
  researchProbability: (researchRequest: TransitionProbabilityResearchRequest) =>
    request<PipelineTransitionEstimate>('/probability-research', researchRequest),
  confirm: (draft: ChainDraft) =>
    request<ConfirmationResult>('/confirm', { draft, user_confirmed: true }),
};
