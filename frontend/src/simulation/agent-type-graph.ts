import './agent-type-graph.css';

import type { AgentTypeProposalAudit } from './agent-type-proposal';
import {
  agentStateDefinitionsMarkup,
  type AgentStateSystem,
} from './agent-state-view';

export interface AgentTypeGraphMemberDefinition {
  id: string;
  name: string;
  definition: string;
  description: string | null;
  source_feature_ids: string[];
}

export interface AgentTypeGraphMember {
  member: AgentTypeGraphMemberDefinition;
  source_type_id: string;
  inherited: boolean;
  explicit_override: boolean;
  overridden_source_type_ids: string[];
}

export interface AgentTypeGraphNode {
  id: string;
  name: string;
  description: string | null;
  parent_ids: string[];
  traits: AgentTypeGraphMember[];
  routines: AgentTypeGraphMember[];
  decisions: AgentTypeGraphMember[];
}

export interface AgentTypeGraphOptions {
  types: AgentTypeGraphNode[];
  audit?: AgentTypeProposalAudit;
  stateSystem?: AgentStateSystem;
  selectedTypeId?: string;
  onSelectionChange?: (agentType: AgentTypeGraphNode) => void;
  onModeChange?: (mode: AgentTypeGraphMode, agentType: AgentTypeGraphNode) => void;
  renderDecisionTree?: (host: HTMLElement, agentType: AgentTypeGraphNode) => void | (() => void);
}

export type AgentTypeGraphMode = 'inheritance' | 'decision';

export interface AgentTypeGraphController {
  select(typeId: string): void;
  setMode(mode: AgentTypeGraphMode): void;
  update(types: AgentTypeGraphNode[]): void;
  selected(): AgentTypeGraphNode | null;
  destroy(): void;
}

interface Point {
  x: number;
  y: number;
}

interface GraphLayout {
  width: number;
  height: number;
  points: Map<string, Point>;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const sorted = (values: string[]): string[] =>
  [...values].sort((left, right) => left.localeCompare(right));

export function validateAgentTypeGraph(types: AgentTypeGraphNode[]): string[] {
  const issues: string[] = [];
  const ids = new Set<string>();
  for (const agentType of types) {
    if (ids.has(agentType.id)) issues.push(`Duplicate agent type id: ${agentType.id}`);
    ids.add(agentType.id);
  }
  for (const agentType of types) {
    for (const parentId of agentType.parent_ids) {
      if (!ids.has(parentId)) issues.push(`Unknown parent ${parentId} for ${agentType.id}`);
    }
  }
  const byId = new Map(types.map((agentType) => [agentType.id, agentType]));
  const active: string[] = [];
  const complete = new Set<string>();
  const visit = (typeId: string): void => {
    if (active.includes(typeId)) {
      const cycle = [...active.slice(active.indexOf(typeId)), typeId].join(' → ');
      issues.push(`Inheritance cycle: ${cycle}`);
      return;
    }
    if (complete.has(typeId)) return;
    active.push(typeId);
    for (const parentId of byId.get(typeId)?.parent_ids ?? []) {
      if (byId.has(parentId)) visit(parentId);
    }
    active.pop();
    complete.add(typeId);
  };
  for (const agentType of types) visit(agentType.id);
  return [...new Set(issues)];
}

function graphLayout(types: AgentTypeGraphNode[]): GraphLayout {
  const byId = new Map(types.map((agentType) => [agentType.id, agentType]));
  const depthCache = new Map<string, number>();
  const depth = (typeId: string): number => {
    const cached = depthCache.get(typeId);
    if (cached !== undefined) return cached;
    const parents = byId.get(typeId)?.parent_ids.filter((parentId) => byId.has(parentId)) ?? [];
    const value = parents.length ? Math.max(...parents.map((parentId) => depth(parentId))) + 1 : 0;
    depthCache.set(typeId, value);
    return value;
  };
  const levels = new Map<number, AgentTypeGraphNode[]>();
  for (const agentType of types) {
    const level = depth(agentType.id);
    levels.set(level, [...(levels.get(level) ?? []), agentType]);
  }
  const widestLevel = Math.max(1, ...[...levels.values()].map((items) => items.length));
  const lastLevel = Math.max(0, ...levels.keys());
  const width = Math.max(720, widestLevel * 190 + 120);
  const height = Math.max(260, (lastLevel + 1) * 140 + 80);
  const points = new Map<string, Point>();
  for (const [level, items] of levels) {
    const ordered = [...items].sort((left, right) => left.name.localeCompare(right.name));
    const spacing = width / (ordered.length + 1);
    ordered.forEach((agentType, index) => {
      points.set(agentType.id, { x: spacing * (index + 1), y: 62 + level * 140 });
    });
  }
  return { width, height, points };
}

function memberCount(agentType: AgentTypeGraphNode, inherited: boolean): number {
  return [...agentType.traits, ...agentType.routines, ...agentType.decisions].filter(
    (item) => item.inherited === inherited,
  ).length;
}

function graphMarkup(types: AgentTypeGraphNode[], selectedTypeId: string | null): string {
  const layout = graphLayout(types);
  const edges = types.flatMap((child) =>
    child.parent_ids.map((parentId) => {
      const parent = layout.points.get(parentId);
      const childPoint = layout.points.get(child.id);
      if (!parent || !childPoint) return '';
      return `<line data-agent-type-edge="${escapeHtml(`${parentId}:${child.id}`)}" x1="${parent.x}" y1="${parent.y + 31}" x2="${childPoint.x}" y2="${childPoint.y - 31}" />`;
    }),
  );
  const nodes = types.map((agentType) => {
    const point = layout.points.get(agentType.id)!;
    const selected = agentType.id === selectedTypeId;
    return `
      <button
        class="agent-type-node${selected ? ' is-selected' : ''}"
        type="button"
        data-agent-type-id="${escapeHtml(agentType.id)}"
        aria-label="${escapeHtml(agentType.name)} agent type"
        aria-pressed="${selected}"
        style="left:${point.x - 73}px;top:${point.y - 31}px"
      >
        <strong>${escapeHtml(agentType.name)}</strong>
        <span>${memberCount(agentType, false)} own · ${memberCount(agentType, true)} inherited</span>
      </button>
    `;
  });
  return `
    <div class="agent-type-graph-scroll" data-agent-type-graph-scroll>
      <div class="agent-type-graph-plane" style="width:${layout.width}px;height:${layout.height}px">
        <svg viewBox="0 0 ${layout.width} ${layout.height}" role="img" aria-label="Agent type inheritance edges">
          <defs>
            <marker id="agent-type-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z"></path>
            </marker>
          </defs>
          ${edges.join('')}
        </svg>
        ${nodes.join('')}
      </div>
    </div>
  `;
}

function sourceName(typeId: string, byId: Map<string, AgentTypeGraphNode>): string {
  return byId.get(typeId)?.name ?? typeId;
}

function membersMarkup(
  title: string,
  members: AgentTypeGraphMember[],
  byId: Map<string, AgentTypeGraphNode>,
): string {
  const items = [...members].sort((left, right) => {
    if (left.inherited !== right.inherited) return Number(left.inherited) - Number(right.inherited);
    return left.member.name.localeCompare(right.member.name);
  });
  const cards = items.length
    ? items
        .map((item) => {
          const ownership = item.inherited
            ? `Inherited from ${sourceName(item.source_type_id, byId)}`
            : 'Own definition';
          const overridden = item.overridden_source_type_ids.length
            ? `<span class="agent-type-member-override">Overrides ${sorted(
                item.overridden_source_type_ids,
              )
                .map((typeId) => escapeHtml(sourceName(typeId, byId)))
                .join(', ')}</span>`
            : '';
          const sources = item.member.source_feature_ids.length
            ? `<span>Registry features: ${sorted(item.member.source_feature_ids).map(escapeHtml).join(', ')}</span>`
            : '';
          return `
            <li class="agent-type-member${item.inherited ? ' is-inherited' : ' is-own'}">
              <div>
                <strong>${escapeHtml(item.member.name)}</strong>
                <span class="agent-type-member-source" data-agent-member-source>${escapeHtml(ownership)}</span>
              </div>
              <p>${escapeHtml(item.member.definition)}</p>
              ${item.member.description ? `<p>${escapeHtml(item.member.description)}</p>` : ''}
              <div class="agent-type-member-meta">${overridden}${sources}</div>
            </li>
          `;
        })
        .join('')
    : '<li class="agent-type-member-empty">None defined</li>';
  return `
    <section class="agent-type-member-section">
      <div><h4>${escapeHtml(title)}</h4><span>${items.length}</span></div>
      <ul>${cards}</ul>
    </section>
  `;
}

function detailMarkup(
  agentType: AgentTypeGraphNode | null,
  byId: Map<string, AgentTypeGraphNode>,
  audit?: AgentTypeProposalAudit,
  stateSystem?: AgentStateSystem,
): string {
  if (!agentType) {
    return '<div class="agent-type-detail-empty">Select an agent type to inspect its definitions.</div>';
  }
  const parents = agentType.parent_ids.length
    ? agentType.parent_ids.map((parentId) => escapeHtml(sourceName(parentId, byId))).join(', ')
    : 'Base type';
  const provenance = audit
    ? `<dl class="agent-type-audit"><div><dt>Created via</dt><dd>${escapeHtml(
        ({
          openai_cli: 'OpenAI CLI',
          openai_api: 'OpenAI API',
          deterministic: 'Deterministic builder',
          manual: 'Manual entry',
        })[audit.provider],
      )}</dd></div><div><dt>Model</dt><dd>${escapeHtml(audit.model)}</dd></div><div><dt>Prompt</dt><dd>${escapeHtml(audit.prompt_version)}</dd></div><div><dt>Generated</dt><dd>${escapeHtml(audit.generated_at)}</dd></div></dl>`
    : '';
  return `
    <div class="agent-type-detail-heading">
      <div>
        <span class="agent-type-kicker">Agent type</span>
        <h3>${escapeHtml(agentType.name)}</h3>
      </div>
      <span class="agent-type-parent-list">${escapeHtml(parents)}</span>
    </div>
    <p class="agent-type-description">${escapeHtml(agentType.description ?? 'No description yet')}</p>
    ${provenance}
    ${membersMarkup('Traits', agentType.traits, byId)}
    ${membersMarkup('Routines', agentType.routines, byId)}
    ${membersMarkup('Decisions', agentType.decisions, byId)}
    ${
      stateSystem
        ? `<details class="agent-type-state-system"><summary>State definitions, formulas, and loops</summary>${agentStateDefinitionsMarkup(stateSystem)}</details>`
        : ''
    }
  `;
}

function modeButton(mode: AgentTypeGraphMode, activeMode: AgentTypeGraphMode): string {
  const label = mode === 'inheritance' ? 'Inheritance' : 'Decision tree';
  return `
    <button
      type="button"
      class="agent-type-mode${mode === activeMode ? ' is-active' : ''}"
      data-agent-type-mode="${mode}"
      aria-label="${label} view"
      aria-pressed="${mode === activeMode}"
    >${label}</button>
  `;
}

export function mountAgentTypeGraph(
  host: HTMLElement,
  options: AgentTypeGraphOptions,
): AgentTypeGraphController {
  let types = [...options.types];
  let selectedTypeId = options.selectedTypeId ?? types[0]?.id ?? null;
  let mode: AgentTypeGraphMode = 'inheritance';
  let decisionCleanup: (() => void) | undefined;
  const root = document.createElement('section');
  root.className = 'agent-type-graph';
  host.replaceChildren(root);

  const selected = (): AgentTypeGraphNode | null =>
    types.find((agentType) => agentType.id === selectedTypeId) ?? null;

  const render = (): void => {
    decisionCleanup?.();
    decisionCleanup = undefined;
    const issues = validateAgentTypeGraph(types);
    const byId = new Map(types.map((agentType) => [agentType.id, agentType]));
    const current = selected();
    const content = issues.length
      ? `<div class="agent-type-graph-errors" role="alert"><strong>Inheritance graph is invalid</strong><ul>${issues
          .map((issue) => `<li>${escapeHtml(issue)}</li>`)
          .join('')}</ul></div>`
      : mode === 'inheritance'
        ? `<div class="agent-type-graph-layout">${graphMarkup(types, selectedTypeId)}<aside data-agent-type-detail>${detailMarkup(current, byId, options.audit, options.stateSystem)}</aside></div>`
        : `<div class="agent-type-decision-view"><div class="agent-type-decision-heading"><span>Selected type</span><strong>${escapeHtml(current?.name ?? 'None')}</strong></div><div data-agent-type-decision-host></div></div>`;
    root.innerHTML = `
      <header class="agent-type-graph-header">
        <div>
          <span class="agent-type-kicker">Simulation graph</span>
          <h2>Agent type inheritance</h2>
          <p>Parent definitions flow to each child. Select a node to inspect its sources and overrides.</p>
        </div>
        <div class="agent-type-mode-switch" role="group" aria-label="Agent graph view">
          ${modeButton('inheritance', mode)}
          ${modeButton('decision', mode)}
        </div>
      </header>
      ${content}
    `;
    if (mode === 'decision') {
      const decisionHost = root.querySelector<HTMLElement>('[data-agent-type-decision-host]');
      if (decisionHost && current) {
        const cleanup = options.renderDecisionTree?.(decisionHost, current);
        if (typeof cleanup === 'function') decisionCleanup = cleanup;
        if (!options.renderDecisionTree) {
          decisionHost.innerHTML =
            '<p class="agent-type-detail-empty">No decision tree attached.</p>';
        }
      }
    }
  };

  const selectType = (typeId: string): void => {
    const agentType = types.find((candidate) => candidate.id === typeId);
    if (!agentType) throw new Error(`Unknown agent type: ${typeId}`);
    selectedTypeId = typeId;
    render();
    options.onSelectionChange?.(agentType);
  };

  const setMode = (nextMode: AgentTypeGraphMode): void => {
    if (mode === nextMode) return;
    mode = nextMode;
    render();
    const current = selected();
    if (current) options.onModeChange?.(mode, current);
  };

  const onClick = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const node = target.closest<HTMLElement>('[data-agent-type-id]');
    if (node?.dataset.agentTypeId) {
      selectType(node.dataset.agentTypeId);
      return;
    }
    const modeControl = target.closest<HTMLElement>('[data-agent-type-mode]');
    const nextMode = modeControl?.dataset.agentTypeMode;
    if (nextMode === 'inheritance' || nextMode === 'decision') setMode(nextMode);
  };
  root.addEventListener('click', onClick);
  render();

  return {
    select: selectType,
    setMode,
    update(nextTypes) {
      types = [...nextTypes];
      if (!types.some((agentType) => agentType.id === selectedTypeId)) {
        selectedTypeId = types[0]?.id ?? null;
      }
      render();
    },
    selected,
    destroy() {
      decisionCleanup?.();
      root.removeEventListener('click', onClick);
      root.remove();
    },
  };
}

export * from './agent-type-proposal';
