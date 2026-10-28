export interface GraphRoleExposure {
  id: string;
  actions: string[];
  decisions: string[];
  conditions: string[];
  leader: boolean;
  count?: number | null;
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
  level: string;
  parent_id?: string | null;
  weight?: number | null;
  represented_count?: number | null;
  simulated_count?: number | null;
  line: number;
  cached: boolean;
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

export interface ProgramGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface GraphViewOptions {
  onViewCode: (line: number) => void;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const label = (value: string): string =>
  value.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');

const count = (value?: number | null): string =>
  value === undefined || value === null ? '—' : value.toLocaleString();

const syncLabel = (days?: number | null): string => {
  if (!days) return 'immediate';
  if (days === 1) return 'daily sync';
  if (days === 7) return 'weekly sync';
  return `${days}-day sync`;
};

export class DslGraphView {
  private graph?: ProgramGraph;
  private selectedNode?: string;
  private roleFilter = '';
  private search = '';
  private slice = '';
  private collapsed = new Set<string>();
  private expandedSubtreeRoles = new Set<string>();
  private scale = 1;
  private panX = 0;
  private panY = 0;
  private cacheStatus = new Map<string, string>();
  private drag?: { x: number; y: number; panX: number; panY: number };

  constructor(
    private readonly host: HTMLElement,
    private readonly options: GraphViewOptions,
  ) {
    this.host.className = 'dsl-graph-view';
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('pointerdown', this.onPointerDown);
    this.host.addEventListener('pointermove', this.onPointerMove);
    this.host.addEventListener('pointerup', this.onPointerUp);
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('pointerdown', this.onPointerDown);
    this.host.removeEventListener('pointermove', this.onPointerMove);
    this.host.removeEventListener('pointerup', this.onPointerUp);
  }

  setGraph(graph?: ProgramGraph | null): void {
    this.graph = graph ?? undefined;
    if (this.selectedNode && !this.graph?.nodes.some((node) => node.id === this.selectedNode)) {
      this.selectedNode = undefined;
    }
    if (!this.host.hidden) this.render();
  }

  setCacheStatus(id: string, status: string): void {
    this.cacheStatus.set(id, status);
    if (!this.host.hidden && this.selectedNode === id) this.renderDetail();
  }

  render(): void {
    const started = performance.now();
    if (!this.graph?.nodes.length) {
      this.host.innerHTML = `<div class="dsl-graph-empty">Graph is unavailable for this DSL — run Validate first.</div>`;
      this.host.dataset.renderMs = (performance.now() - started).toFixed(1);
      return;
    }
    const slices = [...new Set(this.graph.nodes.map((node) => node.vertical_slice))];
    this.host.innerHTML = `
      <div class="dsl-graph-controls">
        <label>Search nodes or roles<input type="search" data-graph-search value="${escapeHtml(this.search)}" placeholder="trader, Store, mayor"></label>
        <label>Vertical slice<select data-graph-slice><option value="">All slices</option>${slices.map((slice) => `<option value="${escapeHtml(slice)}"${slice === this.slice ? ' selected' : ''}>${escapeHtml(label(slice))}</option>`).join('')}</select></label>
        <label>Exposes role<select data-graph-role><option value="">All roles</option>${this.roles()
          .map(
            (role) =>
              `<option value="${escapeHtml(role)}"${role === this.roleFilter ? ' selected' : ''}>${escapeHtml(role)}</option>`,
          )
          .join('')}</select></label>
        <button type="button" data-graph-control="zoom-out" aria-label="Zoom out">−</button>
        <button type="button" data-graph-control="zoom-in" aria-label="Zoom in">+</button>
        <button type="button" data-graph-control="fit">Fit to screen</button>
        <button type="button" data-graph-control="reset">Reset layout</button>
      </div>
      <div class="dsl-graph-legend" aria-label="Graph legend"><span><i class="solid"></i>Parent/child composition</span><span><i class="dashed"></i>Coupling across slices</span><span class="badge">CACHE</span>Cached aggregate available<span class="badge leader">1</span>Leader role<span class="badge mass">R</span>Mass role</div>
      <div class="dsl-graph-body">
        <div class="dsl-graph-viewport" data-graph-viewport>
          <div class="dsl-graph-canvas" data-graph-canvas>
            <svg class="dsl-graph-edges" aria-hidden="true"></svg>
            <div class="dsl-graph-lanes">${this.renderLanes(slices)}</div>
          </div>
        </div>
        <aside class="dsl-graph-detail" data-graph-detail></aside>
      </div>`;
    this.applyTransform();
    this.renderDetail();
    requestAnimationFrame(() => {
      this.renderEdges();
      this.host.dataset.renderMs = (performance.now() - started).toFixed(1);
    });
  }

  private roles(): string[] {
    return [
      ...new Set(
        this.graph?.nodes.flatMap((node) => [
          ...node.roles_exposed.map((role) => role.id),
          ...node.roles_used,
        ]) ?? [],
      ),
    ].sort();
  }

  private renderLanes(slices: string[]): string {
    return slices
      .filter((slice) => !this.slice || slice === this.slice)
      .map((slice) => {
        const nodes = this.visibleNodes()
          .filter((node) => node.vertical_slice === slice)
          .sort((left, right) => this.depth(left) - this.depth(right) || left.line - right.line);
        return `<section class="dsl-graph-lane" data-slice="${escapeHtml(slice)}"><header><strong>${escapeHtml(label(slice))}</strong><span>${nodes.length} nodes</span></header><div>${nodes.map((node) => this.nodeCard(node)).join('')}</div></section>`;
      })
      .join('');
  }

  private visibleNodes(): GraphNode[] {
    const hidden = new Set<string>();
    const children = new Map<string, string[]>();
    for (const node of this.graph?.nodes ?? []) {
      if (!node.parent_id) continue;
      const values = children.get(node.parent_id) ?? [];
      values.push(node.id);
      children.set(node.parent_id, values);
    }
    const hide = (id: string): void => {
      for (const child of children.get(id) ?? []) {
        hidden.add(child);
        hide(child);
      }
    };
    for (const id of this.collapsed) hide(id);
    return (this.graph?.nodes ?? []).filter((node) => {
      if (hidden.has(node.id)) return false;
      const roles = [...node.roles_exposed.map((role) => role.id), ...node.roles_used];
      const roleMatch = !this.roleFilter || roles.includes(this.roleFilter);
      return roleMatch;
    });
  }

  private depth(node: GraphNode): number {
    const nodes = new Map((this.graph?.nodes ?? []).map((candidate) => [candidate.id, candidate]));
    let current = node;
    let depth = 0;
    const visited = new Set<string>();
    while (current.parent_id && !visited.has(current.id)) {
      visited.add(current.id);
      const parent = nodes.get(current.parent_id);
      if (!parent) break;
      depth += 1;
      current = parent;
    }
    return depth;
  }

  private matchesSearch(node: GraphNode): boolean {
    const query = this.search.trim().toLowerCase();
    if (!query) return false;
    return [
      node.id,
      node.level,
      node.vertical_slice,
      ...node.roles_exposed.map((role) => role.id),
      ...node.roles_used,
      ...Object.keys(node.parameters),
      ...node.actions.map((action) => action.id),
    ]
      .join(' ')
      .toLowerCase()
      .includes(query);
  }

  private nodeCard(node: GraphNode): string {
    const roles = node.roles_exposed.slice(0, 3);
    const selected = node.id === this.selectedNode;
    const highlighted =
      this.matchesSearch(node) ||
      (Boolean(this.roleFilter) &&
        (node.roles_exposed.some((role) => role.id === this.roleFilter) ||
          node.roles_used.includes(this.roleFilter)));
    const hasChildren = this.graph?.nodes.some((candidate) => candidate.parent_id === node.id);
    return `<article class="dsl-graph-node${selected ? ' selected' : ''}${highlighted ? ' highlighted' : ''}" data-graph-node="${escapeHtml(node.id)}" data-line="${node.line}">
      <div class="dsl-graph-node-top"><span>${escapeHtml(label(node.level))}</span><div>${node.cached ? '<b class="badge">CACHE</b>' : ''}${node.roles_exposed
        .filter((role) => role.leader)
        .map(
          (role) =>
            `<b class="badge leader" data-role-filter="${escapeHtml(role.id)}">${role.count ?? 1}</b>`,
        )
        .join(
          '',
        )}${node.roles_exposed.filter((role) => !role.leader).length ? '<b class="badge mass">R</b>' : ''}</div></div>
      <strong>${escapeHtml(node.id)}</strong>
      <small>${escapeHtml(label(node.vertical_slice))}</small>
      <p>${count(node.simulated_count)} simulated${node.represented_count ? ` · ${count(node.represented_count)} represented` : ''}</p>
      <p><span>Roles exposed:</span> ${roles.length ? roles.map((role) => `<button type="button" data-role-filter="${escapeHtml(role.id)}">${escapeHtml(role.id)}${role.actions.length ? ` (${escapeHtml(role.actions.slice(0, 2).join(', '))})` : ''}</button>`).join(' · ') : 'none'}</p>
      ${!roles.length && node.subtree_role_count ? `<p><button type="button" data-subtree-roles="${escapeHtml(node.id)}">Subtree roles: ${node.subtree_role_count}</button>${this.expandedSubtreeRoles.has(node.id) ? `<small>${node.subtree_roles.map((role) => `<button type="button" data-role-filter="${escapeHtml(role)}">${escapeHtml(role)}</button>`).join(' · ')}</small>` : ''}</p>` : ''}
      ${hasChildren ? `<button type="button" data-collapse-node="${escapeHtml(node.id)}">${this.collapsed.has(node.id) ? 'Expand' : 'Collapse'} subtree</button>` : ''}
    </article>`;
  }

  private renderDetail(): void {
    const host = this.host.querySelector<HTMLElement>('[data-graph-detail]');
    if (!host) return;
    const node = this.graph?.nodes.find((candidate) => candidate.id === this.selectedNode);
    if (!node) {
      host.innerHTML = `<div class="dsl-graph-detail-empty"><strong>Select a node</strong><p>Open its DSL declarations, roles, outputs, and couplings here.</p></div>`;
      return;
    }
    const section = (title: string, values: string[]): string =>
      `<section><h4>${escapeHtml(title)}</h4>${values.length ? `<ul>${values.map((value) => `<li>${value}</li>`).join('')}</ul>` : '<p>None declared in DSL</p>'}</section>`;
    const roles = node.roles_exposed.map(
      (role) =>
        `<button type="button" data-role-filter="${escapeHtml(role.id)}"><strong>${escapeHtml(role.id)}</strong> · ${role.leader ? `leader${role.count ? ` (${role.count})` : ''}` : 'mass'} · ${escapeHtml(role.actions.join(', ') || 'no actions')}${role.conditions.length ? `<small>when ${escapeHtml(role.conditions.join(' · '))}</small>` : ''}</button>`,
    );
    const states = [
      ...Object.entries(node.parameters).map(([id, value]) => `${escapeHtml(id)} = ${value}`),
      ...node.states.map(escapeHtml),
      ...node.traits.map((value) => `trait ${escapeHtml(value)}`),
      ...node.initial.map(escapeHtml),
    ];
    const decisions = node.decisions.map(
      (decision) =>
        `<strong>${escapeHtml(decision.id)}</strong>: ${decision.branches.map((branch) => `${escapeHtml(branch.action)} (${escapeHtml(branch.probability)}${branch.condition ? ` if ${escapeHtml(branch.condition)}` : ''})`).join(' · ')}`,
    );
    const actions = node.actions.map(
      (action) =>
        `<strong>${escapeHtml(action.id)}</strong> · ${escapeHtml(action.duration)}${action.effects.length ? `<br>${action.effects.map(escapeHtml).join(' · ')}` : ''}`,
    );
    const couplings = node.couplings.map(
      (coupling) =>
        `<strong>${escapeHtml(coupling.id)}</strong> · ${escapeHtml(coupling.source)} → ${escapeHtml(coupling.target)} · ${syncLabel(coupling.sync_interval_days)}<br>${escapeHtml(coupling.formula)}`,
    );
    const aggregate = node.aggregate
      ? [
          `<strong>${escapeHtml(node.aggregate.id)}</strong> · valid ${node.aggregate.valid_for_days} days · ${escapeHtml(this.cacheStatus.get(node.id) ?? 'not evaluated this session')}`,
          ...node.aggregate.inputs.map(
            (input) =>
              `${escapeHtml(input.id)} = ${input.default} · range ${input.minimum}..${input.maximum} · invalidate ±${input.invalidate_threshold}`,
          ),
        ]
      : [];
    const roleAcrossProgram = this.roleFilter
      ? (this.graph?.nodes ?? []).flatMap((candidate) =>
          candidate.roles_exposed
            .filter((role) => role.id === this.roleFilter)
            .map(
              (role) =>
                `<strong>${escapeHtml(candidate.id)}</strong> · ${escapeHtml(role.actions.join(', ') || 'no actions')}${role.conditions.length ? `<br>when ${escapeHtml(role.conditions.join(' · '))}` : ''}`,
            ),
        )
      : [];
    host.innerHTML = `<header><span>${escapeHtml(label(node.level))}</span><h3>${escapeHtml(node.id)}</h3><p>${escapeHtml(label(node.vertical_slice))} · line ${node.line}</p><button type="button" data-view-code="${node.line}">View in code</button></header>
      ${this.roleFilter ? section(`${this.roleFilter} across program`, roleAcrossProgram) : ''}
      ${section('State / Parameters', states)}
      ${section('Decisions', decisions)}
      ${section('Actions', actions)}
      ${section('Roles exposed', roles)}
      ${section('Subtree roles', node.subtree_roles.map(escapeHtml))}
      ${section('Places', node.places.map(escapeHtml))}
      ${section('Outputs', node.outputs.map(escapeHtml))}
      ${section('Couplings', couplings)}
      ${section('Aggregate / Cache', aggregate)}`;
  }

  private renderEdges(): void {
    const canvas = this.host.querySelector<HTMLElement>('[data-graph-canvas]');
    const svg = this.host.querySelector<SVGSVGElement>('.dsl-graph-edges');
    if (!canvas || !svg || !this.graph) return;
    const canvasRect = canvas.getBoundingClientRect();
    const nodes = new Map(
      [...this.host.querySelectorAll<HTMLElement>('[data-graph-node]')].map((element) => [
        element.dataset.graphNode!,
        element,
      ]),
    );
    const width = canvas.scrollWidth;
    const height = canvas.scrollHeight;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('width', String(width));
    svg.setAttribute('height', String(height));
    svg.innerHTML = this.graph.edges
      .filter((edge) => nodes.has(edge.from_id) && nodes.has(edge.to_id))
      .map((edge) => {
        const from = nodes.get(edge.from_id)!.getBoundingClientRect();
        const to = nodes.get(edge.to_id)!.getBoundingClientRect();
        const x1 = (from.left + from.right) / 2 - canvasRect.left;
        const y1 = from.bottom - canvasRect.top;
        const x2 = (to.left + to.right) / 2 - canvasRect.left;
        const y2 = to.top - canvasRect.top;
        const middle = (y1 + y2) / 2;
        const labelText = edge.kind === 'coupling' ? syncLabel(edge.sync_interval_days) : '';
        return `<g class="${edge.kind}" data-edge-id="${escapeHtml(edge.id)}"><title>${escapeHtml(edge.formula ?? edge.id)}</title><path d="M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}"></path>${labelText ? `<text x="${(x1 + x2) / 2}" y="${middle - 4}">${labelText}</text>` : ''}</g>`;
      })
      .join('');
  }

  private applyTransform(): void {
    const canvas = this.host.querySelector<HTMLElement>('[data-graph-canvas]');
    if (!canvas) return;
    canvas.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
  }

  private fit(): void {
    const viewport = this.host.querySelector<HTMLElement>('[data-graph-viewport]');
    const canvas = this.host.querySelector<HTMLElement>('[data-graph-canvas]');
    if (!viewport || !canvas) return;
    this.scale = Math.min(1, viewport.clientWidth / Math.max(canvas.scrollWidth, 1));
    this.panX = 0;
    this.panY = 0;
    this.applyTransform();
  }

  private readonly onClick = (event: MouseEvent): void => {
    const target = event.target as Element;
    const node = target.closest<HTMLElement>('[data-graph-node]');
    const collapse = target.closest<HTMLButtonElement>('[data-collapse-node]');
    const subtreeRoles = target.closest<HTMLButtonElement>('[data-subtree-roles]');
    const role = target.closest<HTMLButtonElement>('[data-role-filter]');
    const code = target.closest<HTMLButtonElement>('[data-view-code]');
    const control = target.closest<HTMLButtonElement>('[data-graph-control]');
    if (collapse) {
      event.stopPropagation();
      const id = collapse.dataset.collapseNode!;
      this.collapsed.has(id) ? this.collapsed.delete(id) : this.collapsed.add(id);
      this.render();
      return;
    }
    if (subtreeRoles) {
      event.stopPropagation();
      const id = subtreeRoles.dataset.subtreeRoles!;
      this.expandedSubtreeRoles.has(id)
        ? this.expandedSubtreeRoles.delete(id)
        : this.expandedSubtreeRoles.add(id);
      this.render();
      return;
    }
    if (role) {
      event.stopPropagation();
      const id = role.dataset.roleFilter!;
      this.roleFilter = this.roleFilter === id ? '' : id;
      this.render();
      return;
    }
    if (code) {
      this.options.onViewCode(Number(code.dataset.viewCode));
      return;
    }
    if (control) {
      const action = control.dataset.graphControl;
      if (action === 'zoom-in') this.scale = Math.min(2, this.scale + 0.1);
      if (action === 'zoom-out') this.scale = Math.max(0.35, this.scale - 0.1);
      if (action === 'fit') this.fit();
      if (action === 'reset') {
        this.scale = 1;
        this.panX = 0;
        this.panY = 0;
        this.collapsed.clear();
      }
      this.applyTransform();
      if (action === 'reset') this.render();
      return;
    }
    if (node) {
      this.selectedNode = node.dataset.graphNode;
      this.render();
    }
  };

  private readonly onInput = (event: Event): void => {
    const input = (event.target as Element).closest<HTMLInputElement>('[data-graph-search]');
    if (!input) return;
    this.search = input.value;
    this.render();
    this.host.querySelector<HTMLInputElement>('[data-graph-search]')?.focus();
  };

  private readonly onChange = (event: Event): void => {
    const target = event.target as HTMLSelectElement;
    if (target.matches('[data-graph-slice]')) this.slice = target.value;
    if (target.matches('[data-graph-role]')) this.roleFilter = target.value;
    this.render();
  };

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (!(event.target as Element).closest('[data-graph-viewport]')) return;
    if ((event.target as Element).closest('[data-graph-node], button, input, select')) return;
    this.drag = { x: event.clientX, y: event.clientY, panX: this.panX, panY: this.panY };
    this.host.setPointerCapture(event.pointerId);
  };

  private readonly onPointerMove = (event: PointerEvent): void => {
    if (!this.drag) return;
    this.panX = this.drag.panX + event.clientX - this.drag.x;
    this.panY = this.drag.panY + event.clientY - this.drag.y;
    this.applyTransform();
  };

  private readonly onPointerUp = (event: PointerEvent): void => {
    this.drag = undefined;
    if (this.host.hasPointerCapture(event.pointerId))
      this.host.releasePointerCapture(event.pointerId);
  };
}
