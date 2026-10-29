import dagre from '@dagrejs/dagre';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { createRoot, type Root } from 'react-dom/client';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

export interface GraphRoleSource {
  kind: string;
  owner: string;
  line: number;
}

export interface GraphRoleExposure {
  id: string;
  actions: string[];
  decisions: string[];
  conditions: string[];
  leader: boolean;
  count?: number | null;
  sources: GraphRoleSource[];
}

export interface GraphDecision {
  id: string;
  branches: Array<{ action: string; probability: string; condition?: string | null }>;
}

export interface GraphAction {
  id: string;
  aggregate: string;
  duration: string;
  target?: string | null;
  effects: string[];
}

export interface GraphAggregate {
  id: string;
  inputs: Array<{
    id: string;
    default: number;
    minimum: number;
    maximum: number;
    invalidate_threshold: number;
  }>;
  valid_for_days: number;
}

export interface GraphNode {
  id: string;
  display_name?: string | null;
  members?: Array<{ id: string; line: number }>;
  node_kind: string;
  vertical_slice: string;
  graph_group: string;
  level: string;
  parent_id?: string | null;
  parent_ids: string[];
  also_used_in: string[];
  inherits_from?: string | null;
  weight?: number | null;
  distribution_probability?: number | null;
  expected_represented?: number | null;
  actual_represented?: number | null;
  expected_simulated?: number | null;
  actual_simulated?: number | null;
  represented_count?: number | null;
  entity_count?: number | null;
  entity_unit?: string | null;
  role_targets: Record<string, number>;
  agent_pool?: string | null;
  exemplar_households?: number | null;
  stratum?: string | null;
  heterogeneity: number;
  distribution_status: string;
  provenance?: string | null;
  clock_minutes: number;
  sync_up_minutes?: number | null;
  exemplar_people?: number | null;
  instances_represented?: number | null;
  city_population_share?: number | null;
  city_exemplar_count?: number | null;
  represented_households?: number | null;
  convergence_status?: string | null;
  cache_version?: number | null;
  simulated_count?: number | null;
  line: number;
  cached: boolean;
  sync_interval_days?: number | null;
  places: string[];
  roles_exposed: GraphRoleExposure[];
  subtree_role_count: number;
  subtree_roles: string[];
  roles_used: string[];
  parameters: Record<string, number>;
  states: string[];
  traits: string[];
  initial: string[];
  decisions: GraphDecision[];
  actions: GraphAction[];
  outputs: string[];
  aggregate?: GraphAggregate | null;
}

export interface GraphEdge {
  id: string;
  from_id: string;
  to_id: string;
  kind: 'parent_child';
  weight?: number | null;
  sync_interval_days?: number | null;
  line: number;
  formula?: string | null;
}

export interface GraphSlice {
  id: string;
  group: string;
  collapsed: boolean;
  node_count: number;
}

export interface ProgramGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  slices: GraphSlice[];
  orphan_agents: string[];
  default_run_id?: string | null;
}

interface GraphViewOptions {
  onViewCode: (line: number) => void;
}

interface ExemplarPlan {
  id: string;
  city_id: string;
  stratum: string;
  households: number;
  people: number;
  represented_people: number;
  instances_represented: number;
  city_population_share: number;
  distribution_status: string;
  provenance: string;
}

interface CityPlan {
  city_id: string;
  represented_people: number;
  represented_households: number;
  exemplars: ExemplarPlan[];
  convergence: { converged: boolean; cap_hit: boolean };
  mixture_metrics: Record<
    string,
    {
      mean: number;
      standard_deviation: number;
      p10: number;
      p50: number;
      p90: number;
      tail_rate: number;
    }
  >;
}

interface ExemplarSystemPlan {
  total_represented_pool: number;
  total_represented_households: number;
  total_real_neighbourhood_instances: number;
  total_exemplars: number;
  cities: CityPlan[];
}

interface ExemplarCacheEntry {
  version: number;
  learning_ticks: number;
  learning_seconds: number;
  agents: Array<{
    id: string;
    household_id: string;
    roles: string[];
    residence_path: string[];
    age: number;
    money: number;
    stress: number;
  }>;
  relationships: Array<{ kind: string; source_id: string; target_id: string }>;
}

interface GraphOccurrence {
  key: string;
  path: string;
  slice: string;
  node: GraphNode;
  parentKey?: string;
  childCount: number;
  inheritedRoles: string[];
  agentLeaves: string[];
}

interface DslNodeData extends Record<string, unknown> {
  occurrence: GraphOccurrence;
  selected: boolean;
  highlighted: boolean;
  dimmed: boolean;
  expanded: boolean;
  onSelect: (path: string) => void;
  onToggle: (path: string) => void;
  onRole: (role: string) => void;
  assignedCount: number;
}

type DslFlowNode = Node<DslNodeData, 'dslNode'>;

const label = (value: string): string =>
  value.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');

const sliceRoots = (graph: ProgramGraph, sliceId: string): GraphNode[] => {
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

const sliceTabLabel = (graph: ProgramGraph, sliceId: string): string => {
  const root = sliceRoots(graph, sliceId)[0];
  return root ? verticalLevelLabel(root.level) : sliceId;
};

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

const uniqueBy = <Value,>(values: Value[], key: (value: Value) => string): Value[] => [
  ...new Map(values.map((value) => [key(value), value])).values(),
];

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

const buildVerticalLevelGraph = (graph: ProgramGraph): ProgramGraph => {
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

const formatted = (value?: number | null, digits = 0): string =>
  value === undefined || value === null
    ? '—'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);

const occurrenceId = (slice: string, path: string): string => `${slice}::${path}`;

const occurrencePathName = (node: GraphNode): string => node.display_name ?? node.id;

const buildOccurrences = (
  graph: ProgramGraph,
  visibleSlices: Set<string>,
  expandedPaths: Set<string>,
): GraphOccurrence[] => {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  for (const edge of graph.edges.filter((edge) => edge.kind === 'parent_child')) {
    const values = children.get(edge.from_id) ?? [];
    values.push(edge.to_id);
    children.set(edge.from_id, values);
  }
  const result: GraphOccurrence[] = [];
  for (const slice of graph.slices.filter((item) => visibleSlices.has(item.id))) {
    const sliceNodes = graph.nodes.filter((node) => node.vertical_slice === slice.id);
    const roots = sliceNodes.filter((node) =>
      node.parent_ids.every((parentId) => nodes.get(parentId)?.vertical_slice !== slice.id),
    );
    const visit = (
      node: GraphNode,
      path: string,
      parentKey: string | undefined,
      inheritedSlice: string,
      inheritedRoles: string[],
      visited: Set<string>,
    ): void => {
      const key = occurrenceId(inheritedSlice, path);
      const allChildIds = children.get(node.id) ?? [];
      const childIds = allChildIds.filter((id) => nodes.get(id)?.vertical_slice === inheritedSlice);
      result.push({
        key,
        path,
        slice: inheritedSlice,
        node,
        parentKey,
        childCount: childIds.length,
        inheritedRoles,
        agentLeaves: [],
      });
      if (!expandedPaths.has(key) || visited.has(node.id)) return;
      const nextVisited = new Set(visited).add(node.id);
      for (const childId of childIds) {
        const child = nodes.get(childId);
        if (!child || child.vertical_slice !== inheritedSlice) continue;
        visit(
          child,
          `${path}>${occurrencePathName(child)}`,
          key,
          inheritedSlice,
          inheritedRoles,
          nextVisited,
        );
      }
    };
    for (const root of roots) {
      visit(root, occurrencePathName(root), undefined, slice.id, [], new Set());
    }
    if (slice.group === 'orphan') {
      for (const id of graph.orphan_agents) {
        const node = nodes.get(id);
        if (node) visit(node, node.id, undefined, slice.id, [], new Set());
      }
    }
  }
  return result;
};

const allExpandablePaths = (graph: ProgramGraph): Set<string> => {
  const visible = new Set(graph.slices.map((slice) => slice.id));
  const provisional = buildOccurrences(graph, visible, new Set());
  const roots = new Set(provisional.map((item) => item.key));
  let expanded = roots;
  for (let index = 0; index < graph.nodes.length + 2; index += 1) {
    const next = buildOccurrences(graph, visible, expanded);
    const nextSet = new Set(next.filter((item) => item.childCount > 0).map((item) => item.key));
    if (nextSet.size === expanded.size) break;
    expanded = nextSet;
  }
  return new Set(
    [...expanded].filter((key) => {
      const path = key.split('::', 2)[1] ?? '';
      return path.split('>').length <= 4;
    }),
  );
};

const roleNames = (node: GraphNode): string[] => [
  ...node.roles_exposed.map((role) => role.id),
  ...node.roles_used,
];

const occurrenceRoleNames = (occurrence: GraphOccurrence): string[] => [
  ...roleNames(occurrence.node),
  ...occurrence.inheritedRoles,
];

const matches = (occurrence: GraphOccurrence, query: string, roleFilter: string): boolean => {
  const roleMatch = !roleFilter || occurrenceRoleNames(occurrence).includes(roleFilter);
  if (!roleMatch) return false;
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [
    occurrence.node.id,
    occurrence.node.display_name ?? '',
    ...(occurrence.node.members ?? []).map((member) => member.id),
    occurrence.node.level,
    occurrence.node.stratum ?? '',
    occurrence.node.provenance ?? '',
    occurrence.slice,
    occurrence.path,
    ...occurrenceRoleNames(occurrence),
    ...occurrence.node.actions.map((action) => action.id),
  ]
    .join(' ')
    .toLowerCase()
    .includes(normalized);
};

interface FlowLayout {
  nodes: DslFlowNode[];
  edges: Edge[];
}

const layoutFlow = (
  occurrences: GraphOccurrence[],
  selectedPath: string | undefined,
  query: string,
  roleFilter: string,
  expandedPaths: Set<string>,
  onSelect: (path: string) => void,
  onToggle: (path: string) => void,
  onRole: (role: string) => void,
): FlowLayout => {
  const nodeWidth = 306;
  const nodeHeight = 260;
  const layout = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  layout.setGraph({
    rankdir: 'TB',
    ranksep: 110,
    nodesep: 44,
    edgesep: 24,
    marginx: 30,
    marginy: 30,
    ranker: 'network-simplex',
  });
  for (const occurrence of occurrences) {
    layout.setNode(occurrence.key, { width: nodeWidth, height: nodeHeight });
  }
  for (const occurrence of occurrences) {
    if (occurrence.parentKey && occurrences.some((item) => item.key === occurrence.parentKey)) {
      layout.setEdge(occurrence.parentKey, occurrence.key);
    }
  }
  dagre.layout(layout);
  const selectedNodeId = occurrences.find((item) => item.path === selectedPath)?.node.id;
  const nodes = occurrences.map((occurrence): DslFlowNode => {
    const point = layout.node(occurrence.key) as { x: number; y: number };
    const highlighted = matches(occurrence, query, roleFilter);
    return {
      id: occurrence.key,
      type: 'dslNode',
      position: { x: point.x - nodeWidth / 2, y: point.y - nodeHeight / 2 },
      draggable: false,
      selectable: true,
      zIndex: highlighted || occurrence.path === selectedPath ? 20 : 5,
      data: {
        occurrence,
        selected: occurrence.path === selectedPath,
        highlighted:
          (Boolean(query.trim() || roleFilter) && highlighted) ||
          (Boolean(selectedNodeId) && occurrence.node.id === selectedNodeId),
        dimmed: Boolean(query.trim() || roleFilter) && !highlighted,
        expanded: expandedPaths.has(occurrence.key),
        onSelect,
        onToggle,
        onRole,
        assignedCount: 0,
      },
    };
  });
  const visibleKeys = new Set(nodes.map((node) => node.id));
  const edges = occurrences
    .filter(
      (occurrence) =>
        occurrence.parentKey &&
        visibleKeys.has(occurrence.key) &&
        visibleKeys.has(occurrence.parentKey),
    )
    .map((occurrence): Edge => ({
      id: `${occurrence.parentKey}->${occurrence.key}`,
      source: occurrence.parentKey!,
      target: occurrence.key,
      type: 'smoothstep',
      className: 'parent-child',
    }));
  return { nodes, edges };
};

const DslNodeCard = ({ data }: NodeProps<DslFlowNode>): ReactNode => {
  const { occurrence } = data;
  const node = occurrence.node;
  const nodeName = node.display_name ?? node.id;
  return (
    <article
      className={`dsl-react-node nopan${data.selected ? ' selected' : ''}${data.highlighted ? ' highlighted' : ''}${data.dimmed ? ' dimmed' : ''}`}
      data-graph-node={nodeName}
      data-graph-path={occurrence.path}
      data-graph-slice={occurrence.slice}
      onClick={() => data.onSelect(occurrence.path)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') data.onSelect(occurrence.path);
      }}
      role="button"
      tabIndex={0}
    >
      <Handle type="target" position={Position.Top} />
      <header>
        <span>{label(node.level)}</span>
        <div>{node.cached && <b className="badge">CACHE</b>}</div>
      </header>
      <strong>{nodeName}</strong>
      <small>{label(occurrence.slice)}</small>
      {node.members?.length ? <p>{node.members.length} declared entities</p> : undefined}
      {node.also_used_in.length > 1 && (
        <p className="dsl-shared">also used in: {node.also_used_in.join(', ')}</p>
      )}
      {node.inherits_from && <p>inherits {node.inherits_from}</p>}
      {node.node_kind === 'exemplar' ? (
        <dl>
          <div>
            <dt>Households</dt>
            <dd>{formatted(node.exemplar_households)}</dd>
          </div>
          <div>
            <dt>People</dt>
            <dd>{formatted(node.exemplar_people)}</dd>
          </div>
          <div>
            <dt>Instances</dt>
            <dd>{formatted(node.instances_represented, 2)}</dd>
          </div>
          <div>
            <dt>City weight</dt>
            <dd>{formatted((node.city_population_share ?? 0) * 100, 3)}%</dd>
          </div>
          <div>
            <dt>Cache</dt>
            <dd>{node.cache_version ? `v${node.cache_version}` : 'not learned'}</dd>
          </div>
        </dl>
      ) : node.city_exemplar_count ? (
        <dl>
          <div>
            <dt>Represented</dt>
            <dd>{formatted(node.represented_count)}</dd>
          </div>
          <div>
            <dt>Households</dt>
            <dd>{formatted(node.represented_households)}</dd>
          </div>
          <div>
            <dt>Exemplars</dt>
            <dd>{formatted(node.city_exemplar_count)}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{node.convergence_status}</dd>
          </div>
          <div>
            <dt>Instances</dt>
            <dd>{formatted(node.instances_represented, 2)}</dd>
          </div>
        </dl>
      ) : (
        <dl>
          <div>
            <dt>Role demand</dt>
            <dd>
              {formatted(Object.values(node.role_targets).reduce((sum, value) => sum + value, 0))}
            </dd>
          </div>
          <div>
            <dt>Entities</dt>
            <dd>
              {formatted(node.entity_count)} {node.entity_unit ?? ''}
            </dd>
          </div>
        </dl>
      )}
      {node.stratum && <p>Stratum: {node.stratum}</p>}
      {node.provenance && (
        <p>
          {node.distribution_status} · {node.provenance}
        </p>
      )}
      <p>
        <span>Roles exposed:</span>{' '}
        {node.roles_exposed.length
          ? node.roles_exposed.slice(0, 3).map((role, index) => (
              <button
                key={role.id}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  data.onRole(role.id);
                }}
              >
                {index > 0 ? ' · ' : ''}
                {role.id} ({role.actions.slice(0, 2).join(', ') || 'label'})
              </button>
            ))
          : 'no leader declared in DSL'}
      </p>
      {occurrence.agentLeaves.length > 0 && (
        <p>Pool agent type: {occurrence.agentLeaves.join(', ')}</p>
      )}
      {node.roles_exposed.length === 0 && node.subtree_role_count > 0 && (
        <p>Roles below: {node.subtree_role_count}</p>
      )}
      {occurrence.inheritedRoles.length > 0 && (
        <p>Roles inherited: {occurrence.inheritedRoles.join(', ')}</p>
      )}
      {occurrence.childCount > 0 && (
        <button
          className="dsl-collapse"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            data.onToggle(occurrence.key);
          }}
        >
          {data.expanded ? 'Hide lower levels' : 'Show next level'}
        </button>
      )}
      <Handle type="source" position={Position.Bottom} />
    </article>
  );
};

const DetailSection = ({ title, children }: { title: string; children?: ReactNode }): ReactNode => (
  <section>
    <h4>{title}</h4>
    {children ?? <p>None declared in DSL</p>}
  </section>
);

interface GraphComponentProps {
  graph?: ProgramGraph;
  cacheStatus: Map<string, string>;
  onViewCode: (line: number) => void;
  exemplarPlan?: ExemplarSystemPlan;
  exemplarCache: Record<string, ExemplarCacheEntry>;
}

const GraphComponent = ({
  graph,
  cacheStatus,
  onViewCode,
  exemplarPlan,
  exemplarCache,
}: GraphComponentProps): ReactNode => {
  const { fitView } = useReactFlow();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string>();
  const [activeSlice, setActiveSlice] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [poolOpen, setPoolOpen] = useState(false);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });
  const verticalGraph = useMemo(
    () => (graph ? buildVerticalLevelGraph(graph) : undefined),
    [graph],
  );

  const sliceTabs = useMemo(() => {
    return (graph?.slices ?? [])
      .filter((slice) => slice.group === 'main')
      .map((slice) => {
        const roots = graph ? sliceRoots(graph, slice.id) : [];
        return {
          ...slice,
          label: graph ? sliceTabLabel(graph, slice.id) : slice.id,
          sourceLine: Math.min(...roots.map((root) => root.line), Number.MAX_SAFE_INTEGER),
        };
      })
      .sort((left, right) => left.sourceLine - right.sourceLine || left.id.localeCompare(right.id));
  }, [graph]);
  useEffect(() => {
    if (!verticalGraph) return;
    setExpandedPaths(allExpandablePaths(verticalGraph));
    setSelectedPath(undefined);
    const available = sliceTabs.map((slice) => slice.id);
    setActiveSlice((current) => (available.includes(current) ? current : (available[0] ?? '')));
  }, [verticalGraph, sliceTabs]);
  const visibleSlices = useMemo(() => new Set([activeSlice]), [activeSlice]);
  const baseOccurrences = useMemo(
    () => (verticalGraph ? buildOccurrences(verticalGraph, visibleSlices, expandedPaths) : []),
    [verticalGraph, visibleSlices, expandedPaths],
  );
  const occurrences = baseOccurrences;
  const matching = useMemo(
    () => occurrences.filter((item) => matches(item, searchQuery, roleFilter)),
    [occurrences, searchQuery, roleFilter],
  );
  const selected = occurrences.find((item) => item.path === selectedPath);
  const roles = useMemo(
    () => [...new Set(occurrences.flatMap(occurrenceRoleNames))].sort(),
    [occurrences],
  );
  const onToggle = useCallback((key: string) => {
    setExpandedPaths((current) => {
      const next = new Set(current);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);
  const onRole = useCallback((role: string) => {
    setRoleFilter((current) => (current === role ? '' : role));
  }, []);
  const flow = useMemo(
    () =>
      verticalGraph
        ? layoutFlow(
            occurrences,
            selectedPath,
            searchQuery,
            roleFilter,
            expandedPaths,
            setSelectedPath,
            onToggle,
            onRole,
          )
        : { nodes: [], edges: [] },
    [
      verticalGraph,
      occurrences,
      activeSlice,
      selectedPath,
      searchQuery,
      roleFilter,
      expandedPaths,
      onToggle,
      onRole,
    ],
  );

  useEffect(() => {
    if ((!searchQuery && !roleFilter) || matching.length === 0 || matching.length > 20) return;
    const matches = flow.nodes.filter((node) => node.data.highlighted);
    const frame = requestAnimationFrame(() => {
      void fitView({ nodes: matches, padding: 0.35, maxZoom: 0.9, duration: 0 });
    });
    return () => cancelAnimationFrame(frame);
  }, [fitView, flow.nodes, matching.length, roleFilter, searchQuery]);

  if (!graph?.nodes.length) {
    return (
      <div className="dsl-graph-empty">Graph is unavailable for this DSL — run Validate first.</div>
    );
  }

  const node = selected?.node;
  const filteredRoleRows = roleFilter
    ? (verticalGraph?.nodes
        .filter((candidate) => candidate.vertical_slice === activeSlice)
        .flatMap((candidate) =>
          candidate.roles_exposed
            .filter((role) => role.id === roleFilter)
            .map((role) => `${candidate.id}: ${role.actions.join(', ') || 'no actions'}`),
        ) ?? [])
    : [];
  const visibleExemplars = (exemplarPlan?.cities ?? [])
    .flatMap((city) => city.exemplars)
    .filter(
      (exemplar) =>
        !searchQuery ||
        `${exemplar.id} ${exemplar.city_id} ${exemplar.stratum}`
          .toLowerCase()
          .includes(searchQuery.toLowerCase()),
    )
    .slice(0, 50);
  const rootNode = graph.nodes.find((candidate) => candidate.id === graph.default_run_id);
  const selectedMemberIds = new Set((node?.members ?? []).map((member) => member.id));
  const selectedCities = (exemplarPlan?.cities ?? []).filter((city) =>
    selectedMemberIds.has(city.city_id),
  );
  const selectedExemplars =
    node?.level === 'neighbourhood'
      ? (exemplarPlan?.cities ?? []).flatMap((city) => city.exemplars)
      : selectedCities.flatMap((city) => city.exemplars);

  return (
    <div className="dsl-react-graph" data-rendered-nodes={flow.nodes.length}>
      <section className="dsl-system-banner" aria-label="Petraterrium system root">
        <strong>{rootNode?.id ?? 'Petraterrium'}</strong>
        <span>Weighted neighbourhood exemplars · cached vertical composition</span>
      </section>
      <section className="dsl-pool-node" aria-label="Logical population summary">
        <button type="button" onClick={() => setPoolOpen((open) => !open)}>
          <strong>Logical population</strong>
          <span>
            {formatted(exemplarPlan?.total_represented_pool ?? 6_999_999_999)} represented ·{' '}
            {formatted(exemplarPlan?.cities.length ?? 0)} cities ·{' '}
            {formatted(exemplarPlan?.total_exemplars ?? 0)} exemplars
          </span>
          <small>
            {formatted(exemplarPlan?.total_real_neighbourhood_instances ?? 0)} real neighbourhoods ·{' '}
            click to inspect exemplar weights
          </small>
        </button>
        {poolOpen && (
          <div className="dsl-pool-agents">
            {visibleExemplars.length ? (
              visibleExemplars.map((exemplar) => (
                <article key={exemplar.id}>
                  <strong>{exemplar.id}</strong>
                  <span>
                    {exemplar.households} households · {exemplar.people} people
                  </span>
                  <small>
                    {exemplar.stratum} · {formatted(exemplar.instances_represented, 2)} instances ·{' '}
                    {formatted(exemplar.city_population_share * 100, 3)}%
                  </small>
                </article>
              ))
            ) : (
              <p>Run the system to inspect weighted neighbourhood exemplars.</p>
            )}
          </div>
        )}
      </section>
      <nav className="dsl-slice-tabs" role="tablist" aria-label="Vertical slices">
        {sliceTabs.map((slice) => (
          <button
            key={slice.id}
            type="button"
            role="tab"
            aria-selected={activeSlice === slice.id}
            onClick={() => {
              setActiveSlice(slice.id);
              setSelectedPath(undefined);
              setSearchQuery('');
              setRoleFilter('');
            }}
          >
            <strong>{slice.label}</strong>
            <small>{slice.node_count} nodes</small>
          </button>
        ))}
      </nav>
      <div className="dsl-graph-controls">
        <label>
          Search nodes, paths, or roles
          <input
            aria-label="Search nodes or roles"
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="president, trader, Toronto"
          />
        </label>
        <label>
          Exposes role
          <select
            aria-label="Exposes role"
            value={roleFilter}
            onChange={(event) => setRoleFilter(event.target.value)}
          >
            <option value="">All roles</option>
            {roles.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <output className="dsl-match-count" aria-live="polite">
          {searchQuery || roleFilter
            ? `${matching.length} nodes match`
            : `${occurrences.length} paths`}
        </output>
      </div>
      <div className="dsl-graph-legend" aria-label="Graph legend">
        <span>
          <i className="solid" />
          Vertical level transition
        </span>
        <span>Sector demand reads from the Pool</span>
        <span className="badge">CACHE</span>Cached aggregate available
        <span className="badge leader">1</span>Leader role
        <span className="badge mass">R</span>Mass role
      </div>
      <details className="dsl-agent-interactions">
        <summary>Agent interactions</summary>
        <ul>
          {[
            ...new Map(
              (verticalGraph?.nodes ?? [])
                .filter((candidate) => candidate.vertical_slice === activeSlice)
                .flatMap((candidate) =>
                  candidate.roles_exposed.flatMap((role) =>
                    role.actions.map((actionId) => {
                      const action = candidate.actions.find((value) => value.id === actionId);
                      const cadence = candidate.sync_up_minutes ?? candidate.clock_minutes;
                      return [
                        `${role.id}:${actionId}`,
                        `${role.id} → ${action?.target ?? 'self'} · ${actionId} · every ${cadence} minutes`,
                      ] as const;
                    }),
                  ),
                ),
            ).values(),
          ]
            .slice(0, 30)
            .map((interaction) => (
              <li key={interaction}>{interaction}</li>
            ))}
        </ul>
      </details>
      <div className="dsl-graph-body">
        <div
          className="dsl-react-flow"
          data-viewport-x={viewport.x}
          data-viewport-y={viewport.y}
          data-viewport-zoom={viewport.zoom}
          data-active-slice={activeSlice}
          onWheelCapture={(event) => event.preventDefault()}
        >
          <ReactFlow
            key={activeSlice}
            nodes={flow.nodes}
            edges={flow.edges}
            nodeTypes={{ dslNode: DslNodeCard }}
            nodesDraggable={false}
            nodesConnectable={false}
            panOnDrag={[0]}
            panOnScroll={false}
            preventScrolling
            zoomOnPinch
            zoomOnScroll
            zoomOnDoubleClick={false}
            onViewportChange={setViewport}
            fitView
            minZoom={0.015}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} size={1} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable />
          </ReactFlow>
          {(searchQuery || roleFilter) && matching.length === 0 && (
            <div className="dsl-graph-empty dsl-no-match">
              No nodes match '{searchQuery || roleFilter}'
            </div>
          )}
        </div>
        <aside className="dsl-graph-detail" data-graph-detail>
          {!node ? (
            <div className="dsl-graph-detail-empty">
              <strong>Select a node</strong>
              <p>Open its DSL declarations, roles, outputs, and cache state here.</p>
            </div>
          ) : (
            <>
              <header>
                <span>{label(node.level)}</span>
                <h3>{node.display_name ?? node.id}</h3>
                <p>
                  {selected?.slice} · line {node.line}
                </p>
                <button type="button" onClick={() => onViewCode(node.line)}>
                  View in code
                </button>
              </header>
              {node.members?.length ? (
                <DetailSection title="Declared entities in this level">
                  <ul>
                    {node.members.map((member) => (
                      <li key={member.id}>
                        <button type="button" onClick={() => onViewCode(member.line)}>
                          <strong>{member.id}</strong>
                          <small>line {member.line}</small>
                        </button>
                      </li>
                    ))}
                  </ul>
                </DetailSection>
              ) : undefined}
              {selectedExemplars.length ? (
                <DetailSection title="Detailed exemplar households">
                  <ul>
                    {selectedExemplars.map((exemplar) => {
                      const cache = exemplarCache[exemplar.id];
                      return (
                        <li key={exemplar.id}>
                          <strong>{exemplar.id}</strong> · {exemplar.households} households ·{' '}
                          {exemplar.people} people · cache{' '}
                          {cache ? `v${cache.version}` : 'not learned'}
                        </li>
                      );
                    })}
                  </ul>
                </DetailSection>
              ) : undefined}
              {selectedCities.length ? (
                <DetailSection title="City mixture distributions">
                  {selectedCities.map((city) => (
                    <section key={city.city_id}>
                      <h5>{city.city_id}</h5>
                      <ul>
                        {Object.entries(city.mixture_metrics).map(([metric, values]) => (
                          <li key={`${city.city_id}:${metric}`}>
                            <strong>{label(metric)}</strong> · mean {formatted(values.mean, 3)} · sd{' '}
                            {formatted(values.standard_deviation, 3)} · p10{' '}
                            {formatted(values.p10, 3)} · p50 {formatted(values.p50, 3)} · p90{' '}
                            {formatted(values.p90, 3)} · tail {formatted(values.tail_rate * 100, 3)}
                            %
                          </li>
                        ))}
                      </ul>
                      <p>
                        {city.exemplars.length} exemplars · {formatted(city.represented_people)}{' '}
                        represented people
                      </p>
                    </section>
                  ))}
                </DetailSection>
              ) : undefined}
              {roleFilter && (
                <DetailSection title={`${roleFilter} across program`}>
                  <ul>
                    {filteredRoleRows.map((row) => (
                      <li key={row}>{row}</li>
                    ))}
                  </ul>
                </DetailSection>
              )}
              <DetailSection title="State / Parameters">
                {Object.keys(node.parameters).length ||
                node.states.length ||
                node.traits.length ||
                node.initial.length ? (
                  <ul>
                    {Object.entries(node.parameters).map(([id, value]) => (
                      <li key={id}>
                        {id} = {value}
                      </li>
                    ))}
                    {node.states.map((value) => (
                      <li key={`state:${value}`}>{value}</li>
                    ))}
                    {node.traits.map((value) => (
                      <li key={`trait:${value}`}>trait {value}</li>
                    ))}
                    {node.initial.map((value) => (
                      <li key={`initial:${value}`}>{value}</li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Decisions">
                {node.decisions.length ? (
                  <ul>
                    {node.decisions.map((decision) => (
                      <li key={decision.id}>
                        <strong>{decision.id}</strong>:{' '}
                        {decision.branches
                          .map(
                            (branch) =>
                              `${branch.action} (${branch.probability}${branch.condition ? ` if ${branch.condition}` : ''})`,
                          )
                          .join(' · ')}
                      </li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Actions">
                {node.actions.length ? (
                  <ul>
                    {node.actions.map((action) => (
                      <li key={action.id}>
                        <strong>{action.id}</strong> · {action.duration}
                        <br />
                        {action.effects.join(' · ')}
                      </li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Roles exposed">
                {node.roles_exposed.length ? (
                  <ul>
                    {node.roles_exposed.map((role) => (
                      <li key={role.id}>
                        <button type="button" onClick={() => onRole(role.id)}>
                          <strong>{role.id}</strong> ·{' '}
                          {role.leader ? `leader (${role.count ?? 1})` : 'mass'} ·{' '}
                          {role.actions.join(', ') || 'no actions'}
                          <small>
                            {role.sources
                              .map((source) => `${source.kind}: ${source.owner}`)
                              .join(' · ')}
                            {role.conditions.length ? ` · when ${role.conditions.join(' · ')}` : ''}
                          </small>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Places">
                {node.places.length ? (
                  <ul>
                    {node.places.map((place) => (
                      <li key={place}>{place}</li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Outputs">
                {node.outputs.length ? (
                  <ul>
                    {node.outputs.map((output) => (
                      <li key={output}>{output}</li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
              <DetailSection title="Aggregate / Cache">
                {node.aggregate ? (
                  <ul>
                    <li>
                      {node.aggregate.id} · valid {node.aggregate.valid_for_days} days ·{' '}
                      {cacheStatus.get(node.id) ?? 'not evaluated this session'}
                    </li>
                    {node.aggregate.inputs.map((input) => (
                      <li key={input.id}>
                        {input.id} = {input.default} · range {input.minimum}..{input.maximum} ·
                        invalidate ±{input.invalidate_threshold}
                      </li>
                    ))}
                  </ul>
                ) : undefined}
              </DetailSection>
            </>
          )}
        </aside>
      </div>
    </div>
  );
};

export class DslGraphView {
  private graph?: ProgramGraph;
  private exemplarPlan?: ExemplarSystemPlan;
  private exemplarCache: Record<string, ExemplarCacheEntry> = {};
  private readonly root: Root;
  private readonly cacheStatus = new Map<string, string>();

  constructor(
    private readonly host: HTMLElement,
    private readonly options: GraphViewOptions,
  ) {
    this.host.className = 'dsl-graph-view';
    this.root = createRoot(host);
  }

  destroy(): void {
    this.root.unmount();
  }

  setGraph(graph?: ProgramGraph | null): void {
    this.graph = graph ?? undefined;
    if (!this.host.hidden) this.render();
  }

  setCacheStatus(id: string, status: string): void {
    this.cacheStatus.set(id, status);
    if (!this.host.hidden) this.render();
  }

  setExemplarPlan(plan: ExemplarSystemPlan, cache: Record<string, ExemplarCacheEntry>): void {
    this.exemplarPlan = plan;
    this.exemplarCache = cache;
    if (!this.host.hidden) this.render();
  }

  render(): void {
    const started = performance.now();
    this.root.render(
      <ReactFlowProvider>
        <GraphComponent
          graph={this.graph}
          cacheStatus={this.cacheStatus}
          onViewCode={this.options.onViewCode}
          exemplarPlan={this.exemplarPlan}
          exemplarCache={this.exemplarCache}
        />
      </ReactFlowProvider>,
    );
    requestAnimationFrame(() => {
      this.host.dataset.renderMs = (performance.now() - started).toFixed(1);
    });
  }
}
