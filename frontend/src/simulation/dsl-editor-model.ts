export type DslEvidenceStatus = 'measured' | 'estimated' | 'fitted' | 'default';

export type DslDurationShape = 'uniform' | 'triangular' | 'lognormal' | 'weibull' | 'empirical';

export interface DslEvidence {
  status: DslEvidenceStatus;
  source: string;
  sourceVersion: string;
  sourceDate?: string | null;
  uncertainty: number;
  reasoning?: string | null;
  source_ids?: string[];
}

export interface DslDurationDistribution {
  min_hours: number;
  median_hours: number;
  max_hours: number;
  shape: DslDurationShape;
  shape_parameters: Record<string, number>;
  evidence: DslEvidence;
}

export interface DslCoefficient {
  id: string;
  name: string;
  value: number;
  evidence: DslEvidence;
}

export interface DslStateThreshold {
  id: string;
  label: string;
  value: number;
}

export interface DslStateDefinition {
  id: string;
  name: string;
  min: number;
  max: number;
  initial: number;
  decay_per_hour: number;
  recovery_per_hour: number;
  thresholds: DslStateThreshold[];
}

export interface DslActionDefinition {
  id: string;
  name: string;
  description: string;
  category: string;
  mode: 'primary' | 'passive';
  priority: number;
  aggregate_statistic_id: string;
  interruptibility: 'interruptible' | 'protected' | 'uninterruptible';
  interruption_outcome: 'defer' | 'cancel';
  emergency_interruptions: string[];
  duration: DslDurationDistribution;
  evidence?: DslEvidence | null;
  formula: string;
  coefficients: DslCoefficient[];
  place_requirements: string[];
  time_requirements: string[];
}

export type DslNodeKind = 'entry' | 'decision' | 'action' | 'terminal' | 'module';

export interface DslTreeNode {
  id: string;
  label: string;
  kind: DslNodeKind;
  action_id?: string | null;
  target_tree_id?: string | null;
}

export interface DslTreeEdge {
  id: string;
  from_node: string;
  to_node: string;
  probability: number;
  formula: string;
  condition: string;
  place_requirements: string[];
  time_requirements: string[];
}

export interface DslDecisionTree {
  id: string;
  name: string;
  entry_node: string;
  nodes: DslTreeNode[];
  edges: DslTreeEdge[];
}

export interface VisualDslDocument {
  schema_version: string;
  version: string;
  tick_hours: number;
  actions: DslActionDefinition[];
  states: DslStateDefinition[];
  trees: DslDecisionTree[];
}

export interface DslValidationIssue {
  path: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface DslDocumentDiff {
  path: string;
  before: string;
  after: string;
}
