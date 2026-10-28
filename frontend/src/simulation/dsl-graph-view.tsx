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
  effects: string[];
}

export interface GraphCoupling {
  id: string;
  source: string;
  target: string;
  formula: string;
  sync_interval_days?: number | null;
  line: number;
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
  couplings: GraphCoupling[];
  aggregate?: GraphAggregate | null;
}

export interface GraphEdge {
  id: string;
  from_id: string;
  to_id: string;
  kind: 'parent_child' | 'coupling';
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

export interface PopulationAllocation {
  path: string;
  parent_path?: string | null;
  node_id: string;
  node_kind: string;
  vertical_slice: string;
  graph_group: string;
  probability: number;
  expected_represented: number;
  actual_represented: number;
  expected_simulated: number;
  actual_simulated: number;
  seed: number;
}

export interface ProgramGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  slices: GraphSlice[];
  orphan_agents: string[];
  population_paths: PopulationAllocation[];
  default_run_id?: string | null;
}

interface GraphViewOptions {
  onViewCode: (line: number) => void;
}

interface PoolAgent {
  id: string;
  household_id: string;
  agent_type: string;
  roles: string[];
  traits: Record<string, string | number | boolean>;
  states: Record<string, string | number | boolean>;
}

interface PoolSummary {
  total_represented_pool: number;
  simulated_pool_sample: number;
  weight_per_simulated_agent: number;
  unassigned_required_roles: number;
}

interface GraphOccurrence {
  key: string;
  path: string;
  slice: string;
  node: GraphNode;
  parentKey?: string;
  childCount: number;
  inheritedRoles: string[];
  allocation?: PopulationAllocation;
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

const formatted = (value?: number | null, digits = 0): string =>
  value === undefined || value === null
    ? '—'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);

const syncLabel = (days?: number | null): string => {
  if (!days) return 'immediate';
  if (days === 1) return 'daily sync';
  if (days === 7) return 'weekly sync';
  return `${days}-day sync`;
};

const occurrenceId = (slice: string, path: string): string => `${slice}::${path}`;

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
  const allocations = new Map(graph.population_paths.map((row) => [row.path, row]));
  const result: GraphOccurrence[] = [];
  for (const slice of graph.slices.filter((item) => visibleSlices.has(item.id))) {
    const sliceCompositions = graph.nodes.filter(
      (node) => node.node_kind === 'composition' && node.vertical_slice === slice.id,
    );
    const roots = sliceCompositions.filter((node) =>
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
      const childIds = allChildIds.filter((id) => nodes.get(id)?.node_kind !== 'agent');
      const agentLeaves = allChildIds.filter((id) => nodes.get(id)?.node_kind === 'agent');
      result.push({
        key,
        path,
        slice: inheritedSlice,
        node,
        parentKey,
        childCount: childIds.length,
        inheritedRoles,
        allocation: allocations.get(path),
        agentLeaves,
      });
      if (!expandedPaths.has(key) || visited.has(node.id)) return;
      const nextVisited = new Set(visited).add(node.id);
      for (const childId of childIds) {
        const child = nodes.get(childId);
        if (!child || child.node_kind === 'agent') continue;
        if (child.node_kind === 'composition' && child.vertical_slice !== inheritedSlice) continue;
        const childRoles =
          node.node_kind === 'archetype'
            ? node.roles_exposed.map((role) => role.id)
            : node.node_kind === 'agent'
              ? [...inheritedRoles, ...node.roles_exposed.map((role) => role.id)]
              : [];
        visit(child, `${path}>${child.id}`, key, inheritedSlice, childRoles, nextVisited);
      }
    };
    for (const root of roots) visit(root, root.id, undefined, slice.id, [], new Set());
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
    occurrence.node.level,
    occurrence.slice,
    occurrence.path,
    ...occurrenceRoleNames(occurrence),
    ...occurrence.node.actions.map((action) => action.id),
  ]
    .join(' ')
    .toLowerCase()
    .includes(normalized);
};

const layoutFlow = (
  occurrences: GraphOccurrence[],
  graph: ProgramGraph,
  selectedPath: string | undefined,
  query: string,
  roleFilter: string,
  expandedPaths: Set<string>,
  onSelect: (path: string) => void,
  onToggle: (path: string) => void,
  onRole: (role: string) => void,
  poolAgents: PoolAgent[],
): { nodes: DslFlowNode[]; edges: Edge[]; laneWidth: number } => {
  const laneWidth = 360;
  const laneGap = 72;
  const flowNodes: DslFlowNode[] = [];
  const flowEdges: Edge[] = [];
  const slices = ['Physical', 'Media', 'Conglomerate', 'Financial'].filter((slice) =>
    occurrences.some((item) => item.slice === slice),
  );
  const selectedNodeId = occurrences.find((item) => item.path === selectedPath)?.node.id;
  for (const [sliceIndex, slice] of slices.entries()) {
    const values = occurrences.filter((item) => item.slice === slice);
    const layout = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    layout.setGraph({ rankdir: 'TB', ranksep: 52, nodesep: 28, marginx: 12, marginy: 58 });
    for (const value of values) layout.setNode(value.key, { width: 306, height: 300 });
    for (const value of values) {
      if (value.parentKey && values.some((candidate) => candidate.key === value.parentKey)) {
        layout.setEdge(value.parentKey, value.key);
      }
    }
    dagre.layout(layout);
    const offset = sliceIndex * (laneWidth + laneGap);
    const ordered = [...values].sort((left, right) => {
      const leftPoint = layout.node(left.key) as { x: number; y: number };
      const rightPoint = layout.node(right.key) as { x: number; y: number };
      return leftPoint.y - rightPoint.y || leftPoint.x - rightPoint.x;
    });
    for (const [order, occurrence] of ordered.entries()) {
      const highlighted = matches(occurrence, query, roleFilter);
      flowNodes.push({
        id: occurrence.key,
        type: 'dslNode',
        position: { x: offset + (laneWidth - 306) / 2, y: 64 + order * 330 },
        draggable: false,
        selectable: true,
        zIndex: highlighted || occurrence.path === selectedPath ? 20 : 1,
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
          assignedCount: poolAgents.filter((agent) =>
            Object.keys(occurrence.node.role_targets).some((role) => agent.roles.includes(role)),
          ).length,
        },
      });
      if (
        occurrence.parentKey &&
        values.some((candidate) => candidate.key === occurrence.parentKey)
      ) {
        flowEdges.push({
          id: `${occurrence.parentKey}->${occurrence.key}`,
          source: occurrence.parentKey,
          target: occurrence.key,
          type: 'smoothstep',
          className: 'parent-child',
        });
      }
    }
  }
  void graph;
  return { nodes: flowNodes, edges: flowEdges, laneWidth };
};

const DslNodeCard = ({ data }: NodeProps<DslFlowNode>): ReactNode => {
  const { occurrence } = data;
  const node = occurrence.node;
  return (
    <article
      className={`dsl-react-node nopan nowheel${data.selected ? ' selected' : ''}${data.highlighted ? ' highlighted' : ''}${data.dimmed ? ' dimmed' : ''}`}
      data-graph-node={node.id}
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
      <strong>{node.id}</strong>
      <small>{occurrence.slice}</small>
      {node.also_used_in.length > 1 && (
        <p className="dsl-shared">also used in: {node.also_used_in.join(', ')}</p>
      )}
      {node.inherits_from && <p>inherits {node.inherits_from}</p>}
      <dl>
        <div>
          <dt>Role demand</dt>
          <dd>
            {formatted(Object.values(node.role_targets).reduce((sum, value) => sum + value, 0))}
          </dd>
        </div>
        <div>
          <dt>Assigned sample</dt>
          <dd>{formatted(data.assignedCount)}</dd>
        </div>
        <div>
          <dt>Entities</dt>
          <dd>
            {formatted(node.entity_count)} {node.entity_unit ?? ''}
          </dd>
        </div>
      </dl>
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
        <p>Subtree roles: {node.subtree_role_count}</p>
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
          {data.expanded ? 'Collapse subtree' : `Expand ${occurrence.childCount} children`}
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
  poolAgents: PoolAgent[];
  poolSummary?: PoolSummary;
}

const GraphComponent = ({
  graph,
  cacheStatus,
  onViewCode,
  poolAgents,
  poolSummary,
}: GraphComponentProps): ReactNode => {
  const { fitView } = useReactFlow();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string>();
  const [sliceFilter, setSliceFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [auxiliaryExpanded, setAuxiliaryExpanded] = useState<Set<string>>(new Set());
  const [poolOpen, setPoolOpen] = useState(false);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });

  useEffect(() => {
    if (!graph) return;
    setExpandedPaths(allExpandablePaths(graph));
    setSelectedPath(undefined);
  }, [graph]);

  const primarySlices = useMemo(
    () =>
      graph?.slices.filter((slice) => slice.group === 'main' || slice.group === 'coupled') ?? [],
    [graph],
  );
  const auxiliarySlices = useMemo(
    () =>
      graph?.slices.filter(
        (slice) =>
          slice.group === 'lab' || slice.group === 'allocation' || slice.group === 'orphan',
      ) ?? [],
    [graph],
  );
  const visibleSlices = useMemo(() => {
    const ids = new Set(primarySlices.map((slice) => slice.id));
    for (const id of auxiliaryExpanded) ids.add(id);
    if (sliceFilter) return new Set(ids.has(sliceFilter) ? [sliceFilter] : []);
    return ids;
  }, [primarySlices, auxiliaryExpanded, sliceFilter]);
  const occurrences = useMemo(
    () => (graph ? buildOccurrences(graph, visibleSlices, expandedPaths) : []),
    [graph, visibleSlices, expandedPaths],
  );
  const matching = useMemo(
    () => occurrences.filter((item) => matches(item, searchQuery, roleFilter)),
    [occurrences, searchQuery, roleFilter],
  );
  const selected = occurrences.find((item) => item.path === selectedPath);
  const roles = useMemo(
    () => [...new Set(graph?.nodes.flatMap((node) => roleNames(node)) ?? [])].sort(),
    [graph],
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
      graph
        ? layoutFlow(
            occurrences,
            graph,
            selectedPath,
            searchQuery,
            roleFilter,
            expandedPaths,
            setSelectedPath,
            onToggle,
            onRole,
            poolAgents,
          )
        : { nodes: [], edges: [], laneWidth: 330 },
    [
      graph,
      occurrences,
      selectedPath,
      searchQuery,
      roleFilter,
      expandedPaths,
      onToggle,
      onRole,
      poolAgents,
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
  const allocation = selected?.allocation;
  const filteredRoleRows = roleFilter
    ? graph.nodes.flatMap((candidate) =>
        candidate.roles_exposed
          .filter((role) => role.id === roleFilter)
          .map((role) => `${candidate.id}: ${role.actions.join(', ') || 'no actions'}`),
      )
    : [];
  const selectedRoles = node ? Object.keys(node.role_targets) : [];
  const visiblePoolAgents = poolAgents
    .filter(
      (agent) =>
        (!roleFilter || agent.roles.includes(roleFilter)) &&
        (!selectedRoles.length || selectedRoles.some((role) => agent.roles.includes(role))),
    )
    .slice(0, 24);
  const rootNode = graph.nodes.find((candidate) => candidate.id === graph.default_run_id);

  return (
    <div className="dsl-react-graph" data-rendered-nodes={flow.nodes.length}>
      <section className="dsl-system-banner" aria-label="Petraterrium system root">
        <strong>{rootNode?.id ?? 'Petraterrium'}</strong>
        <span>One agent pool · four sectors · agent-mediated interactions</span>
      </section>
      <section className="dsl-pool-node" aria-label="Global agent pool">
        <button type="button" onClick={() => setPoolOpen((open) => !open)}>
          <strong>Pool</strong>
          <span>
            {formatted(poolSummary?.total_represented_pool ?? 6_999_999_999)} represented ·{' '}
            {formatted(poolSummary?.simulated_pool_sample ?? 0)} sampled · weight{' '}
            {formatted(poolSummary?.weight_per_simulated_agent ?? 0, 2)}
          </span>
          <small>
            Required-role gaps {formatted(poolSummary?.unassigned_required_roles ?? 0)} · click to
            inspect sampled people
          </small>
        </button>
        {poolOpen && (
          <div className="dsl-pool-agents">
            {visiblePoolAgents.length ? (
              visiblePoolAgents.map((agent) => (
                <article key={agent.id}>
                  <strong>{agent.id}</strong>
                  <span>{agent.household_id}</span>
                  <small>{agent.roles.join(' · ')}</small>
                </article>
              ))
            ) : (
              <p>Run the system to inspect sampled pool agents for this role filter.</p>
            )}
          </div>
        )}
      </section>
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
          Vertical slice
          <select
            aria-label="Vertical slice"
            value={sliceFilter}
            onChange={(event) => setSliceFilter(event.target.value)}
          >
            <option value="">All main slices</option>
            {[...primarySlices, ...auxiliarySlices].map((slice) => (
              <option key={slice.id} value={slice.id}>
                {slice.id}
              </option>
            ))}
          </select>
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
      <div className="dsl-auxiliary-groups">
        {auxiliarySlices.map((slice) => (
          <details key={slice.id} open={auxiliaryExpanded.has(slice.id)}>
            <summary
              onClick={(event) => {
                event.preventDefault();
                setAuxiliaryExpanded((current) => {
                  const next = new Set(current);
                  next.has(slice.id) ? next.delete(slice.id) : next.add(slice.id);
                  return next;
                });
              }}
            >
              {slice.id} · {slice.node_count}
            </summary>
          </details>
        ))}
      </div>
      <div className="dsl-graph-legend" aria-label="Graph legend">
        <span>
          <i className="solid" />
          Parent/child composition
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
              graph.nodes
                .flatMap((candidate) => candidate.roles_exposed)
                .flatMap((role) =>
                  role.actions.map(
                    (action) =>
                      [
                        `${role.id}:${action}`,
                        `${role.id} → pool agent · ${action} · tick cadence`,
                      ] as const,
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
        >
          <div className="dsl-react-lanes">
            {['Physical', 'Media', 'Conglomerate', 'Financial']
              .filter((slice) => visibleSlices.has(slice))
              .map((slice, index) => (
                <div
                  key={slice}
                  style={{ left: index * (flow.laneWidth + 72), width: flow.laneWidth }}
                >
                  <strong>{slice}</strong>
                </div>
              ))}
          </div>
          <ReactFlow
            nodes={flow.nodes}
            edges={flow.edges}
            nodeTypes={{ dslNode: DslNodeCard }}
            nodesDraggable={false}
            nodesConnectable={false}
            panOnDrag={[0]}
            zoomOnDoubleClick={false}
            onViewportChange={setViewport}
            fitView
            minZoom={0.08}
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
              <p>Open its DSL declarations, roles, outputs, and couplings here.</p>
            </div>
          ) : (
            <>
              <header>
                <span>{label(node.level)}</span>
                <h3>{node.id}</h3>
                <p>
                  {selected?.slice} · line {node.line}
                </p>
                <button type="button" onClick={() => onViewCode(node.line)}>
                  View in code
                </button>
              </header>
              {roleFilter && (
                <DetailSection title={`${roleFilter} across program`}>
                  <ul>
                    {filteredRoleRows.map((row) => (
                      <li key={row}>{row}</li>
                    ))}
                  </ul>
                </DetailSection>
              )}
              <DetailSection title="Population distribution">
                {allocation ? (
                  <ul>
                    <li>Probability {formatted(allocation.probability, 6)}</li>
                    <li>Expected simulated {formatted(allocation.expected_simulated, 2)}</li>
                    <li>Actual sampled allocation {formatted(allocation.actual_simulated)}</li>
                    <li>Expected represented {formatted(allocation.expected_represented, 2)}</li>
                    <li>Actual represented {formatted(allocation.actual_represented)}</li>
                    <li>Seed {allocation.seed}</li>
                    <li>Path {allocation.path}</li>
                  </ul>
                ) : undefined}
              </DetailSection>
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
              <DetailSection title="Couplings">
                {node.couplings.length ? (
                  <ul>
                    {node.couplings.map((coupling) => (
                      <li key={coupling.id}>
                        <strong>{coupling.id}</strong> · {coupling.source} → {coupling.target} ·{' '}
                        {syncLabel(coupling.sync_interval_days)}
                        <br />
                        {coupling.formula}
                      </li>
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
  private poolAgents: PoolAgent[] = [];
  private poolSummary?: PoolSummary;
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

  setPoolAgents(agents: PoolAgent[], summary: PoolSummary): void {
    this.poolAgents = agents;
    this.poolSummary = summary;
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
          poolAgents={this.poolAgents}
          poolSummary={this.poolSummary}
        />
      </ReactFlowProvider>,
    );
    requestAnimationFrame(() => {
      this.host.dataset.renderMs = (performance.now() - started).toFixed(1);
    });
  }
}
