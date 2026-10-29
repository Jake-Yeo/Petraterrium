import type { GraphEdge, GraphNode, GraphSlice, ProgramGraph } from './dsl-graph-view';

export interface VerticalNavigationFrame {
  level: string;
  memberIds: string[];
  scopeCityIds: string[];
  breadcrumb: string[];
}

const label = (value: string): string =>
  value.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');

const titleCase = (value: string): string =>
  value.length ? `${value[0].toUpperCase()}${value.slice(1)}` : value;

const verticalLevelLabel = (level: string): string => {
  const normalized = label(level);
  if (level === 'world') return titleCase(normalized);
  if (level === 'municipality') return 'Cities';
  if (normalized.endsWith('y')) return `${titleCase(normalized.slice(0, -1))}ies`;
  if (normalized.endsWith('s')) return titleCase(normalized);
  return `${titleCase(normalized)}s`;
};

const uniqueBy = <Value>(values: Value[], key: (value: Value) => string): Value[] => [
  ...new Map(values.map((value) => [key(value), value])).values(),
];

export const sliceRoots = (graph: ProgramGraph, sliceId: string): GraphNode[] => {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  return graph.nodes
    .filter(
      (node) =>
        node.node_kind === 'composition' &&
        node.graph_group === 'main' &&
        node.vertical_slice === sliceId &&
        node.parent_ids.every((parentId) => nodes.get(parentId)?.vertical_slice !== sliceId),
    )
    .sort((left, right) => left.line - right.line || left.id.localeCompare(right.id));
};

export const sliceTabLabel = (graph: ProgramGraph, sliceId: string): string => {
  const root = sliceRoots(graph, sliceId)[0];
  return root ? verticalLevelLabel(root.level) : sliceId;
};

const aggregateLevelNode = (slice: GraphSlice, level: string, members: GraphNode[]): GraphNode => {
  const first = members[0];
  const syncUpMinutes = members
    .map((member) => member.sync_up_minutes)
    .filter((value): value is number => value !== null && value !== undefined);
  const roleTargets = members.reduce<Record<string, number>>((result, member) => {
    for (const [role, count] of Object.entries(member.role_targets)) {
      result[role] = (result[role] ?? 0) + count;
    }
    return result;
  }, {});
  return {
    ...first,
    id: `__level__${slice.id}__${level}`,
    display_name: verticalLevelLabel(level),
    members: members
      .map((member) => ({ id: member.id, line: member.line }))
      .sort((left, right) => left.line - right.line || left.id.localeCompare(right.id)),
    node_kind: 'vertical_level',
    parent_id: null,
    parent_ids: [],
    also_used_in: [],
    inherits_from: null,
    weight: null,
    distribution_probability: null,
    expected_represented: null,
    actual_represented: null,
    expected_simulated: null,
    actual_simulated: null,
    represented_count: members.reduce((sum, member) => sum + (member.represented_count ?? 0), 0),
    entity_count: members.reduce((sum, member) => sum + (member.entity_count ?? 0), 0),
    role_targets: roleTargets,
    agent_pool: null,
    exemplar_households: null,
    stratum: null,
    heterogeneity: Math.max(...members.map((member) => member.heterogeneity)),
    distribution_status: uniqueBy(
      members.map((member) => member.distribution_status),
      (status) => status,
    ).join(', '),
    provenance: null,
    clock_minutes: Math.min(...members.map((member) => member.clock_minutes)),
    sync_up_minutes: syncUpMinutes.length ? Math.min(...syncUpMinutes) : null,
    simulated_count: members.reduce((sum, member) => sum + (member.simulated_count ?? 0), 0),
    line: Math.min(...members.map((member) => member.line)),
    cached: members.some((member) => member.cached),
    sync_interval_days: null,
    places: uniqueBy(
      members.flatMap((member) => member.places),
      (place) => place,
    ),
    roles_exposed: uniqueBy(
      members.flatMap((member) => member.roles_exposed),
      (role) => role.id,
    ),
    subtree_role_count: new Set(members.flatMap((member) => member.subtree_roles)).size,
    subtree_roles: [...new Set(members.flatMap((member) => member.subtree_roles))],
    roles_used: [...new Set(members.flatMap((member) => member.roles_used))],
    parameters: {},
    states: [...new Set(members.flatMap((member) => member.states))],
    traits: [...new Set(members.flatMap((member) => member.traits))],
    initial: [...new Set(members.flatMap((member) => member.initial))],
    decisions: uniqueBy(
      members.flatMap((member) => member.decisions),
      (decision) => decision.id,
    ),
    actions: uniqueBy(
      members.flatMap((member) => member.actions),
      (action) => action.id,
    ),
    outputs: [...new Set(members.flatMap((member) => member.outputs))],
    aggregate: null,
  };
};

export const buildVerticalLevelGraph = (graph: ProgramGraph): ProgramGraph => {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const originalNodes = new Map(graph.nodes.map((node) => [node.id, node]));
  for (const slice of graph.slices.filter((candidate) => candidate.group === 'main')) {
    const compositions = graph.nodes.filter(
      (node) =>
        node.node_kind === 'composition' &&
        node.graph_group === 'main' &&
        node.vertical_slice === slice.id,
    );
    if (!compositions.length) continue;
    const byLevel = new Map<string, GraphNode[]>();
    for (const composition of compositions) {
      const members = byLevel.get(composition.level) ?? [];
      members.push(composition);
      byLevel.set(composition.level, members);
    }
    const levelNodes = new Map<string, GraphNode>();
    for (const [level, members] of byLevel) {
      const node = aggregateLevelNode(slice, level, members);
      levelNodes.set(level, node);
      nodes.push(node);
    }
    const levelEdges = new Map<string, GraphEdge>();
    for (const edge of graph.edges.filter((candidate) => candidate.kind === 'parent_child')) {
      const parent = originalNodes.get(edge.from_id);
      const child = originalNodes.get(edge.to_id);
      if (
        !parent ||
        !child ||
        parent.node_kind !== 'composition' ||
        child.node_kind !== 'composition' ||
        parent.vertical_slice !== slice.id ||
        child.vertical_slice !== slice.id ||
        parent.level === child.level
      ) {
        continue;
      }
      const id = `${parent.level}->${child.level}`;
      if (!levelEdges.has(id)) {
        levelEdges.set(id, {
          id: `${slice.id}:${id}`,
          from_id: levelNodes.get(parent.level)!.id,
          to_id: levelNodes.get(child.level)!.id,
          kind: 'parent_child',
          line: edge.line,
        });
      }
    }
    edges.push(...levelEdges.values());
  }
  const parents = new Map<string, string[]>();
  for (const edge of edges) {
    const values = parents.get(edge.to_id) ?? [];
    values.push(edge.from_id);
    parents.set(edge.to_id, values);
  }
  for (const node of nodes) {
    node.parent_ids = parents.get(node.id) ?? [];
    node.parent_id = node.parent_ids[0] ?? null;
  }
  return {
    nodes,
    edges,
    slices: graph.slices.filter((slice) => slice.group === 'main'),
    orphan_agents: [],
    default_run_id: null,
  };
};

const orderedSliceLevels = (graph: ProgramGraph, sliceId: string): GraphNode[] => {
  const nodes = graph.nodes.filter((node) => node.vertical_slice === sliceId);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const childByParent = new Map<string, string>();
  for (const edge of graph.edges) {
    if (byId.has(edge.from_id) && byId.has(edge.to_id)) {
      childByParent.set(edge.from_id, edge.to_id);
    }
  }
  const root = nodes.find((node) => node.parent_ids.every((parent) => !byId.has(parent)));
  if (!root) return [];
  const ordered: GraphNode[] = [];
  const visited = new Set<string>();
  let current: GraphNode | undefined = root;
  while (current && !visited.has(current.id)) {
    ordered.push(current);
    visited.add(current.id);
    current = byId.get(childByParent.get(current.id) ?? '');
  }
  return ordered;
};

const compositionChildren = (graph: ProgramGraph, sliceId: string): Map<string, string[]> => {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  for (const edge of graph.edges) {
    const parent = nodes.get(edge.from_id);
    const child = nodes.get(edge.to_id);
    if (
      parent?.node_kind !== 'composition' ||
      child?.node_kind !== 'composition' ||
      parent.graph_group !== 'main' ||
      child.graph_group !== 'main' ||
      parent.vertical_slice !== sliceId ||
      child.vertical_slice !== sliceId
    ) {
      continue;
    }
    const values = children.get(parent.id) ?? [];
    values.push(child.id);
    children.set(parent.id, values);
  }
  return children;
};

const descendantsAtLevel = (
  graph: ProgramGraph,
  sliceId: string,
  rootId: string,
  level: string,
): GraphNode[] => {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const children = compositionChildren(graph, sliceId);
  const pending = [...(children.get(rootId) ?? [])];
  const visited = new Set<string>();
  const matches: GraphNode[] = [];
  while (pending.length) {
    const id = pending.shift()!;
    if (!visited.add(id)) continue;
    const node = nodes.get(id);
    if (!node) continue;
    if (node.level === level) matches.push(node);
    pending.push(...(children.get(id) ?? []));
  }
  return uniqueBy(matches, (node) => node.id).sort(
    (left, right) => left.line - right.line || left.id.localeCompare(right.id),
  );
};

const scopedCityIds = (graph: ProgramGraph, sliceId: string, root: GraphNode): string[] => {
  if (root.level === 'municipality' || root.level === 'city') return [root.id];
  return uniqueBy(
    [
      ...descendantsAtLevel(graph, sliceId, root.id, 'municipality'),
      ...descendantsAtLevel(graph, sliceId, root.id, 'city'),
    ],
    (node) => node.id,
  ).map((node) => node.id);
};

const scopedLevelNode = (
  slice: GraphSlice,
  template: GraphNode,
  members: GraphNode[],
  scopeId: string,
  cityIds: string[],
): GraphNode => {
  const aggregated = members.length ? aggregateLevelNode(slice, template.level, members) : template;
  return {
    ...aggregated,
    id: `__scope__${slice.id}__${scopeId}__${template.level}`,
    display_name: template.display_name,
    members: members.map((member) => ({ id: member.id, line: member.line })),
    scope_city_ids: cityIds,
    node_kind: 'vertical_level',
    parent_id: null,
    parent_ids: [],
    also_used_in: [],
    role_targets: members.length ? aggregated.role_targets : {},
    represented_count: members.length ? aggregated.represented_count : 0,
    entity_count: members.length ? aggregated.entity_count : 0,
    roles_exposed: members.length ? aggregated.roles_exposed : [],
    subtree_role_count: members.length ? aggregated.subtree_role_count : 0,
    subtree_roles: members.length ? aggregated.subtree_roles : [],
    roles_used: members.length ? aggregated.roles_used : [],
    states: members.length ? aggregated.states : [],
    traits: members.length ? aggregated.traits : [],
    initial: members.length ? aggregated.initial : [],
    decisions: members.length ? aggregated.decisions : [],
    actions: members.length ? aggregated.actions : [],
    outputs: members.length ? aggregated.outputs : [],
  };
};

export const buildNestedVerticalGraph = (
  graph: ProgramGraph,
  verticalGraph: ProgramGraph,
  sliceId: string,
  frame: VerticalNavigationFrame,
): ProgramGraph => {
  const slice = graph.slices.find((candidate) => candidate.id === sliceId);
  if (!slice) return verticalGraph;
  const originals = new Map(graph.nodes.map((node) => [node.id, node]));
  const orderedLevels = orderedSliceLevels(verticalGraph, sliceId);
  const levelIndex = orderedLevels.findIndex((node) => node.level === frame.level);
  if (levelIndex < 0) return verticalGraph;
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  for (const memberId of frame.memberIds) {
    const root = originals.get(memberId);
    if (!root || root.level !== frame.level || root.vertical_slice !== sliceId) continue;
    const rootCityIds = scopedCityIds(graph, sliceId, root);
    const cityIds = rootCityIds.length ? rootCityIds : frame.scopeCityIds;
    const instanceId = `__instance__${sliceId}__${root.id}`;
    nodes.push({
      ...root,
      id: instanceId,
      display_name: root.id,
      members: [{ id: root.id, line: root.line }],
      scope_city_ids: cityIds,
      node_kind: 'vertical_instance',
      parent_id: null,
      parent_ids: [],
      also_used_in: [],
    });
    let parentId = instanceId;
    for (const template of orderedLevels.slice(levelIndex + 1)) {
      const members = descendantsAtLevel(graph, sliceId, root.id, template.level);
      const node = scopedLevelNode(slice, template, members, root.id, cityIds);
      node.parent_id = parentId;
      node.parent_ids = [parentId];
      nodes.push(node);
      edges.push({
        id: `${parentId}->${node.id}`,
        from_id: parentId,
        to_id: node.id,
        kind: 'parent_child',
        line: node.line,
      });
      parentId = node.id;
    }
  }
  return {
    nodes,
    edges,
    slices: [{ ...slice, node_count: nodes.length }],
    orphan_agents: [],
    default_run_id: graph.default_run_id,
  };
};
