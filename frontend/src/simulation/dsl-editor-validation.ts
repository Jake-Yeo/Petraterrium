import type {
  DslDecisionTree,
  DslDocumentDiff,
  DslValidationIssue,
  VisualDslDocument,
} from './dsl-editor-model';

const uniqueIssues = (values: string[], path: string, label: string): DslValidationIssue[] => {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates].map((value) => ({
    path,
    message: `${label} ID ${value || '(empty)'} is duplicated.`,
    severity: 'error',
  }));
};

const finite = (value: number): boolean => Number.isFinite(value);

const treeDepthIssues = (tree: DslDecisionTree): DslValidationIssue[] => {
  const adjacency = new Map<string, string[]>();
  for (const edge of tree.edges) {
    adjacency.set(edge.from_node, [...(adjacency.get(edge.from_node) ?? []), edge.to_node]);
  }
  const issues: DslValidationIssue[] = [];
  const visit = (nodeId: string, path: string[], depth: number): void => {
    if (path.includes(nodeId)) {
      issues.push({
        path: `trees.${tree.id}.nodes.${nodeId}`,
        message: `Cycle detected: ${[...path, nodeId].join(' → ')}.`,
        severity: 'error',
      });
      return;
    }
    if (depth > 5) {
      issues.push({
        path: `trees.${tree.id}`,
        message: `Path from ${tree.entry_node} exceeds the maximum depth of five.`,
        severity: 'error',
      });
      return;
    }
    for (const next of adjacency.get(nodeId) ?? []) visit(next, [...path, nodeId], depth + 1);
  };
  visit(tree.entry_node, [], 0);
  return issues;
};

export const validateVisualDsl = (document: VisualDslDocument): DslValidationIssue[] => {
  const issues: DslValidationIssue[] = [];
  if (!document.schema_version.trim()) {
    issues.push({
      path: 'schema_version',
      message: 'Schema version is required.',
      severity: 'error',
    });
  }
  if (!document.version.trim()) {
    issues.push({ path: 'version', message: 'DSL version is required.', severity: 'error' });
  }
  if (!finite(document.tick_hours) || document.tick_hours <= 0 || document.tick_hours > 24) {
    issues.push({
      path: 'tick_hours',
      message: 'Tick hours must be greater than 0 and at most 24.',
      severity: 'error',
    });
  }
  issues.push(
    ...uniqueIssues(
      document.actions.map((action) => action.id),
      'actions',
      'Action',
    ),
  );
  issues.push(
    ...uniqueIssues(
      document.states.map((state) => state.id),
      'states',
      'State',
    ),
  );
  issues.push(
    ...uniqueIssues(
      document.trees.map((tree) => tree.id),
      'trees',
      'Tree',
    ),
  );

  for (const action of document.actions) {
    const path = `actions.${action.id}`;
    const duration = action.duration;
    if (!action.id.trim() || !action.name.trim()) {
      issues.push({ path, message: 'Every action needs an ID and name.', severity: 'error' });
    }
    if (!action.category.trim() || !action.aggregate_statistic_id.trim()) {
      issues.push({
        path,
        message: 'Every action needs a time category and aggregate statistic.',
        severity: 'error',
      });
    }
    if (!Number.isInteger(action.priority)) {
      issues.push({
        path: `${path}.priority`,
        message: 'Action priority must be a whole number.',
        severity: 'error',
      });
    }
    const unknownInterruptions = action.emergency_interruptions.filter(
      (actionId) => !document.actions.some((candidate) => candidate.id === actionId),
    );
    if (unknownInterruptions.length) {
      issues.push({
        path: `${path}.emergency_interruptions`,
        message: `Unknown emergency actions: ${unknownInterruptions.join(', ')}.`,
        severity: 'error',
      });
    }
    if (
      !finite(duration.min_hours) ||
      !finite(duration.median_hours) ||
      !finite(duration.max_hours) ||
      duration.min_hours < 0 ||
      duration.min_hours > duration.median_hours ||
      duration.median_hours > duration.max_hours
    ) {
      issues.push({
        path: `${path}.duration`,
        message: 'Duration must satisfy 0 ≤ minimum ≤ median ≤ maximum.',
        severity: 'error',
      });
    }
    if (
      duration.min_hours === duration.median_hours &&
      duration.median_hours === duration.max_hours
    ) {
      issues.push({
        path: `${path}.duration`,
        message: 'A single fixed duration is invalid. Provide a duration range.',
        severity: 'error',
      });
    }
    if (!duration.evidence.source.trim() || !duration.evidence.sourceVersion.trim()) {
      issues.push({
        path: `${path}.duration.evidence`,
        message: 'Duration source and source version are required.',
        severity: 'error',
      });
    }
    if (duration.shape === 'lognormal' && !(duration.shape_parameters.sigma > 0)) {
      issues.push({
        path: `${path}.duration.shape_parameters.sigma`,
        message: 'Lognormal duration requires a positive sigma.',
        severity: 'error',
      });
    }
    if (Object.values(duration.shape_parameters).some((value) => !finite(value))) {
      issues.push({
        path: `${path}.duration.shape_parameters`,
        message: 'Shape parameters must be finite.',
        severity: 'error',
      });
    }
    if (
      !finite(duration.evidence.uncertainty) ||
      duration.evidence.uncertainty < 0 ||
      duration.evidence.uncertainty > 1
    ) {
      issues.push({
        path: `${path}.duration.evidence.uncertainty`,
        message: 'Duration uncertainty must be between 0 and 1.',
        severity: 'error',
      });
    }
    if (!action.formula.trim()) {
      issues.push({
        path: `${path}.formula`,
        message: 'Action formula is required.',
        severity: 'error',
      });
    }
    issues.push(
      ...uniqueIssues(
        action.coefficients.map((coefficient) => coefficient.id),
        `${path}.coefficients`,
        'Coefficient',
      ),
    );
    for (const coefficient of action.coefficients) {
      if (!coefficient.name.trim() || !finite(coefficient.value)) {
        issues.push({
          path: `${path}.coefficients.${coefficient.id}`,
          message: 'Each coefficient needs a name and finite value.',
          severity: 'error',
        });
      }
      if (!coefficient.evidence.source.trim() || !coefficient.evidence.sourceVersion.trim()) {
        issues.push({
          path: `${path}.coefficients.${coefficient.id}.evidence`,
          message: 'Coefficient source and source version are required.',
          severity: 'error',
        });
      }
      if (
        !finite(coefficient.evidence.uncertainty) ||
        coefficient.evidence.uncertainty < 0 ||
        coefficient.evidence.uncertainty > 1
      ) {
        issues.push({
          path: `${path}.coefficients.${coefficient.id}.evidence.uncertainty`,
          message: 'Coefficient uncertainty must be between 0 and 1.',
          severity: 'error',
        });
      }
    }
    if (duration.max_hours > document.tick_hours) {
      issues.push({
        path: `${path}.duration.max_hours`,
        message: `This action may span multiple ${document.tick_hours}-hour ticks. The sampled occurrence must remain in progress until its remaining duration reaches zero.`,
        severity: 'warning',
      });
    }
  }

  for (const state of document.states) {
    const path = `states.${state.id}`;
    if (!state.id.trim() || !state.name.trim()) {
      issues.push({ path, message: 'Every state needs an ID and name.', severity: 'error' });
    }
    if (!finite(state.min) || !finite(state.max) || state.min >= state.max) {
      issues.push({ path, message: 'State minimum must be below its maximum.', severity: 'error' });
    }
    if (!finite(state.initial) || state.initial < state.min || state.initial > state.max) {
      issues.push({
        path: `${path}.initial`,
        message: 'Initial state value must be inside the state range.',
        severity: 'error',
      });
    }
    issues.push(
      ...uniqueIssues(
        state.thresholds.map((threshold) => threshold.id),
        `${path}.thresholds`,
        'Threshold',
      ),
    );
    for (const threshold of state.thresholds) {
      if (threshold.value < state.min || threshold.value > state.max) {
        issues.push({
          path: `${path}.thresholds.${threshold.id}`,
          message: `Threshold ${threshold.label} must be inside the state range.`,
          severity: 'error',
        });
      }
    }
  }

  const actionIds = new Set(document.actions.map((action) => action.id));
  const treeIds = new Set(document.trees.map((tree) => tree.id));
  for (const tree of document.trees) {
    const path = `trees.${tree.id}`;
    const nodeIds = new Set(tree.nodes.map((node) => node.id));
    issues.push(
      ...uniqueIssues(
        tree.nodes.map((node) => node.id),
        `${path}.nodes`,
        'Node',
      ),
    );
    issues.push(
      ...uniqueIssues(
        tree.edges.map((edge) => edge.id),
        `${path}.edges`,
        'Edge',
      ),
    );
    if (!nodeIds.has(tree.entry_node)) {
      issues.push({
        path: `${path}.entry_node`,
        message: 'Entry node must reference a node in this tree.',
        severity: 'error',
      });
    }
    for (const node of tree.nodes) {
      if (node.kind === 'action' && (!node.action_id || !actionIds.has(node.action_id))) {
        issues.push({
          path: `${path}.nodes.${node.id}.action_id`,
          message: 'Action node must reference an existing action.',
          severity: 'error',
        });
      }
      if (node.kind === 'module' && (!node.target_tree_id || !treeIds.has(node.target_tree_id))) {
        issues.push({
          path: `${path}.nodes.${node.id}.target_tree_id`,
          message: 'Module node must reference an existing tree.',
          severity: 'error',
        });
      }
      const outgoing = tree.edges.filter((edge) => edge.from_node === node.id);
      if (node.kind !== 'terminal' && outgoing.length === 0) {
        issues.push({
          path: `${path}.nodes.${node.id}`,
          message: `Node ${node.label} is a dead end. Mark it terminal or add an outgoing edge.`,
          severity: 'error',
        });
      }
      if (node.kind === 'terminal' && outgoing.length > 0) {
        issues.push({
          path: `${path}.nodes.${node.id}`,
          message: `Terminal node ${node.label} cannot have outgoing edges.`,
          severity: 'error',
        });
      }
      if (outgoing.length > 0) {
        const total = outgoing.reduce((sum, edge) => sum + edge.probability, 0);
        if (Math.abs(total - 1) > 0.000001) {
          issues.push({
            path: `${path}.nodes.${node.id}.outgoing`,
            message: `Outgoing probabilities from ${node.label} total ${total.toFixed(3)} instead of 1.`,
            severity: 'error',
          });
        }
      }
    }
    for (const edge of tree.edges) {
      if (!nodeIds.has(edge.from_node) || !nodeIds.has(edge.to_node)) {
        issues.push({
          path: `${path}.edges.${edge.id}`,
          message: 'Edge endpoints must reference nodes in this tree.',
          severity: 'error',
        });
      }
      if (!finite(edge.probability) || edge.probability < 0 || edge.probability > 1) {
        issues.push({
          path: `${path}.edges.${edge.id}.probability`,
          message: 'Edge probability must be between 0 and 1.',
          severity: 'error',
        });
      }
      if (!edge.formula.trim()) {
        issues.push({
          path: `${path}.edges.${edge.id}.formula`,
          message: 'Edge formula is required.',
          severity: 'error',
        });
      }
      if (!edge.condition.trim()) {
        issues.push({
          path: `${path}.edges.${edge.id}.condition`,
          message: 'Edge condition is required.',
          severity: 'error',
        });
      }
    }
    issues.push(...treeDepthIssues(tree));
  }
  return issues;
};

const flatten = (
  value: unknown,
  path = '',
  output = new Map<string, string>(),
): Map<string, string> => {
  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, `${path}[${index}]`, output));
    if (value.length === 0) output.set(path, '[]');
    return output;
  }
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value);
    entries.forEach(([key, item]) => flatten(item, path ? `${path}.${key}` : key, output));
    if (entries.length === 0) output.set(path, '{}');
    return output;
  }
  output.set(path, JSON.stringify(value));
  return output;
};

export const diffVisualDsl = (
  original: VisualDslDocument,
  draft: VisualDslDocument,
): DslDocumentDiff[] => {
  const before = flatten(original);
  const after = flatten(draft);
  const paths = new Set([...before.keys(), ...after.keys()]);
  return [...paths]
    .filter((path) => before.get(path) !== after.get(path))
    .sort()
    .map((path) => ({
      path,
      before: before.get(path) ?? '(not present)',
      after: after.get(path) ?? '(removed)',
    }));
};
