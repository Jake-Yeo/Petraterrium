import type { DecisionEdgeTemplate, DecisionTreeTemplate } from '../contracts.generated';
import './tree-navigator.css';

export type DecisionTreeStatus = 'draft' | 'ready' | 'blocked' | 'deprecated';
export type DecisionTreeNodeKind = 'decision' | 'action' | 'terminal' | 'module_reference';

export interface DecisionTreeNode {
  id: string;
  label: string;
  kind: DecisionTreeNodeKind;
  description: string;
  target_module_id: string | null;
}

export interface DecisionTreeEdge {
  id: string;
  from_node: string;
  to_node: string;
  label: string;
  condition: string;
  decision_id?: string | null;
  evidence_edge_id?: string | null;
}

export interface DecisionTreeProposalAudit {
  origin: 'ai' | 'deterministic' | 'manual';
  source_id: string;
  source_label: string;
  model: string;
  generated_at: string | null;
  prompt_version: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number | null;
  message: string;
}

export interface DecisionTreeModule {
  id: string;
  version: string;
  name: string;
  description: string;
  entry_node: string;
  nodes: DecisionTreeNode[];
  edges: DecisionTreeEdge[];
  source: string;
  status: DecisionTreeStatus;
  proposal_audit?: DecisionTreeProposalAudit | null;
}

export interface DecisionTreeDefinition {
  id: string;
  version: string;
  name: string;
  description: string;
  root_module_id: string;
  agent_type_ids: string[];
  place_ids: string[];
  source: string;
  status: DecisionTreeStatus;
  proposal_audit?: DecisionTreeProposalAudit | null;
}

export interface DecisionTreeRegistryDefinition {
  version: string;
  trees: DecisionTreeDefinition[];
  modules: DecisionTreeModule[];
}

export interface BrokenModuleReference {
  module_id: string;
  node_id: string;
  target_module_id: string;
}

export interface TreeRegistryValidation {
  valid: boolean;
  issues: Array<{ code: string; path: string; message: string }>;
  broken_references: BrokenModuleReference[];
  reference_cycles: string[][];
  unreachable_nodes: Record<string, string[]>;
}

export interface DecisionTreeNavigatorOptions {
  registry: DecisionTreeRegistryDefinition;
  evidenceTemplates?: DecisionTreeTemplate[];
  validation?: TreeRegistryValidation;
  initialTreeId?: string;
  initialAgentTypeId?: string;
  onSelectionChange?: (treeId: string, moduleId: string, nodeId: string | null) => void;
  renderEdgeEvidence?: (
    host: HTMLElement,
    selection: DecisionTreeEdgeSelection,
  ) => void | Promise<void>;
  confirmRegistry?: (
    registry: DecisionTreeRegistryDefinition,
  ) => Promise<DecisionTreeRegistryResponse>;
}

export interface DecisionTreeEdgeSelection {
  tree: DecisionTreeDefinition;
  module: DecisionTreeModule;
  edge: DecisionTreeEdge;
  evidence: DecisionEdgeTemplate | null;
}

export interface DecisionTreeNavigatorController {
  selectTree(treeId: string): void;
  destroy(): void;
}

interface TreeFilters {
  agentType: string;
  place: string;
  source: string;
  status: string;
}

interface NavigationFrame {
  moduleId: string;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  zoom: number;
  panX: number;
  panY: number;
  collapsed: Set<string>;
}

interface SearchMatch {
  tree: DecisionTreeDefinition;
  module: DecisionTreeModule;
  node: DecisionTreeNode | null;
}

interface ModulePath {
  moduleIds: string[];
  referenceNodeIds: string[];
}

interface Position {
  x: number;
  y: number;
}

export interface DecisionTreeRegistryResponse {
  registry: DecisionTreeRegistryDefinition;
  validation: TreeRegistryValidation;
}

const emptyValidation: TreeRegistryValidation = {
  valid: true,
  issues: [],
  broken_references: [],
  reference_cycles: [],
  unreachable_nodes: {},
};

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const sortedUnique = (values: string[]): string[] =>
  [...new Set(values.filter(Boolean))].sort((left, right) => left.localeCompare(right));

const titleCase = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());

function optionMarkup(values: string[], selected: string, emptyLabel: string): string {
  return [
    `<option value="">${escapeHtml(emptyLabel)}</option>`,
    ...values.map(
      (value) =>
        `<option value="${escapeHtml(value)}"${value === selected ? ' selected' : ''}>${escapeHtml(titleCase(value))}</option>`,
    ),
  ].join('');
}

function proposalAuditMarkup(
  label: string,
  audit: DecisionTreeProposalAudit | null | undefined,
): string {
  if (!audit) {
    return `<section class="tree-node-detail"><span>${escapeHtml(label)}</span><h4>Manual or imported registry entry</h4><p>No proposal audit was attached.</p></section>`;
  }
  const origin = {
    ai: 'AI proposal',
    deterministic: 'Deterministic parser',
    manual: 'Manual confirmation',
  }[audit.origin];
  const generated = audit.generated_at ?? 'Not generated by an AI source';
  const cost =
    audit.estimated_cost_usd === null
      ? 'Not reported'
      : `$${audit.estimated_cost_usd.toFixed(6)}`;
  return `<section class="tree-node-detail"><span>${escapeHtml(label)}</span><h4>${escapeHtml(origin)}</h4><dl><dt>Source</dt><dd>${escapeHtml(audit.source_label)} (${escapeHtml(audit.source_id)})</dd><dt>Model</dt><dd>${escapeHtml(audit.model)}</dd><dt>Generated</dt><dd>${escapeHtml(generated)}</dd><dt>Prompt version</dt><dd>${escapeHtml(audit.prompt_version)}</dd><dt>Tokens</dt><dd>${audit.input_tokens} input · ${audit.output_tokens} output</dd><dt>Estimated cost</dt><dd>${escapeHtml(cost)}</dd></dl><p>${escapeHtml(audit.message)}</p></section>`;
}

function responseError(value: unknown, status: number): string {
  if (value && typeof value === 'object' && 'detail' in value) {
    const detail = (value as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && 'issues' in detail) {
      const issues = (detail as { issues: Array<{ message?: string }> }).issues;
      const message = issues
        .map((issue) => issue.message)
        .filter(Boolean)
        .join('; ');
      if (message) return message;
    }
  }
  return `Could not save the decision module (${status}).`;
}

async function confirmRegistry(
  registry: DecisionTreeRegistryDefinition,
): Promise<DecisionTreeRegistryResponse> {
  const response = await fetch('/api/simulation/decision-trees/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ registry, user_confirmed: true }),
  });
  const value = (await response.json().catch(() => null)) as DecisionTreeRegistryResponse | null;
  if (!response.ok || !value) throw new Error(responseError(value, response.status));
  return value;
}

function treeMatches(tree: DecisionTreeDefinition, filters: TreeFilters): boolean {
  return (
    (!filters.agentType || tree.agent_type_ids.includes(filters.agentType)) &&
    (!filters.place || tree.place_ids.includes(filters.place)) &&
    (!filters.source || tree.source === filters.source) &&
    (!filters.status || tree.status === filters.status)
  );
}

function pathToModule(
  tree: DecisionTreeDefinition,
  targetModuleId: string,
  modules: Map<string, DecisionTreeModule>,
): ModulePath | null {
  const queue: ModulePath[] = [{ moduleIds: [tree.root_module_id], referenceNodeIds: [] }];
  const visited = new Set<string>();
  while (queue.length) {
    const path = queue.shift()!;
    const moduleId = path.moduleIds.at(-1)!;
    if (moduleId === targetModuleId) return path;
    if (visited.has(moduleId)) continue;
    visited.add(moduleId);
    const module = modules.get(moduleId);
    if (!module) continue;
    module.nodes.forEach((node) => {
      if (!node.target_module_id || visited.has(node.target_module_id)) return;
      queue.push({
        moduleIds: [...path.moduleIds, node.target_module_id],
        referenceNodeIds: [...path.referenceNodeIds, node.id],
      });
    });
  }
  return null;
}

function reachableModules(
  tree: DecisionTreeDefinition,
  modules: Map<string, DecisionTreeModule>,
): DecisionTreeModule[] {
  const found = new Set<string>();
  const pending = [tree.root_module_id];
  const result: DecisionTreeModule[] = [];
  while (pending.length) {
    const moduleId = pending.shift()!;
    if (found.has(moduleId)) continue;
    found.add(moduleId);
    const module = modules.get(moduleId);
    if (!module) continue;
    result.push(module);
    pending.push(
      ...module.nodes.flatMap((node) => (node.target_module_id ? [node.target_module_id] : [])),
    );
  }
  return result;
}

function searchRegistry(
  query: string,
  trees: DecisionTreeDefinition[],
  modules: Map<string, DecisionTreeModule>,
  filters: TreeFilters,
): SearchMatch[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [];
  return trees.flatMap((tree) => {
    if (!treeMatches(tree, filters)) return [];
    const results: SearchMatch[] = [];
    for (const module of reachableModules(tree, modules)) {
      if (
        `${tree.name} ${tree.description} ${module.name} ${module.description}`
          .toLocaleLowerCase()
          .includes(needle)
      ) {
        results.push({ tree, module, node: null });
      }
      module.nodes.forEach((node) => {
        if (`${node.label} ${node.description}`.toLocaleLowerCase().includes(needle)) {
          results.push({ tree, module, node });
        }
      });
    }
    return results;
  });
}

function graphLayout(
  module: DecisionTreeModule,
  collapsed: Set<string>,
): {
  positions: Map<string, Position>;
  visible: Set<string>;
  width: number;
  height: number;
} {
  const outgoing = new Map<string, string[]>();
  module.nodes.forEach((node) => outgoing.set(node.id, []));
  module.edges.forEach((edge) => outgoing.get(edge.from_node)?.push(edge.to_node));
  const fullyReachable = new Set<string>();
  const fullQueue = [module.entry_node];
  while (fullQueue.length) {
    const nodeId = fullQueue.shift()!;
    if (fullyReachable.has(nodeId)) continue;
    fullyReachable.add(nodeId);
    fullQueue.push(...(outgoing.get(nodeId) ?? []));
  }
  const visible = new Set<string>();
  const levels = new Map<string, number>([[module.entry_node, 0]]);
  const queue = [module.entry_node];
  while (queue.length) {
    const nodeId = queue.shift()!;
    if (visible.has(nodeId)) continue;
    visible.add(nodeId);
    if (collapsed.has(nodeId)) continue;
    for (const target of outgoing.get(nodeId) ?? []) {
      levels.set(target, Math.max(levels.get(target) ?? 0, (levels.get(nodeId) ?? 0) + 1));
      queue.push(target);
    }
  }
  const deepest = Math.max(0, ...levels.values());
  module.nodes.forEach((node) => {
    if (!fullyReachable.has(node.id)) {
      visible.add(node.id);
      levels.set(node.id, deepest + 1);
    }
  });
  const groups = new Map<number, string[]>();
  module.nodes.forEach((node) => {
    if (!visible.has(node.id)) return;
    const level = levels.get(node.id) ?? 0;
    groups.set(level, [...(groups.get(level) ?? []), node.id]);
  });
  const columns = Math.max(1, groups.size);
  const largestColumn = Math.max(1, ...[...groups.values()].map((items) => items.length));
  const width = Math.max(680, columns * 420 + 100);
  const height = Math.max(430, largestColumn * 150 + 100);
  const positions = new Map<string, Position>();
  [...groups.entries()]
    .sort(([left], [right]) => left - right)
    .forEach(([, nodeIds], column) => {
      nodeIds.sort().forEach((nodeId, row) => {
        positions.set(nodeId, {
          x: 70 + column * 420,
          y: ((row + 1) * height) / (nodeIds.length + 1) - 55,
        });
      });
    });
  return { positions, visible, width, height };
}

function referencePreviewMarkup(
  sourceModule: DecisionTreeModule,
  node: DecisionTreeNode,
  target: DecisionTreeModule,
): string {
  const outgoing = new Set(target.edges.map((edge) => edge.from_node));
  const entry = target.nodes.find((item) => item.id === target.entry_node);
  const exits = target.nodes.filter((item) => item.kind === 'terminal' || !outgoing.has(item.id));
  const previewId = `tree-reference-preview-${sourceModule.id}-${node.id}`;
  return `<aside class="tree-reference-preview" id="${escapeHtml(previewId)}" role="tooltip" data-reference-preview="${escapeHtml(node.id)}"><span>Module preview</span><strong>${escapeHtml(target.name)}</strong><dl><dt>Entry</dt><dd>${escapeHtml(entry?.label ?? target.entry_node)}</dd><dt>Exits</dt><dd>${exits.length ? exits.map((item) => escapeHtml(item.label)).join('<br>') : 'No exit states'}</dd></dl></aside>`;
}

function moduleEditorMarkup(module: DecisionTreeModule): string {
  const nodes = module.nodes
    .map(
      (node) =>
        `<fieldset><legend>${escapeHtml(titleCase(node.kind))} · ${escapeHtml(node.id)}</legend><label><span>Node label</span><input required name="node-label:${escapeHtml(node.id)}" aria-label="Label for node ${escapeHtml(node.id)}" value="${escapeHtml(node.label)}"></label><label><span>Description</span><textarea name="node-description:${escapeHtml(node.id)}" aria-label="Description for node ${escapeHtml(node.id)}">${escapeHtml(node.description)}</textarea></label></fieldset>`,
    )
    .join('');
  const edges = module.edges.length
    ? module.edges
        .map(
          (edge) =>
            `<fieldset><legend>${escapeHtml(edge.from_node)} → ${escapeHtml(edge.to_node)}</legend><label><span>Edge label</span><input name="edge-label:${escapeHtml(edge.id)}" aria-label="Label for edge ${escapeHtml(edge.id)}" value="${escapeHtml(edge.label)}"></label><label><span>Condition</span><textarea name="edge-condition:${escapeHtml(edge.id)}" aria-label="Condition for edge ${escapeHtml(edge.id)}">${escapeHtml(edge.condition)}</textarea></label></fieldset>`,
        )
        .join('')
    : '<p class="tree-empty">This module has no edges.</p>';
  return `<form class="tree-module-editor" data-module-editor aria-label="Edit ${escapeHtml(module.name)} module"><div class="tree-module-editor-heading"><div><span>Shared module</span><h4>Edit ${escapeHtml(module.name)}</h4><p>Changes apply everywhere this module is referenced.</p></div><button type="button" data-cancel-module-edit aria-label="Close module editor">×</button></div><div class="tree-module-editor-meta"><label><span>Module name</span><input required name="module-name" value="${escapeHtml(module.name)}"></label><label><span>Description</span><textarea name="module-description">${escapeHtml(module.description)}</textarea></label></div><div class="tree-module-editor-columns"><section><h5>Nodes</h5>${nodes}</section><section><h5>Edges</h5>${edges}</section></div><div class="tree-module-editor-actions"><output data-module-editor-status aria-live="polite"></output><button type="button" data-cancel-module-edit>Cancel</button><button type="submit">Confirm module changes</button></div></form>`;
}

function editedModule(form: HTMLFormElement, module: DecisionTreeModule): DecisionTreeModule {
  const values = new FormData(form);
  const field = (name: string): string => String(values.get(name) ?? '').trim();
  return {
    ...module,
    name: field('module-name'),
    description: field('module-description'),
    nodes: module.nodes.map((node) => ({
      ...node,
      label: field(`node-label:${node.id}`),
      description: field(`node-description:${node.id}`),
    })),
    edges: module.edges.map((edge) => ({
      ...edge,
      label: field(`edge-label:${edge.id}`),
      condition: field(`edge-condition:${edge.id}`),
    })),
  };
}

function graphMarkup(
  module: DecisionTreeModule,
  frame: NavigationFrame,
  modules: Map<string, DecisionTreeModule>,
  validation: TreeRegistryValidation,
  evidenceTemplates: Map<string, DecisionTreeTemplate>,
): string {
  const layout = graphLayout(module, frame.collapsed);
  const visibleEdges = module.edges.filter(
    (edge) => layout.visible.has(edge.from_node) && layout.visible.has(edge.to_node),
  );
  const edges = visibleEdges
    .map((edge) => {
      const source = layout.positions.get(edge.from_node);
      const target = layout.positions.get(edge.to_node);
      if (!source || !target) return '';
      return `<g class="tree-module-edge"><path d="M ${source.x + 196} ${source.y + 46} C ${source.x + 226} ${source.y + 46}, ${target.x - 30} ${target.y + 46}, ${target.x} ${target.y + 46}" /></g>`;
    })
    .join('');
  const edgeButtons = visibleEdges
    .map((edge) => {
      const source = layout.positions.get(edge.from_node);
      const target = layout.positions.get(edge.to_node);
      if (!source || !target) return '';
      const label = [edge.label, edge.condition].filter(Boolean).join(' · ') || titleCase(edge.id);
      const left = (source.x + target.x + 196) / 2 - 110;
      const top = (source.y + target.y) / 2 + 23;
      const evidenceState =
        edge.decision_id && edge.evidence_edge_id ? 'Evidence linked' : 'Evidence not linked';
      const evidence = evidenceTemplateEdge(edge, evidenceTemplates);
      return `<button type="button" class="tree-module-edge-button${frame.selectedEdgeId === edge.id ? ' is-selected' : ''}" style="left:${left}px;top:${top}px" data-tree-edge="${escapeHtml(edge.id)}" aria-pressed="${frame.selectedEdgeId === edge.id}" aria-label="Inspect ${escapeHtml(label)} probability evidence"><strong>${escapeHtml(label)}</strong><span class="tree-edge-evidence-state">${evidenceState}</span>${edgeFormulaMarkup(edge, evidence)}</button>`;
    })
    .join('');
  const outgoing = new Set(module.edges.map((edge) => edge.from_node));
  const unreachable = new Set(validation.unreachable_nodes[module.id] ?? []);
  const nodes = module.nodes
    .filter((node) => layout.visible.has(node.id))
    .map((node) => {
      const point = layout.positions.get(node.id)!;
      const target = node.target_module_id ? modules.get(node.target_module_id) : null;
      const broken = node.kind === 'module_reference' && !target;
      const previewId = target ? `tree-reference-preview-${module.id}-${node.id}` : null;
      const hasChildren = outgoing.has(node.id);
      const selected = frame.selectedNodeId === node.id;
      const collapse = hasChildren
        ? `<button type="button" class="tree-node-collapse" data-collapse-node="${escapeHtml(node.id)}" aria-label="${frame.collapsed.has(node.id) ? 'Expand' : 'Collapse'} ${escapeHtml(node.label)}" aria-expanded="${!frame.collapsed.has(node.id)}">${frame.collapsed.has(node.id) ? '+' : '−'}</button>`
        : '';
      const open =
        node.kind === 'module_reference'
          ? broken
            ? `<span class="tree-reference-broken">Broken reference · ${escapeHtml(node.target_module_id)}</span>`
            : `<button type="button" class="tree-reference-open" data-open-reference="${escapeHtml(node.id)}" aria-describedby="${escapeHtml(previewId!)}">Open ${escapeHtml(target!.name)}</button>`
          : '';
      return `<article class="tree-module-node tree-node-${node.kind}${selected ? ' is-selected' : ''}${unreachable.has(node.id) ? ' is-unreachable' : ''}${broken ? ' is-broken' : ''}" style="left:${point.x}px;top:${point.y}px" data-tree-node="${escapeHtml(node.id)}">
        ${collapse}
        <button type="button" class="tree-node-select" data-select-node="${escapeHtml(node.id)}" aria-pressed="${selected}"${previewId ? ` aria-describedby="${escapeHtml(previewId)}"` : ''}>
          <span>${escapeHtml(titleCase(node.kind))}</span><strong>${escapeHtml(node.label)}</strong>
        </button>
        ${open}
        ${target ? referencePreviewMarkup(module, node, target) : ''}
      </article>`;
    })
    .join('');
  return `<div class="tree-module-plane" data-tree-plane style="width:${layout.width}px;height:${layout.height}px;transform:translate(${frame.panX}px, ${frame.panY}px) scale(${frame.zoom})">
    <svg width="${layout.width}" height="${layout.height}" aria-hidden="true">${edges}</svg>${edgeButtons}${nodes}
  </div>`;
}

function evidenceTemplateEdge(
  edge: DecisionTreeEdge,
  templates: Map<string, DecisionTreeTemplate>,
): DecisionEdgeTemplate | null {
  if (!edge.decision_id || !edge.evidence_edge_id) return null;
  const template = templates.get(edge.decision_id);
  return template?.edges.find((item) => item.id === edge.evidence_edge_id) ?? null;
}

function edgeFormulaMarkup(edge: DecisionTreeEdge, evidence: DecisionEdgeTemplate | null): string {
  if (!edge.decision_id || !edge.evidence_edge_id) {
    return '<span class="tree-edge-formula is-missing">No confirmed probability formula</span>';
  }
  if (!evidence) {
    return '<span class="tree-edge-formula is-missing">Confirmed formula unavailable</span>';
  }
  const factorNames = evidence.formula.factors.map((factor) => factor.name).join(' × ');
  return `<span class="tree-edge-formula" data-tree-edge-formula><b>${escapeHtml(evidence.formula.name)}</b><em>${escapeHtml(factorNames)}</em></span>`;
}

function referenceLocations(
  moduleId: string,
  registry: DecisionTreeRegistryDefinition,
): Array<{ kind: 'tree' | 'module'; id: string; name: string; nodeId: string | null }> {
  const treeReferences = registry.trees
    .filter((tree) => tree.root_module_id === moduleId)
    .map((tree) => ({ kind: 'tree' as const, id: tree.id, name: tree.name, nodeId: null }));
  const moduleReferences = registry.modules.flatMap((module) =>
    module.nodes
      .filter((node) => node.target_module_id === moduleId)
      .map((node) => ({
        kind: 'module' as const,
        id: module.id,
        name: module.name,
        nodeId: node.id,
      })),
  );
  return [...treeReferences, ...moduleReferences].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

export function mountDecisionTreeNavigator(
  host: HTMLElement,
  options: DecisionTreeNavigatorOptions,
): DecisionTreeNavigatorController {
  const registry = options.registry;
  let validation = options.validation ?? emptyValidation;
  const modules = new Map(registry.modules.map((module) => [module.id, module]));
  const trees = new Map(registry.trees.map((tree) => [tree.id, tree]));
  const evidenceTemplates = new Map(
    (options.evidenceTemplates ?? []).map((template) => [template.id, template]),
  );
  const filters: TreeFilters = {
    agentType: options.initialAgentTypeId ?? '',
    place: '',
    source: '',
    status: '',
  };
  let query = '';
  let activeTreeId = options.initialTreeId ?? registry.trees[0]?.id ?? '';
  let frames: NavigationFrame[] = [];
  let editingModuleId: string | null = null;
  let editorNotice = '';
  let dragging: { x: number; y: number; panX: number; panY: number; pointerId: number } | null =
    null;
  let destroyed = false;
  const root = document.createElement('section');
  root.className = 'tree-navigator';
  host.replaceChildren(root);

  const makeFrame = (moduleId: string): NavigationFrame => ({
    moduleId,
    selectedNodeId: null,
    selectedEdgeId: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    collapsed: new Set(),
  });

  const currentTree = (): DecisionTreeDefinition | undefined => trees.get(activeTreeId);
  const currentFrame = (): NavigationFrame | undefined => frames.at(-1);
  const currentModule = (): DecisionTreeModule | undefined => {
    const frame = currentFrame();
    return frame ? modules.get(frame.moduleId) : undefined;
  };

  const setTree = (treeId: string): void => {
    const tree = trees.get(treeId);
    if (!tree) return;
    activeTreeId = tree.id;
    frames = [makeFrame(tree.root_module_id)];
    editingModuleId = null;
    editorNotice = '';
    render();
  };

  const applyRegistry = (view: DecisionTreeRegistryResponse): void => {
    registry.version = view.registry.version;
    registry.trees.splice(0, registry.trees.length, ...view.registry.trees);
    registry.modules.splice(0, registry.modules.length, ...view.registry.modules);
    trees.clear();
    modules.clear();
    registry.trees.forEach((tree) => trees.set(tree.id, tree));
    registry.modules.forEach((module) => modules.set(module.id, module));
    validation = view.validation;
  };

  const openPath = (match: SearchMatch): void => {
    const path = pathToModule(match.tree, match.module.id, modules);
    if (!path) return;
    activeTreeId = match.tree.id;
    frames = path.moduleIds.map(makeFrame);
    path.referenceNodeIds.forEach((nodeId, index) => {
      frames[index].selectedNodeId = nodeId;
    });
    frames.at(-1)!.selectedNodeId = match.node?.id ?? null;
    query = '';
    editingModuleId = null;
    editorNotice = '';
    render();
  };

  const notifySelection = (): void => {
    const frame = currentFrame();
    if (frame) options.onSelectionChange?.(activeTreeId, frame.moduleId, frame.selectedNodeId);
  };

  const render = (): void => {
    if (destroyed) return;
    const tree = currentTree();
    if (tree && !frames.length) frames = [makeFrame(tree.root_module_id)];
    const frame = currentFrame();
    const module = currentModule();
    const filteredTrees = registry.trees.filter((item) => treeMatches(item, filters));
    const searchMatches = searchRegistry(query, registry.trees, modules, filters);
    const agentTypes = sortedUnique(registry.trees.flatMap((item) => item.agent_type_ids));
    const places = sortedUnique(registry.trees.flatMap((item) => item.place_ids));
    const sources = sortedUnique(registry.trees.map((item) => item.source));
    const treeList = filteredTrees.length
      ? filteredTrees
          .map(
            (item) =>
              `<button type="button" class="tree-catalog-item${item.id === activeTreeId ? ' is-active' : ''}" data-tree-id="${escapeHtml(item.id)}" aria-pressed="${item.id === activeTreeId}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(titleCase(item.status))} · ${escapeHtml(item.source)}</span></button>`,
          )
          .join('')
      : '<p class="tree-empty">No decision trees match these filters.</p>';
    const results = query.trim()
      ? `<div class="tree-search-results" role="listbox" aria-label="Decision tree search results">${
          searchMatches.length
            ? searchMatches
                .slice(0, 60)
                .map(
                  (match, index) =>
                    `<button type="button" role="option" data-search-index="${index}"><strong>${escapeHtml(match.node?.label ?? match.module.name)}</strong><span>${escapeHtml(match.tree.name)} · ${escapeHtml(match.module.name)}</span></button>`,
                )
                .join('')
            : '<p>No trees or nodes found.</p>'
        }</div>`
      : '';
    const breadcrumbs = frames
      .map((item, index) => {
        const name = modules.get(item.moduleId)?.name ?? item.moduleId;
        return `<li>${index < frames.length - 1 ? `<button type="button" data-frame-index="${index}">${escapeHtml(name)}</button>` : `<span aria-current="page">${escapeHtml(name)}</span>`}</li>`;
      })
      .join('');
    const references = module ? referenceLocations(module.id, registry) : [];
    const referenceList = references.length
      ? references
          .map(
            (reference, index) =>
              `<li><button type="button" data-caller-index="${index}"><span>${reference.kind === 'tree' ? 'Tree root' : 'Module call'}</span><strong>${escapeHtml(reference.name)}</strong>${reference.nodeId ? `<small>${escapeHtml(reference.nodeId)}</small>` : ''}</button></li>`,
          )
          .join('')
      : '<li class="tree-empty">No callers. This module is not currently used.</li>';
    const selectedNode = module?.nodes.find((node) => node.id === frame?.selectedNodeId);
    const selectedEdge = module?.edges.find((edge) => edge.id === frame?.selectedEdgeId);
    const selectedEvidence = selectedEdge
      ? evidenceTemplateEdge(selectedEdge, evidenceTemplates)
      : null;
    const selectedFormula = selectedEvidence
      ? `${selectedEvidence.formula.name}: ${selectedEvidence.formula.factors.map((factor) => factor.name).join(' × ')}`
      : 'No confirmed probability formula';
    const selectedDetail = selectedEdge
      ? `<section class="tree-node-detail tree-edge-detail" aria-label="Selected decision transition"><span>Transition</span><h4>${escapeHtml(selectedEdge.label || titleCase(selectedEdge.id))}</h4><p>${escapeHtml(selectedEdge.condition || 'No additional condition')}</p><dl><dt>From</dt><dd>${escapeHtml(selectedEdge.from_node)}</dd><dt>To</dt><dd>${escapeHtml(selectedEdge.to_node)}</dd><dt>Formula</dt><dd>${escapeHtml(selectedFormula)}</dd><dt>Evidence link</dt><dd>${selectedEdge.decision_id && selectedEdge.evidence_edge_id ? `${escapeHtml(selectedEdge.decision_id)} · ${escapeHtml(selectedEdge.evidence_edge_id)}` : 'No evidence link attached'}</dd></dl><div data-edge-evidence></div></section>`
      : selectedNode
        ? `<section class="tree-node-detail" aria-label="Selected decision node"><span>${escapeHtml(titleCase(selectedNode.kind))}</span><h4>${escapeHtml(selectedNode.label)}</h4><p>${escapeHtml(selectedNode.description || 'No description yet')}</p>${selectedNode.target_module_id ? `<dl><dt>Target module</dt><dd>${escapeHtml(selectedNode.target_module_id)}</dd></dl>` : ''}</section>`
        : '<section class="tree-node-detail is-empty">Select a node or transition to inspect it.</section>';
    const editor = module && editingModuleId === module.id ? moduleEditorMarkup(module) : '';
    const currentBroken = module
      ? validation.broken_references.filter((item) => item.module_id === module.id)
      : [];
    const diagnostics = currentBroken.length
      ? `<div class="tree-module-diagnostics" role="alert"><strong>${currentBroken.length} broken ${currentBroken.length === 1 ? 'reference' : 'references'}</strong>${currentBroken.map((item) => `<span>${escapeHtml(item.node_id)} → ${escapeHtml(item.target_module_id)}</span>`).join('')}</div>`
      : '';
    const proposalProvenance =
      tree && module
        ? `<div class="tree-module-inspector tree-proposal-audit" role="region" aria-label="Decision tree proposal provenance">${proposalAuditMarkup('Tree proposal', tree.proposal_audit)}${proposalAuditMarkup('Module proposal', module.proposal_audit)}</div>`
        : '';
    root.innerHTML = `<header class="tree-navigator-header"><div><span class="tree-kicker">Simulation</span><h2>Decision trees</h2><p>Open one reusable module at a time and follow explicit module calls.</p></div><span class="tree-registry-version">Registry ${escapeHtml(registry.version)}</span></header>
      <div class="tree-toolbar">
        <label class="tree-search"><span>Search trees and nodes</span><input type="search" data-tree-search value="${escapeHtml(query)}" placeholder="Search names or node labels" /></label>
        <label><span>Agent type</span><select data-tree-filter="agentType">${optionMarkup(agentTypes, filters.agentType, 'All agent types')}</select></label>
        <label><span>Place</span><select data-tree-filter="place">${optionMarkup(places, filters.place, 'All places')}</select></label>
        <label><span>Source</span><select data-tree-filter="source">${optionMarkup(sources, filters.source, 'All sources')}</select></label>
        <label><span>Status</span><select data-tree-filter="status">${optionMarkup(['ready', 'draft', 'blocked', 'deprecated'], filters.status, 'All statuses')}</select></label>
        ${results}
      </div>
      <div class="tree-navigator-layout">
        <aside class="tree-catalog" aria-label="Decision tree catalog"><div><h3>Trees</h3><span>${filteredTrees.length}</span></div>${treeList}</aside>
        <main class="tree-module-workspace">
          ${
            tree && module && frame
              ? `<div class="tree-module-topline"><button type="button" data-tree-back ${frames.length === 1 ? 'disabled' : ''}>Back</button><nav aria-label="Decision tree module breadcrumbs"><ol>${breadcrumbs}</ol></nav></div>
          <div class="tree-module-heading"><div><span>${escapeHtml(tree.name)}</span><h3>${escapeHtml(module.name)}</h3><p>${escapeHtml(module.description || 'No description yet')}</p></div><div class="tree-module-meta"><span class="status-${escapeHtml(module.status)}">${escapeHtml(titleCase(module.status))}</span><span>${escapeHtml(module.source)}</span><span>v${escapeHtml(module.version)}</span><button type="button" data-edit-module aria-expanded="${editingModuleId === module.id}">${editingModuleId === module.id ? 'Editing module' : 'Edit module'}</button></div></div>
          ${proposalProvenance}
          ${editorNotice ? `<p class="tree-editor-notice" role="status">${escapeHtml(editorNotice)}</p>` : ''}
          ${editor}
          ${diagnostics}
          <div class="tree-viewport-shell"><div class="tree-zoom-controls" aria-label="Graph zoom controls"><button type="button" data-zoom="out" aria-label="Zoom out">−</button><output aria-label="Zoom level">${Math.round(frame.zoom * 100)}%</output><button type="button" data-zoom="in" aria-label="Zoom in">+</button><button type="button" data-zoom="reset">Reset view</button></div><div class="tree-module-viewport" data-tree-viewport tabindex="0" aria-label="${escapeHtml(module.name)} module graph">${graphMarkup(module, frame, modules, validation, evidenceTemplates)}</div></div>
          <div class="tree-module-inspector">${selectedDetail}<section class="tree-reference-list"><div><span>References</span><h4>Used by</h4></div><ul>${referenceList}</ul></section></div>`
              : '<div class="tree-empty tree-module-empty">Select a valid decision tree.</div>'
          }
        </main>
      </div>`;

    const evidenceHost = root.querySelector<HTMLElement>('[data-edge-evidence]');
    if (evidenceHost && tree && module && selectedEdge) {
      if (selectedEdge.decision_id && selectedEdge.evidence_edge_id) {
        if (options.renderEdgeEvidence) {
          evidenceHost.innerHTML =
            '<p class="tree-evidence-loading" role="status">Resolving evidence for this agent and place…</p>';
          void Promise.resolve(
            options.renderEdgeEvidence(evidenceHost, {
              tree,
              module,
              edge: selectedEdge,
              evidence: selectedEvidence,
            }),
          ).catch((error: unknown) => {
            evidenceHost.innerHTML = `<p class="tree-evidence-error" role="alert">${escapeHtml(error instanceof Error ? error.message : String(error))}</p>`;
          });
        } else {
          evidenceHost.innerHTML =
            '<p class="tree-evidence-unlinked" role="status">Select an initial agent to evaluate this linked transition against that agent’s traits and place.</p>';
        }
      } else {
        evidenceHost.innerHTML =
          '<p class="tree-evidence-unlinked" role="status">This transition has no decision-evidence link. It cannot be presented as measured or used as a fitted predictor.</p>';
      }
    }

    root
      .querySelector<HTMLInputElement>('[data-tree-search]')
      ?.addEventListener('input', (event) => {
        query = (event.currentTarget as HTMLInputElement).value;
        render();
        const input = root.querySelector<HTMLInputElement>('[data-tree-search]');
        input?.focus();
        input?.setSelectionRange(query.length, query.length);
      });
    root.querySelectorAll<HTMLSelectElement>('[data-tree-filter]').forEach((select) => {
      select.addEventListener('change', () => {
        const key = select.dataset.treeFilter as keyof TreeFilters;
        filters[key] = select.value;
        render();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-tree-id]').forEach((button) => {
      button.addEventListener('click', () => setTree(button.dataset.treeId!));
    });
    root.querySelectorAll<HTMLButtonElement>('[data-search-index]').forEach((button) => {
      button.addEventListener('click', () =>
        openPath(searchMatches[Number(button.dataset.searchIndex)]),
      );
    });
    root.querySelector<HTMLButtonElement>('[data-edit-module]')?.addEventListener('click', () => {
      if (!module) return;
      editorNotice = '';
      editingModuleId = editingModuleId === module.id ? null : module.id;
      render();
      root.querySelector<HTMLInputElement>('[name="module-name"]')?.focus();
    });
    root.querySelectorAll<HTMLButtonElement>('[data-cancel-module-edit]').forEach((button) => {
      button.addEventListener('click', () => {
        editingModuleId = null;
        render();
        root.querySelector<HTMLButtonElement>('[data-edit-module]')?.focus();
      });
    });
    root
      .querySelector<HTMLFormElement>('[data-module-editor]')
      ?.addEventListener('submit', (event) => {
        event.preventDefault();
        const form = event.currentTarget as HTMLFormElement;
        if (!module || !form.reportValidity()) return;
        const saveButton = form.querySelector<HTMLButtonElement>('[type="submit"]')!;
        const status = form.querySelector<HTMLOutputElement>('[data-module-editor-status]')!;
        const nextModule = editedModule(form, module);
        const nextRegistry = {
          ...registry,
          modules: registry.modules.map((item) => (item.id === nextModule.id ? nextModule : item)),
        };
        saveButton.disabled = true;
        saveButton.textContent = 'Saving…';
        status.className = '';
        status.textContent = 'Validating and saving the shared module…';
        void (options.confirmRegistry ?? confirmRegistry)(nextRegistry)
          .then((view) => {
            if (destroyed) return;
            applyRegistry(view);
            editingModuleId = null;
            editorNotice = `${nextModule.name} saved everywhere it is referenced.`;
            render();
          })
          .catch((error: unknown) => {
            if (destroyed) return;
            saveButton.disabled = false;
            saveButton.textContent = 'Confirm module changes';
            status.className = 'is-error';
            status.textContent = error instanceof Error ? error.message : String(error);
          });
      });
    root.querySelector<HTMLButtonElement>('[data-tree-back]')?.addEventListener('click', () => {
      if (frames.length <= 1) return;
      frames.pop();
      editingModuleId = null;
      editorNotice = '';
      render();
      notifySelection();
    });
    root.querySelectorAll<HTMLButtonElement>('[data-frame-index]').forEach((button) => {
      button.addEventListener('click', () => {
        frames = frames.slice(0, Number(button.dataset.frameIndex) + 1);
        editingModuleId = null;
        editorNotice = '';
        render();
        notifySelection();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-select-node]').forEach((button) => {
      button.addEventListener('click', () => {
        if (!frame) return;
        frame.selectedNodeId = button.dataset.selectNode!;
        frame.selectedEdgeId = null;
        render();
        notifySelection();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-tree-edge]').forEach((button) => {
      button.addEventListener('click', () => {
        if (!frame) return;
        frame.selectedEdgeId = button.dataset.treeEdge!;
        frame.selectedNodeId = null;
        render();
        notifySelection();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-collapse-node]').forEach((button) => {
      button.addEventListener('click', () => {
        if (!frame) return;
        const nodeId = button.dataset.collapseNode!;
        if (frame.collapsed.has(nodeId)) frame.collapsed.delete(nodeId);
        else frame.collapsed.add(nodeId);
        render();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-open-reference]').forEach((button) => {
      button.addEventListener('click', () => {
        if (!module || !frame) return;
        const node = module.nodes.find((item) => item.id === button.dataset.openReference);
        if (!node?.target_module_id || !modules.has(node.target_module_id)) return;
        frame.selectedNodeId = node.id;
        frames.push(makeFrame(node.target_module_id));
        editingModuleId = null;
        editorNotice = '';
        render();
        notifySelection();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-zoom]').forEach((button) => {
      button.addEventListener('click', () => {
        if (!frame) return;
        if (button.dataset.zoom === 'in') frame.zoom = Math.min(2, frame.zoom + 0.25);
        if (button.dataset.zoom === 'out') frame.zoom = Math.max(0.5, frame.zoom - 0.25);
        if (button.dataset.zoom === 'reset') Object.assign(frame, { zoom: 1, panX: 0, panY: 0 });
        render();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-caller-index]').forEach((button) => {
      button.addEventListener('click', () => {
        const reference = references[Number(button.dataset.callerIndex)];
        if (reference.kind === 'tree') {
          setTree(reference.id);
          return;
        }
        const candidate = registry.trees
          .map((item) => ({ tree: item, path: pathToModule(item, reference.id, modules) }))
          .find((item) => item.path);
        const caller = modules.get(reference.id);
        if (candidate && caller)
          openPath({
            tree: candidate.tree,
            module: caller,
            node: caller.nodes.find((item) => item.id === reference.nodeId) ?? null,
          });
      });
    });
    const viewport = root.querySelector<HTMLElement>('[data-tree-viewport]');
    viewport?.addEventListener('pointerdown', (event) => {
      if (!frame || (event.target as HTMLElement).closest('button')) return;
      dragging = {
        x: event.clientX,
        y: event.clientY,
        panX: frame.panX,
        panY: frame.panY,
        pointerId: event.pointerId,
      };
      viewport.setPointerCapture(event.pointerId);
      viewport.classList.add('is-panning');
    });
    viewport?.addEventListener('pointermove', (event) => {
      if (!frame || !dragging || dragging.pointerId !== event.pointerId) return;
      frame.panX = dragging.panX + event.clientX - dragging.x;
      frame.panY = dragging.panY + event.clientY - dragging.y;
      const plane = viewport.querySelector<HTMLElement>('[data-tree-plane]');
      if (plane)
        plane.style.transform = `translate(${frame.panX}px, ${frame.panY}px) scale(${frame.zoom})`;
    });
    const stopDragging = (event: PointerEvent): void => {
      if (!dragging || dragging.pointerId !== event.pointerId) return;
      dragging = null;
      viewport?.classList.remove('is-panning');
    };
    viewport?.addEventListener('pointerup', stopDragging);
    viewport?.addEventListener('pointercancel', stopDragging);
  };

  if (activeTreeId) setTree(activeTreeId);
  else render();

  return {
    selectTree: setTree,
    destroy() {
      destroyed = true;
      root.remove();
    },
  };
}
