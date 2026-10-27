import './styles.css';
import { escapeHtml as e } from '../views';
import { markovBuilderApi } from './api';
import type {
  ChainDraft,
  ChainNodeDraft,
  ChainTransitionDraft,
  ChainValidationResult,
  ConfirmationResult,
  MarkovBuilderApi,
  OutgoingProbabilityTotal,
  ProposalAudit,
  ProposalOrigin,
} from './types';

export interface MarkovChainBuilderOptions {
  api?: MarkovBuilderApi;
  initialText?: string;
  onConfirmed?: (result: ConfirmationResult) => Promise<void> | void;
}

type Point = { x: number; y: number };

let builderSequence = 0;

const slug = (value: string, fallback: string): string => {
  let identity = value
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
  if (!identity) identity = fallback;
  if (!/^[a-z]/.test(identity)) identity = `${fallback}_${identity}`;
  return identity.slice(0, 80).replace(/_+$/g, '');
};

const option = (value: string, label: string, selected: string | null): string =>
  `<option value="${e(value)}" ${value === selected ? 'selected' : ''}>${e(label)}</option>`;

const originLabel = (origin: ProposalOrigin): string =>
  ({
    user_explicit: 'From your text',
    model_proposal: 'Model proposal',
    structural: 'Draft structure',
    manual_edit: 'Edited by you',
  })[origin];

const percentage = (value: number): string => `${(value * 100).toFixed(2).replace(/\.00$/, '')}%`;

export class MarkovChainBuilder {
  private readonly api: MarkovBuilderApi;
  private readonly markerId: string;
  private prompt: string;
  private draft?: ChainDraft;
  private validation?: ChainValidationResult;
  private audit?: ProposalAudit;
  private busy = false;
  private message = '';
  private error = '';
  private validationSequence = 0;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: MarkovChainBuilderOptions = {},
  ) {
    this.api = options.api ?? markovBuilderApi;
    this.prompt = options.initialText ?? '';
    this.markerId = `markov-arrow-${++builderSequence}`;
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('input', this.onInput);
  }

  activate(): void {
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('input', this.onInput);
  }

  currentDraft(): ChainDraft | undefined {
    return this.draft ? structuredClone(this.draft) : undefined;
  }

  private render(): void {
    this.host.innerHTML = `
      <section class="markov-builder" aria-labelledby="markov-builder-title">
        <header class="markov-builder-header">
          <div>
            <p class="eyebrow">DECISION TREE BUILDER</p>
            <h1 id="markov-builder-title">Describe a decision</h1>
            <p>Turn explicit states and transitions into a reviewable draft. Unknown numbers stay unknown until you supply evidence.</p>
          </div>
          ${this.draft ? '<button class="button secondary" data-markov-action="reset">Start over</button>' : ''}
        </header>
        <section class="markov-prompt-card">
          <label for="markov-prompt">What should happen?</label>
          <textarea id="markov-prompt" rows="4" placeholder="An agent decides whether to stay at home or go out">${e(this.prompt)}</textarea>
          <div class="markov-prompt-actions">
            <label class="markov-check"><input id="markov-use-model" type="checkbox" checked> Use the configured model when available</label>
            <button class="button primary" data-markov-action="propose" ${this.busy ? 'disabled' : ''}>${this.busy ? 'Building draft…' : 'Propose chain'}</button>
          </div>
        </section>
        ${this.feedback()}
        ${this.draft ? this.editor() : this.emptyState()}
      </section>`;
  }

  private feedback(): string {
    const audit = this.audit
      ? `<div class="markov-audit"><strong>${e(this.audit.provider === 'deterministic-parser' ? 'Explicit parser' : this.audit.model)}</strong><span>${e(this.audit.message)}</span></div>`
      : '';
    const message = this.message ? `<p class="markov-message">${e(this.message)}</p>` : '';
    const error = this.error ? `<p class="markov-error" role="alert">${e(this.error)}</p>` : '';
    return `${audit}${message}${error}`;
  }

  private emptyState(): string {
    return `
      <section class="markov-empty">
        <strong>No chain draft yet</strong>
        <p>Describe the choice in plain language. The draft will show missing probabilities, conditions, terminal states, and graph problems before anything can be saved.</p>
        <small>Explicit syntax also works: Decision → Home [terminal] | 60% if weekend</small>
      </section>`;
  }

  private editor(): string {
    const draft = this.draft!;
    const validation = this.validation;
    const terminalCount = validation?.terminal_states.length ?? draft.nodes.filter((node) => node.terminal).length;
    const terminalLabel = `${terminalCount} terminal ${terminalCount === 1 ? 'state' : 'states'}`;
    return `
      <section class="markov-editor">
        <div class="markov-editor-heading">
          <div><p class="eyebrow">UNSAVED DRAFT</p><h2>${e(draft.name)}</h2></div>
          <span class="markov-status ${validation?.can_confirm ? 'ready' : 'blocked'}">${validation?.can_confirm ? 'Ready for confirmation' : 'Needs review'}</span>
        </div>
        <div class="markov-metadata">
          <label>Chain id<input data-markov-meta="id" value="${e(draft.id)}"></label>
          <label>Name<input data-markov-meta="name" value="${e(draft.name)}"></label>
          <label>Entry state<select data-markov-meta="entry_node"><option value="">Choose entry state</option>${draft.nodes.map((node) => option(node.id, node.label, draft.entry_node)).join('')}</select></label>
        </div>
        <div class="markov-workspace">
          <section class="markov-preview" aria-label="Markov chain graph preview">
            <div class="markov-section-heading"><div><p class="eyebrow">GRAPH PREVIEW</p><h3>States and transitions</h3></div><span>${draft.nodes.length} states · ${draft.transitions.length} edges · ${terminalLabel}</span></div>
            ${this.graph()}
          </section>
          ${this.diagnostics()}
        </div>
        ${this.nodeEditor()}
        ${this.transitionEditor()}
        <footer class="markov-confirm">
          <div><strong>Explicit confirmation required</strong><p>Saving is blocked until every transition has a probability and condition, each outgoing total is 100%, and every path terminates.</p></div>
          <button class="button primary" data-markov-action="confirm" ${!validation?.can_confirm || this.busy ? 'disabled' : ''}>Confirm and save decision tree</button>
        </footer>
      </section>`;
  }

  private graph(): string {
    const draft = this.draft!;
    if (!draft.nodes.length) return '<div class="markov-graph-empty">Add a state to begin.</div>';
    const width = 920;
    const columns = Math.min(4, Math.max(1, draft.nodes.length));
    const rows = Math.ceil(draft.nodes.length / columns);
    const height = Math.max(310, rows * 150);
    const positions = new Map<string, Point>();
    draft.nodes.forEach((node, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      positions.set(node.id, {
        x: columns === 1 ? width / 2 : 100 + (column * (width - 200)) / (columns - 1),
        y: 85 + row * 150,
      });
    });
    const totalByNode = new Map(
      (this.validation?.outgoing_totals ?? []).map((item) => [item.node_id, item]),
    );
    const paths = draft.transitions
      .map((edge) => this.edgeSvg(edge, positions))
      .join('');
    const nodes = draft.nodes
      .map((node) => this.nodeSvg(node, positions.get(node.id)!, totalByNode.get(node.id)))
      .join('');
    return `<div class="markov-graph-scroll"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Editable Markov chain with ${draft.nodes.length} states and ${draft.transitions.length} transitions"><defs><marker id="${this.markerId}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs><g class="markov-edges">${paths}</g><g class="markov-nodes">${nodes}</g></svg></div>`;
  }

  private edgeSvg(edge: ChainTransitionDraft, positions: Map<string, Point>): string {
    const source = positions.get(edge.from_node);
    const target = positions.get(edge.to_node);
    if (!source || !target) return '';
    const self = edge.from_node === edge.to_node;
    const path = self
      ? `M ${source.x + 42} ${source.y - 18} C ${source.x + 100} ${source.y - 90}, ${source.x - 100} ${source.y - 90}, ${source.x - 42} ${source.y - 18}`
      : `M ${source.x + 46} ${source.y} C ${(source.x + target.x) / 2} ${source.y}, ${(source.x + target.x) / 2} ${target.y}, ${target.x - 46} ${target.y}`;
    const labelX = self ? source.x : (source.x + target.x) / 2;
    const labelY = self ? source.y - 70 : (source.y + target.y) / 2 - 8;
    const probability = edge.probability === null ? 'P unknown' : percentage(edge.probability);
    return `<g class="markov-edge ${edge.probability === null || !edge.condition ? 'unresolved' : ''}"><path d="${path}" marker-end="url(#${this.markerId})"></path><text x="${labelX}" y="${labelY}" text-anchor="middle"><tspan>${e(probability)}</tspan><tspan x="${labelX}" dy="13">${e(edge.condition || 'condition missing')}</tspan></text></g>`;
  }

  private nodeSvg(
    node: ChainNodeDraft,
    point: Point,
    total: OutgoingProbabilityTotal | undefined,
  ): string {
    const summary = node.terminal
      ? 'Terminal'
      : total?.complete
        ? `Outgoing ${percentage(total.known_total)}`
        : `Known ${percentage(total?.known_total ?? 0)} · ${total?.unknown_count ?? 0} unknown`;
    const className = [
      'markov-node',
      node.terminal ? 'terminal' : '',
      this.draft?.entry_node === node.id ? 'entry' : '',
      total && !total.sums_to_one ? 'invalid' : '',
    ]
      .filter(Boolean)
      .join(' ');
    return `<g class="${className}" transform="translate(${point.x} ${point.y})"><rect x="-67" y="-32" width="134" height="64" rx="8"></rect><text text-anchor="middle"><tspan x="0" y="-5">${e(node.label)}</tspan><tspan class="markov-node-total" x="0" y="14">${e(summary)}</tspan></text></g>`;
  }

  private diagnostics(): string {
    const validation = this.validation;
    if (!validation) {
      return '<aside class="markov-diagnostics"><p>Checking graph…</p></aside>';
    }
    const terminalRows = validation.terminal_states.map(
      (identity) => `<li class="ok"><strong>${e(identity)}</strong><span>Terminal · no outgoing total required</span></li>`,
    );
    const totalRows = validation.outgoing_totals.map((total) => {
      const status = total.sums_to_one ? 'ok' : 'error';
      const unknown = total.unknown_count
        ? ` · ${total.unknown_count} unknown ${total.unknown_count === 1 ? 'edge' : 'edges'}`
        : '';
      return `<li class="${status}"><strong>${e(total.node_id)}</strong><span>${percentage(total.known_total)} outgoing${unknown}</span></li>`;
    });
    const issues = validation.issues.length
      ? validation.issues
          .map(
            (issue) => `<li class="${issue.severity}"><span>${e(issue.code.replaceAll('_', ' '))}</span><p>${e(issue.message)}</p></li>`,
          )
          .join('')
      : '<li class="ok"><span>Graph valid</span><p>All outgoing totals and termination paths are complete.</p></li>';
    return `
      <aside class="markov-diagnostics">
        <div class="markov-section-heading"><div><p class="eyebrow">VALIDATION</p><h3>${validation.can_confirm ? 'Ready to confirm' : 'Resolve before saving'}</h3></div></div>
        <h4>Every state</h4>
        <ul class="markov-totals">${[...totalRows, ...terminalRows].join('')}</ul>
        <h4>Checks</h4>
        <ul class="markov-issues">${issues}</ul>
      </aside>`;
  }

  private nodeEditor(): string {
    const draft = this.draft!;
    return `
      <section class="markov-table-section">
        <div class="markov-section-heading"><div><p class="eyebrow">STATES</p><h3>Edit nodes</h3></div><button class="button secondary" data-markov-action="add-node">Add state</button></div>
        <div class="markov-table-scroll"><table><thead><tr><th>Id</th><th>Label</th><th>Origin</th><th>Terminal</th><th></th></tr></thead><tbody>${draft.nodes
          .map(
            (node, index) => `<tr><td><input data-node-index="${index}" data-node-field="id" value="${e(node.id)}" aria-label="Node id"></td><td><input data-node-index="${index}" data-node-field="label" value="${e(node.label)}" aria-label="Node label"></td><td><span class="markov-origin ${e(node.origin)}">${e(originLabel(node.origin))}</span></td><td><label class="markov-terminal"><input type="checkbox" data-node-index="${index}" data-node-field="terminal" ${node.terminal ? 'checked' : ''}> Terminal</label></td><td><button class="markov-remove" data-markov-action="remove-node" data-index="${index}" aria-label="Remove ${e(node.label)}">Remove</button></td></tr>`,
          )
          .join('')}</tbody></table></div>
      </section>`;
  }

  private transitionEditor(): string {
    const draft = this.draft!;
    const stateOptions = (selected: string) =>
      draft.nodes.map((node) => option(node.id, node.label, selected)).join('');
    return `
      <section class="markov-table-section">
        <div class="markov-section-heading"><div><p class="eyebrow">TRANSITIONS</p><h3>Edit edges</h3></div><button class="button secondary" data-markov-action="add-edge" ${draft.nodes.length < 2 ? 'disabled' : ''}>Add transition</button></div>
        <div class="markov-table-scroll"><table class="markov-edge-table"><thead><tr><th>Id</th><th>From</th><th>To</th><th>Probability</th><th>Condition</th><th>Origin</th><th></th></tr></thead><tbody>${draft.transitions
          .map(
            (edge, index) => `<tr><td><input data-edge-index="${index}" data-edge-field="id" value="${e(edge.id)}" aria-label="Transition id"></td><td><select data-edge-index="${index}" data-edge-field="from_node" aria-label="From state">${stateOptions(edge.from_node)}</select></td><td><select data-edge-index="${index}" data-edge-field="to_node" aria-label="To state">${stateOptions(edge.to_node)}</select></td><td><input type="number" min="0" max="1" step="0.01" data-edge-index="${index}" data-edge-field="probability" value="${edge.probability ?? ''}" placeholder="Unknown" aria-label="Transition probability"></td><td><input data-edge-index="${index}" data-edge-field="condition" value="${e(edge.condition ?? '')}" placeholder="always, day = Friday…" aria-label="Transition condition"></td><td><span class="markov-origin ${e(edge.origin)}">${e(originLabel(edge.origin))}</span></td><td><button class="markov-remove" data-markov-action="remove-edge" data-index="${index}" aria-label="Remove transition ${e(edge.id)}">Remove</button></td></tr>`,
          )
          .join('')}</tbody></table></div>
      </section>`;
  }

  private onInput = (event: Event): void => {
    const target = event.target as HTMLTextAreaElement;
    if (target.id === 'markov-prompt') this.prompt = target.value;
  };

  private onClick = (event: MouseEvent): void => {
    const target = (event.target as Element).closest<HTMLElement>('[data-markov-action]');
    const action = target?.dataset.markovAction;
    if (!action) return;
    if (action === 'propose') void this.propose();
    if (action === 'reset') this.reset();
    if (action === 'add-node') this.addNode();
    if (action === 'add-edge') this.addEdge();
    if (action === 'remove-node') this.removeNode(Number(target.dataset.index));
    if (action === 'remove-edge') this.removeEdge(Number(target.dataset.index));
    if (action === 'confirm') void this.confirm();
  };

  private onChange = (event: Event): void => {
    if (!this.draft) return;
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    const meta = target.dataset.markovMeta;
    if (meta) {
      if (meta === 'id') this.draft.id = slug(target.value, 'chain');
      if (meta === 'name') this.draft.name = target.value.trim() || 'Untitled chain';
      if (meta === 'entry_node') this.draft.entry_node = target.value || null;
      this.changed();
      return;
    }
    const nodeIndex = Number(target.dataset.nodeIndex);
    const nodeField = target.dataset.nodeField;
    if (nodeField && Number.isInteger(nodeIndex)) {
      this.editNode(nodeIndex, nodeField, target);
      return;
    }
    const edgeIndex = Number(target.dataset.edgeIndex);
    const edgeField = target.dataset.edgeField;
    if (edgeField && Number.isInteger(edgeIndex)) this.editEdge(edgeIndex, edgeField, target);
  };

  private async propose(): Promise<void> {
    const text = this.prompt.trim();
    if (!text) {
      this.error = 'Describe the decision before building a draft.';
      this.render();
      return;
    }
    const useLlm = this.host.querySelector<HTMLInputElement>('#markov-use-model')?.checked ?? true;
    this.busy = true;
    this.error = '';
    this.message = '';
    this.render();
    try {
      const result = await this.api.propose(text, useLlm);
      this.draft = result.draft;
      this.validation = result.validation;
      this.audit = result.audit;
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = false;
      this.render();
    }
  }

  private reset(): void {
    this.draft = undefined;
    this.validation = undefined;
    this.audit = undefined;
    this.error = '';
    this.message = '';
    this.render();
  }

  private addNode(): void {
    if (!this.draft) return;
    const used = new Set(this.draft.nodes.map((node) => node.id));
    let position = this.draft.nodes.length + 1;
    while (used.has(`state_${position}`)) position += 1;
    const identity = `state_${position}`;
    this.draft.nodes.push({
      id: identity,
      label: `State ${position}`,
      terminal: false,
      origin: 'manual_edit',
      source_excerpt: null,
    });
    this.draft.entry_node ??= identity;
    this.changed();
  }

  private addEdge(): void {
    if (!this.draft || this.draft.nodes.length < 2) return;
    const used = new Set(this.draft.transitions.map((edge) => edge.id));
    let position = this.draft.transitions.length + 1;
    while (used.has(`transition_${position}`)) position += 1;
    this.draft.transitions.push({
      id: `transition_${position}`,
      from_node: this.draft.nodes[0]!.id,
      to_node: this.draft.nodes[1]!.id,
      probability: null,
      condition: null,
      origin: 'manual_edit',
      source_excerpt: null,
    });
    this.changed();
  }

  private removeNode(index: number): void {
    if (!this.draft || !this.draft.nodes[index]) return;
    const [removed] = this.draft.nodes.splice(index, 1);
    this.draft.transitions = this.draft.transitions.filter(
      (edge) => edge.from_node !== removed!.id && edge.to_node !== removed!.id,
    );
    if (this.draft.entry_node === removed!.id) {
      this.draft.entry_node = this.draft.nodes[0]?.id ?? null;
    }
    this.changed();
  }

  private removeEdge(index: number): void {
    if (!this.draft || !this.draft.transitions[index]) return;
    this.draft.transitions.splice(index, 1);
    this.changed();
  }

  private editNode(
    index: number,
    field: string,
    target: HTMLInputElement | HTMLSelectElement,
  ): void {
    const node = this.draft?.nodes[index];
    if (!node || !this.draft) return;
    if (field === 'id') {
      const previous = node.id;
      node.id = slug(target.value, `state_${index + 1}`);
      if (this.draft.entry_node === previous) this.draft.entry_node = node.id;
      this.draft.transitions.forEach((edge) => {
        if (edge.from_node === previous) edge.from_node = node.id;
        if (edge.to_node === previous) edge.to_node = node.id;
      });
    }
    if (field === 'label') node.label = target.value.trim() || `State ${index + 1}`;
    if (field === 'terminal' && target instanceof HTMLInputElement) node.terminal = target.checked;
    node.origin = 'manual_edit';
    this.changed();
  }

  private editEdge(
    index: number,
    field: string,
    target: HTMLInputElement | HTMLSelectElement,
  ): void {
    const edge = this.draft?.transitions[index];
    if (!edge) return;
    if (field === 'id') edge.id = slug(target.value, `transition_${index + 1}`);
    if (field === 'from_node') edge.from_node = target.value;
    if (field === 'to_node') edge.to_node = target.value;
    if (field === 'probability') {
      const value = target.value.trim();
      edge.probability = value === '' ? null : Number(value);
    }
    if (field === 'condition') edge.condition = target.value.trim() || null;
    edge.origin = 'manual_edit';
    this.changed();
  }

  private changed(): void {
    if (!this.draft) return;
    this.draft.revision += 1;
    this.validation = undefined;
    this.message = '';
    this.error = '';
    void this.validate();
    this.render();
  }

  private async validate(): Promise<void> {
    if (!this.draft) return;
    const sequence = ++this.validationSequence;
    const draft = structuredClone(this.draft);
    try {
      const validation = await this.api.validate(draft);
      if (sequence !== this.validationSequence) return;
      this.validation = validation;
      this.render();
    } catch (error) {
      if (sequence !== this.validationSequence) return;
      this.error = error instanceof Error ? error.message : String(error);
      this.render();
    }
  }

  private async confirm(): Promise<void> {
    if (!this.draft || !this.validation?.can_confirm) return;
    this.busy = true;
    this.error = '';
    this.render();
    try {
      const result = await this.api.confirm(this.draft);
      await this.options.onConfirmed?.(result);
      this.message = this.options.onConfirmed
        ? 'Decision tree saved. Transition probabilities remain blocked until matching measured or held-out fitted evidence is attached.'
        : result.persisted
          ? `Saved as ${result.persistence_id ?? result.chain.id}.`
          : 'Confirmed decision graph is ready.';
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = false;
      this.render();
    }
  }
}
