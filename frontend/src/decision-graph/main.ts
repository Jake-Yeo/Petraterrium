import './styles.css';
import { api } from '../api';
import type {
  DecisionGraph,
  DecisionGraphEdge,
  RunDetail,
} from '../contracts.generated';
import { escapeHtml as e } from '../views';

type Position = { x: number; y: number };

const option = (value: string, selected: string): string =>
  `<option value="${e(value)}" ${value === selected ? 'selected' : ''}>${e(value || 'All')}</option>`;

const systemColor = (system: string): string => {
  let hash = 0;
  for (const character of system) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 42% 58%)`;
};

function layout(graph: DecisionGraph): Map<string, Position> {
  const incoming = new Map(graph.nodes.map((node) => [node.action_id, 0]));
  const outgoing = new Map(graph.nodes.map((node) => [node.action_id, [] as string[]]));
  graph.edges.forEach((edge) => {
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  });
  const levels = new Map<string, number>();
  const queue = graph.nodes
    .filter((node) => (incoming.get(node.action_id) ?? 0) === 0)
    .map((node) => node.action_id);
  queue.forEach((identity) => levels.set(identity, 0));
  while (queue.length) {
    const source = queue.shift()!;
    for (const target of outgoing.get(source) ?? []) {
      incoming.set(target, (incoming.get(target) ?? 1) - 1);
      levels.set(target, Math.max(levels.get(target) ?? 0, (levels.get(source) ?? 0) + 1));
      if (incoming.get(target) === 0) queue.push(target);
    }
  }
  const maximum = Math.max(0, ...levels.values());
  graph.nodes.forEach((node) => {
    if (!levels.has(node.action_id)) levels.set(node.action_id, maximum + 1);
  });
  const groups = new Map<number, string[]>();
  graph.nodes.forEach((node) => {
    const level = levels.get(node.action_id)!;
    groups.set(level, [...(groups.get(level) ?? []), node.action_id]);
  });
  const width = 980;
  const height = Math.max(470, Math.max(...Array.from(groups.values()).map((items) => items.length)) * 105);
  const columns = Math.max(1, groups.size);
  const positions = new Map<string, Position>();
  Array.from(groups.entries())
    .sort(([left], [right]) => left - right)
    .forEach(([, identities], column) => {
      identities.sort().forEach((identity, row) => {
        positions.set(identity, {
          x: columns === 1 ? width / 2 : 90 + (column * (width - 180)) / (columns - 1),
          y: ((row + 1) * height) / (identities.length + 1),
        });
      });
    });
  return positions;
}

export class DecisionGraphView {
  private active = false;
  private run?: RunDetail;
  private graph?: DecisionGraph;
  private agentId = '';
  private state = '';
  private segment = '';
  private place = '';
  private role = '';
  private search = '';
  private topOnly = false;
  private timeline = Number.MAX_SAFE_INTEGER;

  constructor(private host: HTMLElement) {
    host.addEventListener('click', this.onClick);
    host.addEventListener('change', this.onChange);
    host.addEventListener('input', this.onInput);
  }

  async activate(run?: RunDetail): Promise<void> {
    this.active = true;
    this.run = run;
    if (!run) {
      this.host.innerHTML =
        '<section class="decision-loading">Run a simulation to inspect recorded action transitions.</section>';
      return;
    }
    await this.load();
  }

  deactivate(): void {
    this.active = false;
  }

  async setRun(run?: RunDetail): Promise<void> {
    this.run = run;
    if (this.active) await this.activate(run);
  }

  selectAgent(agentId: string): void {
    this.agentId = agentId;
  }

  private query(): URLSearchParams {
    const query = new URLSearchParams();
    for (const [key, value] of [
      ['state', this.state],
      ['segment', this.segment],
      ['place', this.place],
      ['role', this.role],
      ['agent_id', this.agentId],
    ]) {
      if (value) query.set(key, value);
    }
    return query;
  }

  private async load(): Promise<void> {
    if (!this.run) return;
    this.host.innerHTML = '<section class="decision-loading">Loading decision graph…</section>';
    try {
      this.graph = await api.runDecisionGraph(this.run.run_id, this.query());
      this.timeline = this.graph.filter_options.maximum_tick;
      if (this.active) this.render();
    } catch (error) {
      this.host.innerHTML = `<section class="decision-loading decision-error">${e(error instanceof Error ? error.message : String(error))}</section>`;
    }
  }

  private render(): void {
    if (!this.graph) return;
    const graph = this.graph;
    this.host.innerHTML = `
      <section class="decision-header">
        <div><p class="eyebrow">RECORDED ACTION TRANSITIONS</p><h1>Decision graph</h1><p>Inspect recorded frequencies, role gates, delays, and spotlight paths.</p></div>
      </section>
      <section class="decision-controls">
        <label>State<select id="graph-state">${option('', this.state)}${graph.filter_options.states.map((value) => option(value, this.state)).join('')}</select></label>
        <label>Segment<select id="graph-segment">${option('', this.segment)}${graph.filter_options.segments.map((value) => option(value, this.segment)).join('')}</select></label>
        <label>Place<select id="graph-place">${option('', this.place)}${graph.filter_options.places.map((value) => option(value, this.place)).join('')}</select></label>
        <label>Role<select id="graph-role">${option('', this.role)}${graph.filter_options.roles.map((value) => option(value, this.role)).join('')}</select></label>
        <label>Spotlight agent<select id="graph-agent">${option('', this.agentId)}${graph.filter_options.agents.map((value) => option(value, this.agentId)).join('')}</select></label>
        <label>Find action<input id="graph-search" type="search" value="${e(this.search)}" placeholder="repost"></label>
        <label class="decision-check"><input id="graph-top" type="checkbox" ${this.topOnly ? 'checked' : ''}> Top transitions</label>
      </section>
      <div class="decision-receipt"><span class="field-status ${graph.unfiltered ? 'imputed' : 'present'}">${graph.unfiltered ? 'UNFILTERED VIEW' : 'FILTERED VIEW'}</span><span>${graph.nodes.length} actions · ${graph.edges.length} allowed edges · ${graph.edges.reduce((total, edge) => total + edge.observed_count, 0)} recorded transitions</span></div>
      <section class="decision-workspace">
        <div><div id="decision-canvas" class="decision-canvas"></div>${this.pathControls()}</div>
        <aside id="decision-inspector" class="decision-inspector">${this.defaultInspector()}</aside>
      </section>
      ${this.diagnostics()}
      ${this.transitionMatrix()}`;
    this.renderCanvas();
  }

  private visibleEdges(): DecisionGraphEdge[] {
    if (!this.graph) return [];
    const sorted = [...this.graph.edges].sort(
      (left, right) =>
        right.observed_count - left.observed_count ||
        left.edge_id.localeCompare(right.edge_id),
    );
    return this.topOnly ? sorted.slice(0, Math.max(1, Math.ceil(sorted.length / 2))) : sorted;
  }

  private activePath(): { actions: Set<string>; edges: Set<string> } {
    const steps = (this.graph?.path ?? []).filter((step) => step.tick <= this.timeline);
    return {
      actions: new Set(steps.map((step) => step.action_id)),
      edges: new Set(
        steps
          .filter((step) => step.previous_action_id)
          .map((step) => `${step.previous_action_id}:${step.action_id}`),
      ),
    };
  }

  private renderCanvas(): void {
    if (!this.graph) return;
    const target = this.host.querySelector<HTMLElement>('#decision-canvas');
    if (!target) return;
    const positions = layout(this.graph);
    const path = this.activePath();
    const edges = this.visibleEdges();
    const maximumCount = Math.max(1, ...this.graph.nodes.map((node) => node.observed_count));
    target.innerHTML = `
      <svg viewBox="0 0 980 560" role="img" aria-label="Decision graph with action nodes and transition edges">
        <defs><marker id="decision-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs>
        <g class="decision-edges">${edges
          .map((edge, index) => {
            const source = positions.get(edge.source)!;
            const destination = positions.get(edge.target)!;
            const active = path.edges.has(`${edge.source}:${edge.target}`);
            const width = 1 + edge.observed_frequency * 7;
            const curve = Math.max(40, Math.abs(destination.x - source.x) * 0.45);
            const d = `M ${source.x} ${source.y} C ${source.x + curve} ${source.y}, ${destination.x - curve} ${destination.y}, ${destination.x} ${destination.y}`;
            return `<path class="decision-edge ${active ? 'path-active' : ''}" d="${d}" style="stroke-width:${width}" marker-end="url(#decision-arrow)" ${edge.delay_ticks ? 'stroke-dasharray="7 6"' : ''}></path><path class="decision-edge-hit" d="${d}" data-graph-edge="${index}" aria-label="${e(edge.source)} to ${e(edge.target)}"></path>`;
          })
          .join('')}</g>
        <g class="decision-nodes">${this.graph.nodes
          .map((node) => {
            const point = positions.get(node.action_id)!;
            const radius = 31 + Math.sqrt(node.observed_count / maximumCount) * 13;
            const matches = !this.search || node.action_id.toLowerCase().includes(this.search.toLowerCase());
            return `<g class="decision-node ${path.actions.has(node.action_id) ? 'path-active' : ''} ${matches ? '' : 'search-dim'}" transform="translate(${point.x} ${point.y})" data-graph-node="${e(node.action_id)}" tabindex="0" role="button" aria-label="Inspect ${e(node.action_id)}"><circle r="${radius}" style="--node-color:${systemColor(node.system)}"></circle><text text-anchor="middle" y="-3">${e(node.action_id)}</text><text class="node-count" text-anchor="middle" y="13">${node.observed_count} logs</text></g>`;
          })
          .join('')}</g>
      </svg>`;
  }

  private pathControls(): string {
    if (!this.graph?.path.length)
      return '<div class="decision-path-empty">Choose a spotlight agent to inspect an ordered recorded path.</div>';
    return `<div class="decision-path"><label>Spotlight timeline <input id="graph-timeline" type="range" min="0" max="${this.graph.filter_options.maximum_tick}" value="${this.timeline}"></label><span class="mono">THROUGH TICK ${this.timeline}</span><ol>${this.graph.path
      .filter((step) => step.tick <= this.timeline)
      .map(
        (step) => `<li><span>${step.tick}</span><strong>${e(step.action_id)}</strong><small>${step.previous_action_id ? `${e(step.previous_action_id)} → ` : ''}${e(step.action_id)}${step.target_agent_id ? ` → agent ${e(step.target_agent_id.slice(0, 8))}` : ''}</small></li>`,
      )
      .join('')}</ol></div>`;
  }

  private defaultInspector(): string {
    return `<span class="small-label">INSPECTOR</span><h2>Select a node or edge</h2><p>Nodes show action metadata. Edges show intended probability, formula, delay, conditions, and recorded samples.</p>`;
  }

  private inspectNode(identity: string): void {
    const node = this.graph?.nodes.find((item) => item.action_id === identity);
    const target = this.host.querySelector<HTMLElement>('#decision-inspector');
    if (!node || !target) return;
    const prerequisites = [
      node.source_state ? `state ${node.source_state}` : '',
      node.opportunity ? `opportunity ${node.opportunity}` : '',
      node.parameter ? `parameter ${node.parameter}` : '',
    ].filter(Boolean);
    const roleGate = [
      node.requires_role ? `actor ${node.requires_role}` : '',
      node.target_requires_role ? `target ${node.target_requires_role}` : '',
    ].filter(Boolean);
    const priorityModifiers = Object.entries(node.priority_modifiers)
      .map(([name, value]) => `${e(name)} ${value >= 0 ? '+' : ''}${value}`)
      .join(', ');
    target.innerHTML = `<span class="small-label">ACTION NODE / ${e(node.system)}</span><h2>${e(node.action_id)}</h2><dl><div><dt>Base P(action)</dt><dd>${node.base_probability} / ${e(node.time_unit)}</dd></div><div><dt>Observed logs</dt><dd>${node.observed_count}</dd></div><div><dt>Prerequisites</dt><dd>${prerequisites.map(e).join(', ') || 'None declared'}</dd></div><div><dt>Role gate</dt><dd>${roleGate.map(e).join(', ') || 'Any role'}</dd></div><div><dt>Priority</dt><dd>${node.priority}${priorityModifiers ? ` · ${priorityModifiers}` : ''}</dd></div><div><dt>Duration</dt><dd>${node.duration_minutes} min</dd></div><div><dt>Conflict policy</dt><dd>${e(node.loser_outcome)} · ${node.reschedulable ? 'reschedulable' : 'not reschedulable'}</dd></div><div><dt>Interruptible</dt><dd>${node.interruptible ? 'Yes' : 'No'}</dd></div><div><dt>Protected</dt><dd>${node.protected ? 'Yes' : 'No'}</dd></div><div><dt>Compatible</dt><dd>${node.compatible_with.map(e).join(', ') || 'None declared'}</dd></div></dl>`;
  }

  private inspectEdge(edge: DecisionGraphEdge): void {
    const target = this.host.querySelector<HTMLElement>('#decision-inspector');
    if (!target) return;
    target.innerHTML = `<span class="small-label">TRANSITION EDGE / ${e(edge.chain_id)}</span><h2>${e(edge.source)} → ${e(edge.target)}</h2><p class="edge-formula">${e(edge.formula)}</p><dl><div><dt>Intended</dt><dd>${(edge.intended_probability * 100).toFixed(1)}%</dd></div><div><dt>Observed</dt><dd>${(edge.observed_frequency * 100).toFixed(1)}% · ${edge.observed_count} logs</dd></div><div><dt>Delay</dt><dd>${e(edge.delay_label)}</dd></div><div><dt>Chain outcome</dt><dd>${edge.terminates ? 'Terminates' : 'May continue'}</dd></div><div><dt>Propagation</dt><dd>${edge.cross_agent ? 'Cross-agent' : 'Within-agent'}</dd></div><div><dt>Conditions</dt><dd>${Object.entries(edge.conditions).map(([key, value]) => `${e(key)}=${e(value)}`).join(', ') || 'No branch condition'}</dd></div><div><dt>Sample agents</dt><dd>${edge.sample_agents.map((agent) => e(agent.slice(0, 10))).join(', ') || 'No recorded sample'}</dd></div></dl>`;
  }

  private diagnostics(): string {
    if (!this.graph?.diagnostics.length) return '';
    return `<section class="decision-diagnostics"><div><p class="eyebrow">VALIDATION</p><h2>Graph diagnostics</h2></div><ul>${this.graph.diagnostics.map((item) => `<li><span>${e(item.kind.replaceAll('_', ' '))}</span><strong>${e(item.subject)}</strong><p>${e(item.message)}</p></li>`).join('')}</ul></section>`;
  }

  private transitionMatrix(): string {
    if (!this.graph) return '';
    const rows = Object.entries(this.graph.transition_matrix);
    return `<details class="decision-matrix"><summary><div><span class="eyebrow">MASSES</span><strong>Aggregated transition matrix</strong></div><span>${rows.length} source actions</span></summary><div class="table-scroll"><table><thead><tr><th>From</th><th>To</th><th>Recorded count</th></tr></thead><tbody>${rows.flatMap(([source, targets]) => Object.entries(targets).map(([target, count]) => `<tr><th>${e(source)}</th><td>${e(target)}</td><td>${count.toLocaleString()}</td></tr>`)).join('')}</tbody></table></div></details>`;
  }

  private onClick = (event: MouseEvent): void => {
    const element = event.target as Element;
    const node = element.closest<SVGGElement>('[data-graph-node]');
    if (node?.dataset.graphNode) this.inspectNode(node.dataset.graphNode);
    const edgeElement = element.closest<SVGPathElement>('[data-graph-edge]');
    if (edgeElement?.dataset.graphEdge && this.graph) {
      const edge = this.visibleEdges()[Number(edgeElement.dataset.graphEdge)];
      if (edge) this.inspectEdge(edge);
    }
  };

  private onChange = (event: Event): void => {
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    if (target.id === 'graph-state') this.state = target.value;
    else if (target.id === 'graph-segment') this.segment = target.value;
    else if (target.id === 'graph-place') this.place = target.value;
    else if (target.id === 'graph-role') this.role = target.value;
    else if (target.id === 'graph-agent') this.agentId = target.value;
    else if (target.id === 'graph-top') {
      this.topOnly = (target as HTMLInputElement).checked;
      this.renderCanvas();
      return;
    } else return;
    void this.load();
  };

  private onInput = (event: Event): void => {
    const target = event.target as HTMLInputElement;
    if (target.id === 'graph-search') {
      this.search = target.value;
      this.renderCanvas();
    }
    if (target.id === 'graph-timeline') {
      this.timeline = Number(target.value);
      this.render();
    }
  };
}
