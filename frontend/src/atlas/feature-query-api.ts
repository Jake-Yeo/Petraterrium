import type {
  FeatureFilter,
  FeatureInheritanceView,
  JoinedFilterClient,
  JoinedFilterEstimate,
  PlaceSelector,
} from './joined-filter';

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function placeOptions(search = ''): Promise<PlaceSelector[]> {
  const query = new URLSearchParams({ search, limit: '25' });
  const response = await jsonRequest<{ places: PlaceSelector[] }>(
    `/atlas/feature-query/places?${query}`,
  );
  return response.places;
}

export const featureQueryClient: JoinedFilterClient = {
  featureInheritance: (selector: PlaceSelector, featureId: string) =>
    jsonRequest<FeatureInheritanceView>(
      '/atlas/feature-query/inheritance',
      post({ selector, feature_id: featureId }),
    ),
  estimateJoinedFilters: (selector: PlaceSelector, filters: FeatureFilter[]) =>
    jsonRequest<JoinedFilterEstimate>(
      '/atlas/feature-query/joined',
      post({ selector, filters }),
    ),
  searchPlaces: (search: string) => placeOptions(search),
};
