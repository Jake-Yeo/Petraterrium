import { request, validator } from '../api';
import type {
  AtlasOverview,
  AtlasScopes,
  Backbone,
  ChoiceEvidenceCatalog,
  CityDetail,
  HierarchyOverview,
  ImportCommit,
  ImportHistory,
  ImportMetadata,
  ImportPreview,
  ImportVersion,
  MappingConfirmation,
  Promotion,
  SourceCatalog,
  SourceFetch,
  UniversalFeatureOverview,
  ValidationReport,
} from '../contracts.generated';

const post = (data: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});

export const atlasApi = {
  scopes: () => request('/atlas/scopes', validator<AtlasScopes>('AtlasScopes')),
  draft: (id: string, scope: string) =>
    request(
      `/atlas/imports/${id}?scope=${encodeURIComponent(scope)}`,
      validator<ImportPreview>('ImportPreview'),
    ),
  overview: (query: URLSearchParams) =>
    request(`/atlas/overview?${query}`, validator<AtlasOverview>('AtlasOverview')),
  city: (id: number, query: URLSearchParams) =>
    request(`/atlas/cities/${id}?${query}`, validator<CityDetail>('CityDetail')),
  backbone: () => request('/atlas/backbone', validator<Backbone>('Backbone'), { method: 'POST' }),
  sources: () => request('/atlas/sources', validator<SourceCatalog>('SourceCatalog')),
  features: () =>
    request('/atlas/features', validator<UniversalFeatureOverview>('UniversalFeatureOverview')),
  hierarchy: (scope: string, asOf: string) =>
    request(
      `/atlas/hierarchy?scope=${encodeURIComponent(scope)}&as_of=${encodeURIComponent(asOf)}`,
      validator<HierarchyOverview>('HierarchyOverview'),
    ),
  choices: (scope: string, asOf: string) =>
    request(
      `/atlas/choice-evidence?scope=${encodeURIComponent(scope)}&as_of=${encodeURIComponent(asOf)}`,
      validator<ChoiceEvidenceCatalog>('ChoiceEvidenceCatalog'),
    ),
  history: (scope: string) =>
    request(
      `/atlas/imports?scope=${encodeURIComponent(scope)}`,
      validator<ImportHistory>('ImportHistory'),
    ),
  preview: (file: File, metadata: ImportMetadata, llm: boolean) => {
    const body = new FormData();
    body.append('file', file);
    body.append('metadata', JSON.stringify(metadata));
    body.append('use_llm', String(llm));
    return request('/atlas/imports/preview', validator<ImportPreview>('ImportPreview'), {
      method: 'POST',
      body,
    });
  },
  fetchSource: (source: string, data: SourceFetch) =>
    request(
      `/atlas/sources/${encodeURIComponent(source)}/fetch`,
      validator<ImportPreview>('ImportPreview'),
      post(data),
    ),
  validate: (id: string, scope: string, data: MappingConfirmation) =>
    request(
      `/atlas/imports/${id}/validate?scope=${encodeURIComponent(scope)}`,
      validator<ValidationReport>('ValidationReport'),
      post(data),
    ),
  commit: (id: string, scope: string, data: ImportCommit) =>
    request(
      `/atlas/imports/${id}/commit?scope=${encodeURIComponent(scope)}`,
      validator<ImportVersion>('ImportVersion'),
      post(data),
    ),
  promote: (id: string, scope: string, data: Promotion) =>
    request(
      `/atlas/imports/${id}/promote?scope=${encodeURIComponent(scope)}`,
      validator<ImportVersion>('ImportVersion'),
      post(data),
    ),
};
