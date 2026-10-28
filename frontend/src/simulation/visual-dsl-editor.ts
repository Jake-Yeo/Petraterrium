import './prompt2-ui.css';
import type {
  DslActionDefinition,
  DslCoefficient,
  DslDecisionTree,
  DslDocumentDiff,
  DslDurationDistribution,
  DslEvidence,
  DslStateDefinition,
  DslTreeEdge,
  DslTreeNode,
  DslValidationIssue,
  VisualDslDocument,
} from './dsl-editor-model';
import { diffVisualDsl, validateVisualDsl } from './dsl-editor-validation';
import { cloneValue, escapeHtml, parseFiniteNumber, sentenceCase } from './prompt2-ui-utils';

export interface VisualDslEditorOptions {
  document: VisualDslDocument;
  onConfirm: (document: VisualDslDocument, diff: DslDocumentDiff[]) => Promise<void> | void;
}

type EditorSection = 'actions' | 'states' | 'trees';

const evidenceStatuses: DslEvidence['status'][] = ['measured', 'estimated', 'fitted', 'default'];
const durationShapes: DslDurationDistribution['shape'][] = ['uniform', 'triangular', 'lognormal'];
const nodeKinds: DslTreeNode['kind'][] = ['entry', 'decision', 'action', 'terminal', 'module'];

const uniqueId = (prefix: string, existing: string[]): string => {
  let index = existing.length + 1;
  let candidate = `${prefix}-${index}`;
  while (existing.includes(candidate)) {
    index += 1;
    candidate = `${prefix}-${index}`;
  }
  return candidate;
};

const newEvidence = (): DslEvidence => ({
  status: 'estimated',
  source: 'User-confirmed DSL edit',
  sourceVersion: 'manual-1',
  sourceDate: new Date().toISOString().slice(0, 10),
  uncertainty: 0.5,
  reasoning: 'Editable estimate pending stronger fitted evidence.',
});

export class VisualDslEditor {
  private original: VisualDslDocument;
  private draft: VisualDslDocument;
  private section: EditorSection = 'actions';
  private selectedActionId = '';
  private selectedStateId = '';
  private selectedTreeId = '';
  private reviewing = false;
  private saving = false;
  private error = '';

  constructor(
    private readonly host: HTMLElement,
    private readonly options: VisualDslEditorOptions,
  ) {
    this.original = cloneValue(options.document);
    this.draft = cloneValue(options.document);
    this.resetSelections();
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
    this.render();
  }

  value(): VisualDslDocument {
    return cloneValue(this.draft);
  }

  issues(): DslValidationIssue[] {
    return validateVisualDsl(this.draft);
  }

  diff(): DslDocumentDiff[] {
    return diffVisualDsl(this.original, this.draft);
  }

  update(document: VisualDslDocument): void {
    this.original = cloneValue(document);
    this.draft = cloneValue(document);
    this.reviewing = false;
    this.error = '';
    this.resetSelections();
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.host.replaceChildren();
  }

  private resetSelections(): void {
    this.selectedActionId = this.draft.actions[0]?.id ?? '';
    this.selectedStateId = this.draft.states[0]?.id ?? '';
    this.selectedTreeId = this.draft.trees[0]?.id ?? '';
  }

  private readonly onChange = (event: Event): void => {
    const input =
      event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement
        ? event.target
        : null;
    if (!input?.dataset.dslField) return;
    this.applyField(input);
    this.reviewing = false;
    this.error = '';
    this.render();
  };

  private readonly onClick = (event: Event): void => {
    const button =
      event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>('button[data-dsl-action]')
        : null;
    const action = button?.dataset.dslAction;
    if (!action || this.saving) return;
    const targetId = button?.dataset.targetId ?? '';
    if (action === 'section') this.section = targetId as EditorSection;
    if (action === 'select-action') this.selectedActionId = targetId;
    if (action === 'select-state') this.selectedStateId = targetId;
    if (action === 'select-tree') this.selectedTreeId = targetId;
    if (action === 'add-action') this.addAction();
    if (action === 'add-state') this.addState();
    if (action === 'add-tree') this.addTree();
    if (action === 'add-coefficient') this.addCoefficient();
    if (action === 'delete-coefficient') this.deleteCoefficient(Number(button?.dataset.itemIndex));
    if (action === 'add-threshold') this.addThreshold();
    if (action === 'delete-threshold') this.deleteThreshold(Number(button?.dataset.itemIndex));
    if (action === 'add-node') this.addNode();
    if (action === 'delete-node') this.deleteNode(Number(button?.dataset.itemIndex));
    if (action === 'add-edge') this.addEdge();
    if (action === 'delete-edge') this.deleteEdge(Number(button?.dataset.itemIndex));
    if (action === 'add-requirement')
      this.addRequirement(button?.dataset.requirementKind ?? '', Number(button?.dataset.itemIndex));
    if (action === 'delete-requirement')
      this.deleteRequirement(
        button?.dataset.requirementKind ?? '',
        Number(button?.dataset.itemIndex),
        Number(button?.dataset.requirementIndex),
      );
    if (action === 'revert') {
      this.draft = cloneValue(this.original);
      this.reviewing = false;
      this.error = '';
      this.resetSelections();
    }
    if (action === 'review') this.reviewing = true;
    if (action === 'cancel-review') this.reviewing = false;
    if (action === 'confirm') void this.confirm();
    this.render();
  };

  private async confirm(): Promise<void> {
    const issues = this.issues();
    const diff = this.diff();
    if (issues.some((issue) => issue.severity === 'error') || diff.length === 0) return;
    this.saving = true;
    this.error = '';
    this.render();
    try {
      await this.options.onConfirm(this.value(), diff);
      this.original = cloneValue(this.draft);
      this.reviewing = false;
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.saving = false;
      this.render();
    }
  }

  private selectedAction(): DslActionDefinition | undefined {
    return this.draft.actions.find((action) => action.id === this.selectedActionId);
  }

  private selectedState(): DslStateDefinition | undefined {
    return this.draft.states.find((state) => state.id === this.selectedStateId);
  }

  private selectedTree(): DslDecisionTree | undefined {
    return this.draft.trees.find((tree) => tree.id === this.selectedTreeId);
  }

  private render(): void {
    const issues = this.issues();
    const diff = this.diff();
    const errors = issues.filter((issue) => issue.severity === 'error').length;
    this.host.className = 'prompt2-card visual-dsl-editor';
    this.host.innerHTML = `
      <header class="dsl-editor-heading">
        <div><span class="prompt2-eyebrow">VISUAL DSL BUILDER</span><h3>Simulation definitions</h3><p>Schema ${escapeHtml(this.draft.schema_version)} · DSL ${escapeHtml(this.draft.version)}</p></div>
        <label><span>Tick duration</span><span class="dsl-hours-input"><input type="number" min="0.01" max="24" step="0.01" value="${this.draft.tick_hours}" data-dsl-field="tick_hours" aria-label="Tick duration hours"> hours</span></label>
      </header>
      <nav class="dsl-editor-tabs" aria-label="DSL definition sections">${(['actions', 'states', 'trees'] as EditorSection[]).map((section) => `<button type="button" role="tab" aria-selected="${this.section === section}" data-dsl-action="section" data-target-id="${section}">${sentenceCase(section)} <span>${this.draft[section].length}</span></button>`).join('')}</nav>
      <div class="dsl-editor-workspace">
        ${this.listMarkup()}
        <section class="dsl-editor-detail">${this.detailMarkup()}</section>
      </div>
      <section class="dsl-editor-audit" data-dsl-audit>
        <div class="dsl-editor-audit-summary"><span class="${errors ? 'is-invalid' : ''}">${errors ? `${errors} validation ${errors === 1 ? 'error' : 'errors'}` : 'Valid for confirmation'}</span><span>${issues.length - errors} warnings</span><span>${diff.length} staged changes</span></div>
        ${this.issueMarkup(issues)}
        ${this.diffMarkup(diff)}
      </section>
      ${this.reviewing ? this.confirmMarkup(diff, errors) : ''}
      ${this.error ? `<p class="dsl-editor-error" role="alert">${escapeHtml(this.error)}</p>` : ''}
      <footer class="dsl-editor-actions"><button type="button" data-dsl-action="revert" ${diff.length === 0 || this.saving ? 'disabled' : ''}>Revert staged changes</button><button type="button" class="prompt2-primary" data-dsl-action="review" ${diff.length === 0 || errors || this.saving ? 'disabled' : ''}>Review and confirm changes</button></footer>
    `;
  }

  private listMarkup(): string {
    const config = {
      actions: {
        items: this.draft.actions,
        selected: this.selectedActionId,
        select: 'select-action',
        add: 'add-action',
        label: 'Add action',
      },
      states: {
        items: this.draft.states,
        selected: this.selectedStateId,
        select: 'select-state',
        add: 'add-state',
        label: 'Add state',
      },
      trees: {
        items: this.draft.trees,
        selected: this.selectedTreeId,
        select: 'select-tree',
        add: 'add-tree',
        label: 'Add tree',
      },
    }[this.section];
    return `<aside class="dsl-editor-list"><div>${config.items.map((item) => `<button type="button" class="${item.id === config.selected ? 'is-selected' : ''}" data-dsl-action="${config.select}" data-target-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)}</small></button>`).join('') || '<p>No definitions in this section.</p>'}</div><button type="button" data-dsl-action="${config.add}">+ ${config.label}</button></aside>`;
  }

  private detailMarkup(): string {
    if (this.section === 'actions') return this.actionMarkup(this.selectedAction());
    if (this.section === 'states') return this.stateMarkup(this.selectedState());
    return this.treeMarkup(this.selectedTree());
  }

  private actionMarkup(action: DslActionDefinition | undefined): string {
    if (!action) return '<p class="dsl-editor-empty">Add an action to begin.</p>';
    return `
      <div class="dsl-editor-title"><div><span class="prompt2-eyebrow">ACTION</span><h3>${escapeHtml(action.name)}</h3><code>${escapeHtml(action.id)}</code></div></div>
      <div class="dsl-form-grid">
        ${this.input('Name', 'action.name', action.name)}
        ${this.input('Description', 'action.description', action.description, 'text', 'wide')}
        ${this.input('Time category', 'action.category', action.category)}
        ${this.input('Priority', 'action.priority', action.priority, 'number')}
        ${this.input('Aggregate statistic', 'action.aggregate_statistic_id', action.aggregate_statistic_id)}
        ${this.select('Mode', 'action.mode', action.mode, ['primary', 'passive'])}
        ${this.select('Interruptibility', 'action.interruptibility', action.interruptibility, ['interruptible', 'protected', 'uninterruptible'])}
        ${this.select('Interruption outcome', 'action.interruption_outcome', action.interruption_outcome, ['defer', 'cancel'])}
        ${this.input('Emergency interrupting actions', 'action.emergency_interruptions', action.emergency_interruptions.join(', '), 'text', 'wide')}
        ${this.input('Formula', 'action.formula', action.formula, 'text', 'wide')}
      </div>
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">DURATION DISTRIBUTION</span><h4>Hours per sampled occurrence</h4></div><span>No fixed durations</span></header>
        <div class="dsl-form-grid duration-grid">${this.input('Minimum hours', 'action.duration.min_hours', action.duration.min_hours, 'number')}${this.input('Median hours', 'action.duration.median_hours', action.duration.median_hours, 'number')}${this.input('Maximum hours', 'action.duration.max_hours', action.duration.max_hours, 'number')}${this.select('Shape', 'action.duration.shape', action.duration.shape, durationShapes)}</div>
        ${action.duration.shape === 'lognormal' ? this.input('Lognormal sigma', 'action.duration.shape_parameters.sigma', action.duration.shape_parameters.sigma ?? '', 'number') : ''}
        ${Object.entries(action.duration.shape_parameters)
          .filter(([key]) => key !== 'sigma')
          .map(([key, value]) =>
            this.input(
              `Shape parameter ${key}`,
              `action.duration.shape_parameters.${key}`,
              value,
              'number',
            ),
          )
          .join('')}
        ${this.evidenceMarkup('action.duration.evidence', action.duration.evidence)}
      </section>
      ${action.evidence ? `<section class="dsl-editor-group"><header><h4>Action probability evidence</h4></header>${this.evidenceMarkup('action.evidence', action.evidence)}</section>` : ''}
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">COEFFICIENTS</span><h4>Formula inputs and evidence</h4></div><button type="button" data-dsl-action="add-coefficient">Add coefficient</button></header>${action.coefficients.map((coefficient, index) => this.coefficientMarkup(coefficient, index)).join('') || '<p class="dsl-editor-empty">This formula has no coefficients.</p>'}</section>
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">REQUIREMENTS</span><h4>Place and time constraints</h4></div></header>${this.requirementsMarkup('action-place', action.place_requirements)}${this.requirementsMarkup('action-time', action.time_requirements)}</section>
    `;
  }

  private coefficientMarkup(coefficient: DslCoefficient, index: number): string {
    return `<article class="dsl-editor-subcard"><header><h4>${escapeHtml(coefficient.name)}</h4><button type="button" class="prompt2-danger" data-dsl-action="delete-coefficient" data-item-index="${index}">Remove</button></header><div class="dsl-form-grid">${this.input('Name', 'coefficient.name', coefficient.name, 'text', '', index)}${this.input('Value', 'coefficient.value', coefficient.value, 'number', '', index)}</div>${this.evidenceMarkup('coefficient.evidence', coefficient.evidence, index)}</article>`;
  }

  private stateMarkup(state: DslStateDefinition | undefined): string {
    if (!state) return '<p class="dsl-editor-empty">Add a state to begin.</p>';
    return `
      <div class="dsl-editor-title"><div><span class="prompt2-eyebrow">STATE</span><h3>${escapeHtml(state.name)}</h3><code>${escapeHtml(state.id)}</code></div></div>
      <div class="dsl-form-grid">${this.input('Name', 'state.name', state.name)}${this.input('Minimum', 'state.min', state.min, 'number')}${this.input('Maximum', 'state.max', state.max, 'number')}${this.input('Initial value', 'state.initial', state.initial, 'number')}${this.input('Decay per hour', 'state.decay_per_hour', state.decay_per_hour, 'number')}${this.input('Recovery per hour', 'state.recovery_per_hour', state.recovery_per_hour, 'number')}</div>
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">THRESHOLDS</span><h4>Named state boundaries</h4></div><button type="button" data-dsl-action="add-threshold">Add threshold</button></header><p>Use threshold(${escapeHtml(state.id)}, threshold_id) in a condition to apply a named boundary.</p>${state.thresholds.map((threshold, index) => `<article class="dsl-editor-inline-row"><code>${escapeHtml(threshold.id)}</code>${this.input('Label', 'threshold.label', threshold.label, 'text', '', index)}${this.input('Value', 'threshold.value', threshold.value, 'number', '', index)}<button type="button" class="prompt2-danger" data-dsl-action="delete-threshold" data-item-index="${index}">Remove</button></article>`).join('') || '<p class="dsl-editor-empty">No thresholds defined.</p>'}</section>
    `;
  }

  private treeMarkup(tree: DslDecisionTree | undefined): string {
    if (!tree) return '<p class="dsl-editor-empty">Add a decision tree to begin.</p>';
    const nodeOptions = tree.nodes.map((node) => node.id);
    return `
      <div class="dsl-editor-title"><div><span class="prompt2-eyebrow">DECISION TREE</span><h3>${escapeHtml(tree.name)}</h3><code>${escapeHtml(tree.id)}</code></div></div>
      <div class="dsl-form-grid">${this.input('Name', 'tree.name', tree.name)}${this.select('Entry node', 'tree.entry_node', tree.entry_node, nodeOptions)}</div>
      ${this.graphPreviewMarkup(tree)}
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">NODES</span><h4>States and actions in this graph</h4></div><button type="button" data-dsl-action="add-node">Add node</button></header><div class="dsl-editor-node-grid">${tree.nodes.map((node, index) => this.nodeMarkup(node, index)).join('')}</div></section>
      <section class="dsl-editor-group"><header><div><span class="prompt2-eyebrow">EDGES</span><h4>Transitions, formulas, and conditions</h4></div><button type="button" data-dsl-action="add-edge">Add edge</button></header>${tree.edges.map((edge, index) => this.edgeMarkup(edge, index, nodeOptions)).join('') || '<p class="dsl-editor-empty">No transitions defined.</p>'}</section>
    `;
  }

  private graphPreviewMarkup(tree: DslDecisionTree): string {
    return `<section class="dsl-graph-preview" aria-label="Decision tree preview"><header><span class="prompt2-eyebrow">LIVE GRAPH PREVIEW</span><span>${tree.nodes.length} nodes · ${tree.edges.length} edges</span></header><div class="dsl-graph-preview-nodes">${tree.nodes.map((node) => `<span class="kind-${node.kind}"><strong>${escapeHtml(node.label)}</strong><small>${escapeHtml(node.kind)}</small></span>`).join('')}</div><div class="dsl-graph-preview-edges">${tree.edges.map((edge) => `<span><code>${escapeHtml(edge.from_node)}</code><b>→</b><code>${escapeHtml(edge.to_node)}</code><small>${(edge.probability * 100).toFixed(1)}% · ${escapeHtml(edge.condition)}</small></span>`).join('') || '<p>No edges.</p>'}</div></section>`;
  }

  private nodeMarkup(node: DslTreeNode, index: number): string {
    const actionSelect =
      node.kind === 'action'
        ? this.select(
            'Action',
            'node.action_id',
            node.action_id ?? '',
            this.draft.actions.map((action) => action.id),
            '',
            index,
          )
        : '';
    const treeSelect =
      node.kind === 'module'
        ? this.select(
            'Target tree',
            'node.target_tree_id',
            node.target_tree_id ?? '',
            this.draft.trees.map((tree) => tree.id),
            '',
            index,
          )
        : '';
    return `<article class="dsl-editor-subcard"><header><code>${escapeHtml(node.id)}</code><button type="button" class="prompt2-danger" data-dsl-action="delete-node" data-item-index="${index}">Remove</button></header><div class="dsl-form-grid">${this.input('Label', 'node.label', node.label, 'text', '', index)}${this.select('Kind', 'node.kind', node.kind, nodeKinds, '', index)}${actionSelect}${treeSelect}</div></article>`;
  }

  private edgeMarkup(edge: DslTreeEdge, index: number, nodeOptions: string[]): string {
    return `<article class="dsl-editor-subcard dsl-editor-edge"><header><div><span class="prompt2-eyebrow">EDGE</span><code>${escapeHtml(edge.id)}</code></div><button type="button" class="prompt2-danger" data-dsl-action="delete-edge" data-item-index="${index}">Remove</button></header><div class="dsl-form-grid">${this.select('From node', 'edge.from_node', edge.from_node, nodeOptions, '', index)}${this.select('To node', 'edge.to_node', edge.to_node, nodeOptions, '', index)}${this.input('Probability', 'edge.probability', edge.probability, 'number', '', index)}${this.input('Formula', 'edge.formula', edge.formula, 'text', 'wide', index)}${this.input('Condition', 'edge.condition', edge.condition, 'text', 'wide', index)}</div>${this.requirementsMarkup('edge-place', edge.place_requirements, index)}${this.requirementsMarkup('edge-time', edge.time_requirements, index)}</article>`;
  }

  private evidenceMarkup(prefix: string, evidence: DslEvidence, index?: number): string {
    return `<div class="dsl-evidence"><div class="dsl-form-grid">${this.select('Status', `${prefix}.status`, evidence.status, evidenceStatuses, '', index)}${this.input('Source', `${prefix}.source`, evidence.source, 'text', 'wide', index)}${this.input('Source version', `${prefix}.sourceVersion`, evidence.sourceVersion, 'text', '', index)}${this.input('Source date', `${prefix}.sourceDate`, evidence.sourceDate ?? '', 'date', '', index)}${this.input('Uncertainty (0–1)', `${prefix}.uncertainty`, evidence.uncertainty, 'number', '', index)}${this.input('Reasoning', `${prefix}.reasoning`, evidence.reasoning ?? '', 'text', 'wide', index)}</div></div>`;
  }

  private requirementsMarkup(kind: string, values: string[], itemIndex?: number): string {
    const label = kind.endsWith('place') ? 'Place requirements' : 'Time requirements';
    return `<div class="dsl-requirements"><header><strong>${label}</strong><button type="button" data-dsl-action="add-requirement" data-requirement-kind="${kind}" ${itemIndex === undefined ? '' : `data-item-index="${itemIndex}"`}>Add</button></header>${values.map((value, requirementIndex) => `<div><input type="text" value="${escapeHtml(value)}" data-dsl-field="requirement" data-requirement-kind="${kind}" data-requirement-index="${requirementIndex}" ${itemIndex === undefined ? '' : `data-item-index="${itemIndex}"`} aria-label="${label} ${requirementIndex + 1}"><button type="button" data-dsl-action="delete-requirement" data-requirement-kind="${kind}" data-requirement-index="${requirementIndex}" ${itemIndex === undefined ? '' : `data-item-index="${itemIndex}"`}>Remove</button></div>`).join('') || `<p>No ${label.toLowerCase()}.</p>`}</div>`;
  }

  private input(
    label: string,
    field: string,
    value: string | number,
    type = 'text',
    className = '',
    index?: number,
  ): string {
    const step = type === 'number' ? 'step="any"' : '';
    return `<label class="${className}"><span>${escapeHtml(label)}</span><input type="${type}" value="${escapeHtml(String(value))}" data-dsl-field="${escapeHtml(field)}" ${index === undefined ? '' : `data-item-index="${index}"`} ${step}></label>`;
  }

  private select(
    label: string,
    field: string,
    value: string,
    options: readonly string[],
    className = '',
    index?: number,
  ): string {
    return `<label class="${className}"><span>${escapeHtml(label)}</span><select data-dsl-field="${escapeHtml(field)}" ${index === undefined ? '' : `data-item-index="${index}"`}>${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? 'selected' : ''}>${escapeHtml(sentenceCase(option))}</option>`).join('')}</select></label>`;
  }

  private issueMarkup(issues: DslValidationIssue[]): string {
    if (!issues.length)
      return '<p class="dsl-editor-valid">All references, ranges, probabilities, and graph constraints are valid.</p>';
    return `<details ${issues.some((issue) => issue.severity === 'error') ? 'open' : ''}><summary>Validation results</summary><ul>${issues.map((issue) => `<li class="severity-${issue.severity}"><strong>${escapeHtml(issue.path)}</strong>${escapeHtml(issue.message)}</li>`).join('')}</ul></details>`;
  }

  private diffMarkup(diff: DslDocumentDiff[]): string {
    if (!diff.length) return '<p class="dsl-editor-no-diff">No staged changes.</p>';
    return `<details><summary>Staged diff (${diff.length})</summary><div class="dsl-editor-diff">${diff.map((item) => `<div><code>${escapeHtml(item.path)}</code><span>${escapeHtml(item.before)} → ${escapeHtml(item.after)}</span></div>`).join('')}</div></details>`;
  }

  private confirmMarkup(diff: DslDocumentDiff[], errors: number): string {
    return `<section class="dsl-editor-confirm" role="alertdialog" aria-label="Confirm DSL changes"><div><strong>Confirm ${diff.length} DSL ${diff.length === 1 ? 'change' : 'changes'}</strong><p>New runs will use the updated DSL version and hash. Existing runs keep their recorded definition and results.</p></div>${errors ? `<p class="is-invalid">Resolve ${errors} validation errors before saving.</p>` : ''}<div><button type="button" data-dsl-action="cancel-review">Keep editing</button><button type="button" class="prompt2-primary" data-dsl-action="confirm" ${errors || this.saving ? 'disabled' : ''}>${this.saving ? 'Saving…' : 'Confirm DSL changes'}</button></div></section>`;
  }

  private applyField(input: HTMLInputElement | HTMLSelectElement): void {
    const field = input.dataset.dslField ?? '';
    const index = Number(input.dataset.itemIndex);
    const numeric = parseFiniteNumber(input.value);
    const action = this.selectedAction();
    const state = this.selectedState();
    const tree = this.selectedTree();
    if (field === 'tick_hours' && numeric !== null) this.draft.tick_hours = numeric;
    if (this.section === 'actions' && action) {
      this.applyActionField(action, field, input.value, numeric, index, input);
    }
    if (this.section === 'states' && state) {
      this.applyStateField(state, field, input.value, numeric, index);
    }
    if (this.section === 'trees' && tree) {
      this.applyTreeField(tree, field, input.value, numeric, index, input);
    }
  }

  private applyActionField(
    action: DslActionDefinition,
    field: string,
    value: string,
    numeric: number | null,
    index: number,
    input: HTMLInputElement | HTMLSelectElement,
  ): void {
    if (field === 'action.name') action.name = value;
    if (field === 'action.description') action.description = value;
    if (field === 'action.category') action.category = value;
    if (field === 'action.priority' && numeric !== null) action.priority = numeric;
    if (field === 'action.aggregate_statistic_id') action.aggregate_statistic_id = value;
    if (field === 'action.mode') action.mode = value as DslActionDefinition['mode'];
    if (field === 'action.interruptibility')
      action.interruptibility = value as DslActionDefinition['interruptibility'];
    if (field === 'action.interruption_outcome')
      action.interruption_outcome = value as DslActionDefinition['interruption_outcome'];
    if (field === 'action.emergency_interruptions')
      action.emergency_interruptions = value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
    if (field === 'action.formula') action.formula = value;
    if (field === 'action.duration.min_hours' && numeric !== null)
      action.duration.min_hours = numeric;
    if (field === 'action.duration.median_hours' && numeric !== null)
      action.duration.median_hours = numeric;
    if (field === 'action.duration.max_hours' && numeric !== null)
      action.duration.max_hours = numeric;
    if (field === 'action.duration.shape')
      action.duration.shape = value as DslDurationDistribution['shape'];
    if (field.startsWith('action.duration.shape_parameters.')) {
      const parameter = field.split('.').at(-1) ?? '';
      if (numeric !== null) action.duration.shape_parameters[parameter] = numeric;
      else delete action.duration.shape_parameters[parameter];
    }
    if (field.startsWith('action.duration.evidence.'))
      this.applyEvidence(action.duration.evidence, field.split('.').at(-1) ?? '', value, numeric);
    if (field.startsWith('action.evidence.') && action.evidence)
      this.applyEvidence(action.evidence, field.split('.').at(-1) ?? '', value, numeric);
    const coefficient = action.coefficients[index];
    if (coefficient && field === 'coefficient.name') coefficient.name = value;
    if (coefficient && field === 'coefficient.value' && numeric !== null)
      coefficient.value = numeric;
    if (coefficient && field.startsWith('coefficient.evidence.'))
      this.applyEvidence(coefficient.evidence, field.split('.').at(-1) ?? '', value, numeric);
    if (field === 'requirement')
      this.applyRequirement(action.place_requirements, action.time_requirements, input, value);
  }

  private applyStateField(
    state: DslStateDefinition,
    field: string,
    value: string,
    numeric: number | null,
    index: number,
  ): void {
    if (field === 'state.name') state.name = value;
    if (field === 'state.min' && numeric !== null) state.min = numeric;
    if (field === 'state.max' && numeric !== null) state.max = numeric;
    if (field === 'state.initial' && numeric !== null) state.initial = numeric;
    if (field === 'state.decay_per_hour' && numeric !== null) state.decay_per_hour = numeric;
    if (field === 'state.recovery_per_hour' && numeric !== null) state.recovery_per_hour = numeric;
    const threshold = state.thresholds[index];
    if (threshold && field === 'threshold.label') threshold.label = value;
    if (threshold && field === 'threshold.value' && numeric !== null) threshold.value = numeric;
  }

  private applyTreeField(
    tree: DslDecisionTree,
    field: string,
    value: string,
    numeric: number | null,
    index: number,
    input: HTMLInputElement | HTMLSelectElement,
  ): void {
    if (field === 'tree.name') tree.name = value;
    if (field === 'tree.entry_node') tree.entry_node = value;
    const node = tree.nodes[index];
    if (node && field === 'node.label') node.label = value;
    if (node && field === 'node.kind') node.kind = value as DslTreeNode['kind'];
    if (node && field === 'node.action_id') node.action_id = value;
    if (node && field === 'node.target_tree_id') node.target_tree_id = value;
    const edge = tree.edges[index];
    if (edge && field === 'edge.from_node') edge.from_node = value;
    if (edge && field === 'edge.to_node') edge.to_node = value;
    if (edge && field === 'edge.probability' && numeric !== null) edge.probability = numeric;
    if (edge && field === 'edge.formula') edge.formula = value;
    if (edge && field === 'edge.condition') edge.condition = value;
    if (edge && field === 'requirement')
      this.applyRequirement(edge.place_requirements, edge.time_requirements, input, value);
  }

  private applyEvidence(
    evidence: DslEvidence,
    field: string,
    value: string,
    numeric: number | null,
  ): void {
    if (field === 'status') evidence.status = value as DslEvidence['status'];
    if (field === 'source') evidence.source = value;
    if (field === 'sourceVersion') evidence.sourceVersion = value;
    if (field === 'sourceDate') evidence.sourceDate = value;
    if (field === 'uncertainty' && numeric !== null) evidence.uncertainty = numeric;
    if (field === 'reasoning') evidence.reasoning = value;
  }

  private applyRequirement(
    placeValues: string[],
    timeValues: string[],
    input: HTMLInputElement | HTMLSelectElement,
    value: string,
  ): void {
    const index = Number(input.dataset.requirementIndex);
    const values = input.dataset.requirementKind?.endsWith('place') ? placeValues : timeValues;
    if (values[index] !== undefined) values[index] = value;
  }

  private addAction(): void {
    const id = uniqueId(
      'action',
      this.draft.actions.map((action) => action.id),
    );
    this.draft.actions.push({
      id,
      name: 'New action',
      description: '',
      category: 'other',
      mode: 'primary',
      priority: 0,
      aggregate_statistic_id: id,
      interruptibility: 'interruptible',
      interruption_outcome: 'defer',
      emergency_interruptions: [],
      duration: {
        min_hours: 0.25,
        median_hours: 0.5,
        max_hours: 1,
        shape: 'triangular',
        shape_parameters: {},
        evidence: newEvidence(),
      },
      evidence: newEvidence(),
      formula: '1',
      coefficients: [],
      place_requirements: [],
      time_requirements: [],
    });
    this.section = 'actions';
    this.selectedActionId = id;
  }

  private addState(): void {
    const id = uniqueId(
      'state',
      this.draft.states.map((state) => state.id),
    );
    this.draft.states.push({
      id,
      name: 'New state',
      min: 0,
      max: 1,
      initial: 0.5,
      decay_per_hour: 0,
      recovery_per_hour: 0,
      thresholds: [],
    });
    this.section = 'states';
    this.selectedStateId = id;
  }

  private addTree(): void {
    const id = uniqueId(
      'tree',
      this.draft.trees.map((tree) => tree.id),
    );
    this.draft.trees.push({
      id,
      name: 'New decision tree',
      entry_node: 'entry',
      nodes: [
        { id: 'entry', label: 'Entry', kind: 'entry' },
        { id: 'complete', label: 'Complete', kind: 'terminal' },
      ],
      edges: [
        {
          id: 'entry-complete',
          from_node: 'entry',
          to_node: 'complete',
          probability: 1,
          formula: '1',
          condition: 'always',
          place_requirements: [],
          time_requirements: [],
        },
      ],
    });
    this.section = 'trees';
    this.selectedTreeId = id;
  }

  private addCoefficient(): void {
    const action = this.selectedAction();
    if (!action) return;
    const id = uniqueId(
      'coefficient',
      action.coefficients.map((coefficient) => coefficient.id),
    );
    action.coefficients.push({ id, name: 'New coefficient', value: 0, evidence: newEvidence() });
  }

  private deleteCoefficient(index: number): void {
    this.selectedAction()?.coefficients.splice(index, 1);
  }

  private addThreshold(): void {
    const state = this.selectedState();
    if (!state) return;
    const id = uniqueId(
      'threshold',
      state.thresholds.map((threshold) => threshold.id),
    );
    state.thresholds.push({ id, label: 'New threshold', value: state.initial });
  }

  private deleteThreshold(index: number): void {
    this.selectedState()?.thresholds.splice(index, 1);
  }

  private addNode(): void {
    const tree = this.selectedTree();
    if (!tree) return;
    const id = uniqueId(
      'node',
      tree.nodes.map((node) => node.id),
    );
    tree.nodes.push({ id, label: 'New terminal', kind: 'terminal' });
  }

  private deleteNode(index: number): void {
    const tree = this.selectedTree();
    const node = tree?.nodes[index];
    if (!tree || !node) return;
    tree.nodes.splice(index, 1);
    tree.edges = tree.edges.filter(
      (edge) => edge.from_node !== node.id && edge.to_node !== node.id,
    );
  }

  private addEdge(): void {
    const tree = this.selectedTree();
    if (!tree || tree.nodes.length < 2) return;
    const id = uniqueId(
      'edge',
      tree.edges.map((edge) => edge.id),
    );
    tree.edges.push({
      id,
      from_node: tree.nodes[0]!.id,
      to_node: tree.nodes.at(-1)!.id,
      probability: 1,
      formula: '1',
      condition: 'always',
      place_requirements: [],
      time_requirements: [],
    });
  }

  private deleteEdge(index: number): void {
    this.selectedTree()?.edges.splice(index, 1);
  }

  private addRequirement(kind: string, itemIndex: number): void {
    const values = this.requirementValues(kind, itemIndex);
    values?.push(kind.endsWith('place') ? 'any place' : 'any time');
  }

  private deleteRequirement(kind: string, itemIndex: number, requirementIndex: number): void {
    this.requirementValues(kind, itemIndex)?.splice(requirementIndex, 1);
  }

  private requirementValues(kind: string, itemIndex: number): string[] | undefined {
    if (kind.startsWith('action')) {
      const action = this.selectedAction();
      return kind.endsWith('place') ? action?.place_requirements : action?.time_requirements;
    }
    const edge = this.selectedTree()?.edges[itemIndex];
    return kind.endsWith('place') ? edge?.place_requirements : edge?.time_requirements;
  }
}
