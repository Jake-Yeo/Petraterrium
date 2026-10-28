import type {
  AutoImportAttemptView,
  AutoImportBatchItemView,
  AutoImportBatchPromotionRequest as GeneratedBatchPromotionRequest,
  AutoImportBatchRequest as GeneratedAutoImportBatchRequest,
  AutoImportBatchSummary as GeneratedAutoImportBatchSummary,
  AutoImportBatchView,
  AutoImportCanonicalValue,
  AutoImportDistributionRequirement,
  AutoImportEstimateInput,
  AutoImportEstimateTraceView,
  AutoImportEvidenceView,
  AutoImportMappingColumn,
  AutoImportMappingOption,
  AutoImportMappingReview,
  AutoImportPromotionRequest as GeneratedPromotionRequest,
  AutoImportRerunRequest as GeneratedRerunRequest,
  AutoImportQueueItemView,
  AutoImportQueuePageView,
  AutoImportResearchSource,
  AutoImportSearchEntry,
  AutoImportTargetView,
  AutoImportVerificationCheck,
} from '../contracts.generated';

export type AutoImportLevel = AutoImportTargetView['level'];
export type AutoImportFieldStatus = AutoImportTargetView['current_status'];
export type AutoImportPriority = AutoImportQueueItemView['priority'];
export type AutoImportEvidenceKind = NonNullable<AutoImportAttemptView['evidence_kind']>;
export type AutoImportAttemptStage = AutoImportAttemptView['stage'];
export type AutoImportBatchStatus = AutoImportBatchView['status'];

export type CanonicalValue = AutoImportCanonicalValue;
export type DistributionRequirement = AutoImportDistributionRequirement;
export type AutoImportTarget = AutoImportTargetView;
export type AutoImportQueueItem = AutoImportQueueItemView;

export type AutoImportQueueQuery = {
  scope: string;
  as_of: string;
  level: AutoImportLevel | 'all';
  feature_id: string;
  search: string;
  sort: 'hierarchy_impact' | 'impact' | 'population';
  priority: AutoImportPriority;
  city_population_threshold: number;
  page: number;
  page_size: number;
};

export type AutoImportQueuePage = AutoImportQueuePageView;
export type MappingOption = AutoImportMappingOption;
export type MappingColumn = AutoImportMappingColumn;
export type VerificationCheck = AutoImportVerificationCheck;
export type ResearchSource = AutoImportResearchSource;
export type ResearchSearchEntry = AutoImportSearchEntry;
export type EstimateInput = AutoImportEstimateInput;
export type EstimateTrace = AutoImportEstimateTraceView;
export type AutoImportAttempt = AutoImportAttemptView;

export type AutoImportSourceInput = {
  urls: string[];
  pasted_text: string;
  files: File[];
};

export type MappingConfirmation = AutoImportMappingReview;
export type PromotionRequest = GeneratedPromotionRequest;
export type RerunRequest = GeneratedRerunRequest;
export type AutoImportBatchRequest = GeneratedAutoImportBatchRequest;
export type BulkSelection = AutoImportBatchRequest['selection'];
export type AutoImportBatchSummary = GeneratedAutoImportBatchSummary;
export type AutoImportBatchItem = AutoImportBatchItemView;
export type AutoImportBatch = AutoImportBatchView;
export type BatchPromotionRequest = GeneratedBatchPromotionRequest;
export type AutoImportEvidencePage = AutoImportEvidenceView;

export type AutoImportClient = {
  queue: (query: AutoImportQueueQuery, signal?: AbortSignal) => Promise<AutoImportQueuePage>;
  start: (
    target: AutoImportTarget,
    input: AutoImportSourceInput,
    scope: string,
  ) => Promise<AutoImportAttempt>;
  attempt: (attemptId: string, signal?: AbortSignal) => Promise<AutoImportAttempt>;
  confirmMapping: (
    attemptId: string,
    confirmation: MappingConfirmation,
  ) => Promise<AutoImportAttempt>;
  continueResearch: (attemptId: string) => Promise<AutoImportAttempt>;
  rerun: (attemptId: string, request: RerunRequest) => Promise<AutoImportAttempt>;
  promote: (attemptId: string, request: PromotionRequest) => Promise<AutoImportAttempt>;
  createBatch: (request: AutoImportBatchRequest) => Promise<AutoImportBatch>;
  batch: (batchId: string, signal?: AbortSignal) => Promise<AutoImportBatch>;
  retryBatch: (batchId: string) => Promise<AutoImportBatch>;
  latestBatch: (scope: string, signal?: AbortSignal) => Promise<AutoImportBatch | null>;
  promoteBatch: (batchId: string, request: BatchPromotionRequest) => Promise<AutoImportBatch>;
  featureEvidence: (
    featureId: string,
    scope: string,
    asOf: string,
    signal?: AbortSignal,
  ) => Promise<AutoImportEvidencePage>;
};

export type AutoImportContext = {
  scope: string;
  asOf: string;
};

export type AutoImportSurfaceOptions = {
  client?: AutoImportClient;
  context: () => AutoImportContext;
  onPromoted?: (attempt: AutoImportAttempt) => void | Promise<void>;
  onBatchPromoted?: (batch: AutoImportBatch) => void | Promise<void>;
  onError?: (message: string) => void;
  pollIntervalMs?: number;
};
