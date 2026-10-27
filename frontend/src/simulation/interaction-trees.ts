import './interaction-trees.css';

export type InteractionEvidenceStatus = 'measured_joint' | 'fitted_model' | 'approved_estimate';

export interface InteractionTransitionEvidence {
  source: string;
  version: string;
  status: InteractionEvidenceStatus;
  uncertainty: number;
  source_date: string | null;
  evidence_id: string | null;
}

export interface InteractionTreeCondition {
  input: string;
  operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte';
  value: string | number | boolean;
}

export type InteractionTreeEffect =
  | {
      kind: 'agent_state';
      participant: 'actor' | 'target';
      field: string;
      operation: 'set' | 'add';
      value: number;
      minimum: number | null;
      maximum: number | null;
      scale_by?: string[];
    }
  | {
      kind: 'agent_routine';
      participant: 'actor' | 'target';
      operation: 'add' | 'remove';
      routine_id: string;
    }
  | {
      kind: 'relationship_state';
      field: string;
      operation: 'set' | 'add';
      value: number;
      minimum: number | null;
      maximum: number | null;
      scale_by?: string[];
    }
  | {
      kind: 'relationship_kind';
      relationship_type: string;
    };

export interface InteractionTreeNode {
  id: string;
  label: string;
  terminal: boolean;
  target_tree_id?: string | null;
}

export interface InteractionProbabilityFactorCase {
  id: string;
  conditions: InteractionTreeCondition[];
  multiplier: number;
}

export interface InteractionProbabilityFactor {
  id: string;
  label: string;
  cases: InteractionProbabilityFactorCase[];
  evidence: InteractionTransitionEvidence;
}

export interface InteractionTreeTransition {
  id: string;
  from_node: string;
  to_node: string;
  outcome: string;
  probability: number;
  probability_factors?: InteractionProbabilityFactor[];
  evidence: InteractionTransitionEvidence;
  conditions: InteractionTreeCondition[];
  effects: InteractionTreeEffect[];
}

export interface InteractionTreeDefinition {
  id: string;
  name: string;
  version: string;
  entry_node: string;
  allowed_channels: string[];
  co_location_policy: 'required' | 'remote_allowed';
  nodes: InteractionTreeNode[];
  transitions: InteractionTreeTransition[];
}

export interface InteractionParticipantSnapshot {
  agent_id: string;
  place_id: string;
  traits?: Record<string, string | number | boolean>;
  states: Record<string, number>;
  routines: string[];
}

export interface DirectedRelationshipSnapshot {
  source_agent_id: string;
  target_agent_id: string;
  eligible: boolean;
  relationship_type: string;
  states: Record<string, number>;
}

export interface InteractionPathStep {
  tree_id?: string | null;
  node_id: string;
  transition_id: string;
  outcome: string;
  probability: number;
  draw: number;
  evidence: InteractionTransitionEvidence;
  factors?: EvaluatedInteractionProbabilityFactor[];
  outgoing_probabilities?: EvaluatedInteractionTransition[];
}

export interface EvaluatedInteractionProbabilityFactor {
  factor_id: string;
  label: string;
  case_id: string;
  multiplier: number;
  inputs: Record<string, string | number | boolean>;
  evidence: InteractionTransitionEvidence;
}

export interface EvaluatedInteractionTransition {
  transition_id: string;
  outcome: string;
  base_probability: number;
  unnormalized_weight: number;
  probability: number;
  factors: EvaluatedInteractionProbabilityFactor[];
  evidence: InteractionTransitionEvidence;
}

export interface InteractionTreeChange {
  recipient: 'actor' | 'target' | 'relationship';
  field: string;
  before: string | number | boolean;
  after: string | number | boolean;
}

export interface InteractionTreeResult {
  tree_id: string;
  tree_version: string;
  seed: number;
  tick: number;
  outcome_node: string;
  outcome: string;
  path: InteractionPathStep[];
  receipt: {
    actor_id: string;
    target_id: string;
    relationship_direction: string;
    place_id: string;
    channel: string;
    weekday: number;
    hour: number;
  };
  actor_before: InteractionParticipantSnapshot;
  actor_after: InteractionParticipantSnapshot;
  target_before: InteractionParticipantSnapshot;
  target_after: InteractionParticipantSnapshot;
  relationship_before: DirectedRelationshipSnapshot;
  relationship_after: DirectedRelationshipSnapshot;
  changes: InteractionTreeChange[];
}

export interface InteractionTreeInspectorOptions {
  definition: InteractionTreeDefinition;
  registry?: InteractionTreeDefinition[];
  result?: InteractionTreeResult | null;
  selectedTransitionId?: string;
}

export interface InteractionTreeInspectorController {
  update(definition: InteractionTreeDefinition, result?: InteractionTreeResult | null): void;
  openTree(treeId: string): void;
  selectTransition(transitionId: string): void;
  destroy(): void;
}

const escapeHtml = (value: unknown): string =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const humanize = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const percent = (value: number): string => `${(value * 100).toFixed(1)}%`;

const displayValue = (value: string | number | boolean): string => {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return humanize(value);
};

function effectLabel(effect: InteractionTreeEffect): string {
  if (effect.kind === 'agent_state') {
    const operation =
      effect.operation === 'add' ? `${effect.value >= 0 ? '+' : ''}${effect.value}` : effect.value;
    const scale = effect.scale_by?.length
      ? ` × ${effect.scale_by.map((input) => humanize(input)).join(' × ')}`
      : '';
    return `${humanize(effect.participant)} · ${humanize(effect.field)} ${operation}${scale}`;
  }
  if (effect.kind === 'agent_routine') {
    return `${humanize(effect.participant)} · ${humanize(effect.operation)} ${humanize(effect.routine_id)}`;
  }
  if (effect.kind === 'relationship_state') {
    const operation =
      effect.operation === 'add' ? `${effect.value >= 0 ? '+' : ''}${effect.value}` : effect.value;
    const scale = effect.scale_by?.length
      ? ` × ${effect.scale_by.map((input) => humanize(input)).join(' × ')}`
      : '';
    return `Relationship · ${humanize(effect.field)} ${operation}${scale}`;
  }
  return `Relationship · becomes ${humanize(effect.relationship_type)}`;
}

function conditionLabel(condition: InteractionTreeCondition): string {
  const operators: Record<InteractionTreeCondition['operator'], string> = {
    eq: '=',
    ne: '≠',
    gt: '>',
    gte: '≥',
    lt: '<',
    lte: '≤',
  };
  return `${condition.input} ${operators[condition.operator]} ${displayValue(condition.value)}`;
}

function treeMarkup(
  definition: InteractionTreeDefinition,
  registry: Map<string, InteractionTreeDefinition>,
  unavailableReferences: Set<string>,
  result: InteractionTreeResult | null,
  selectedTransitionId: string | null,
): string {
  const selectedPath = new Set(
    result?.path
      .filter((step) => !step.tree_id || step.tree_id === definition.id)
      .map((step) => step.transition_id) ?? [],
  );
  const nodes = definition.nodes
    .map((node) => {
      const incoming = definition.transitions.filter(
        (transition) => transition.to_node === node.id,
      );
      const outgoing = definition.transitions.filter(
        (transition) => transition.from_node === node.id,
      );
      const target = node.target_tree_id ? registry.get(node.target_tree_id) : null;
      const reference = node.target_tree_id
        ? target
          ? `<button
              type="button"
              class="interaction-tree-reference"
              data-interaction-tree-reference="${escapeHtml(node.target_tree_id)}"
              aria-label="Open ${escapeHtml(target.name)} interaction tree"
            >
              <span>Opens:</span>
              <strong>${escapeHtml(target.name)}</strong>
            </button>`
          : unavailableReferences.has(node.target_tree_id)
            ? `<div class="interaction-tree-reference is-broken" data-broken-interaction-tree-reference="${escapeHtml(node.target_tree_id)}">
                <span>Broken reference</span>
                <strong>Opens: ${escapeHtml(node.target_tree_id)}</strong>
              </div>`
            : `<div class="interaction-tree-reference is-loading" data-loading-interaction-tree-reference="${escapeHtml(node.target_tree_id)}" role="status">
                <span>Loading reference</span>
                <strong>Opens: ${escapeHtml(node.target_tree_id)}</strong>
              </div>`
        : '';
      return `
        <section class="interaction-tree-node${node.terminal ? ' is-terminal' : ''}${node.target_tree_id ? ' is-reference' : ''}${result?.outcome_node === node.id ? ' is-outcome' : ''}" data-interaction-node="${escapeHtml(node.id)}">
          <div class="interaction-tree-node-heading">
            <span>${node.target_tree_id ? 'Reference' : node.id === definition.entry_node ? 'Entry' : node.terminal ? 'Terminal' : 'Decision'}</span>
            <strong>${escapeHtml(node.label)}</strong>
          </div>
          ${
            incoming.length
              ? `<div class="interaction-tree-incoming">${incoming.map((transition) => `<span>${escapeHtml(transition.outcome)}</span>`).join('')}</div>`
              : ''
          }
          ${reference}
          <div class="interaction-tree-edges">
            ${outgoing
              .map(
                (transition) => `
                  <button
                    type="button"
                    class="interaction-tree-edge${selectedPath.has(transition.id) ? ' is-path' : ''}${selectedTransitionId === transition.id ? ' is-selected' : ''}"
                    data-interaction-transition="${escapeHtml(transition.id)}"
                    aria-pressed="${selectedTransitionId === transition.id}"
                  >
                    <span>${escapeHtml(transition.outcome)}</span>
                    <strong>${percent(transition.probability)}</strong>
                    <small>to ${escapeHtml(definition.nodes.find((item) => item.id === transition.to_node)?.label ?? transition.to_node)}</small>
                  </button>
                `,
              )
              .join('')}
          </div>
        </section>
      `;
    })
    .join('');
  return `<div class="interaction-tree-map" data-interaction-tree-map>${nodes}</div>`;
}

function navigationMarkup(
  path: string[],
  registry: Map<string, InteractionTreeDefinition>,
): string {
  return `
    <nav class="interaction-tree-navigation" aria-label="Interaction tree navigation">
      <button type="button" data-interaction-tree-back${path.length === 1 ? ' disabled' : ''}>Back</button>
      <ol>
        ${path
          .map((treeId, index) => {
            const tree = registry.get(treeId);
            const current = index === path.length - 1;
            return `<li>
              <button
                type="button"
                data-interaction-tree-jump="${escapeHtml(treeId)}"
                data-interaction-tree-jump-index="${index}"
                ${current ? 'aria-current="page"' : ''}
              >${escapeHtml(tree?.name ?? treeId)}</button>
            </li>`;
          })
          .join('')}
      </ol>
    </nav>
  `;
}

function transitionMarkup(transition: InteractionTreeTransition | null): string {
  if (!transition) {
    return '<div class="interaction-tree-empty">Select a transition to inspect its evidence and effects.</div>';
  }
  const conditions = transition.conditions.length
    ? transition.conditions
        .map((condition) => `<li><code>${escapeHtml(conditionLabel(condition))}</code></li>`)
        .join('')
    : '<li>Always eligible after tree-level checks</li>';
  const effects = transition.effects.length
    ? transition.effects.map((effect) => `<li>${escapeHtml(effectLabel(effect))}</li>`).join('')
    : '<li>No state changes</li>';
  const factors = transition.probability_factors ?? [];
  const probabilityFormula = factors.length
    ? `${percent(transition.probability)} × ${factors.map((factor) => escapeHtml(factor.label)).join(' × ')}, normalized across eligible branches`
    : percent(transition.probability);
  const factorRows = factors.length
    ? factors
        .map(
          (factor) => `<li>
            <strong>${escapeHtml(factor.label)}</strong>
            <span>${factor.cases
              .map(
                (factorCase) =>
                  `${escapeHtml(factorCase.id)}: ${factorCase.conditions.map(conditionLabel).map(escapeHtml).join(' AND ')} → ×${factorCase.multiplier.toLocaleString('en', { maximumFractionDigits: 6 })}`,
              )
              .join(' · ')}</span>
            <small>${escapeHtml(factor.evidence.source)} · ${escapeHtml(factor.evidence.version)} · ${escapeHtml(humanize(factor.evidence.status))}</small>
          </li>`,
        )
        .join('')
    : '<li>Static sourced probability</li>';
  return `
    <article class="interaction-transition-detail" data-interaction-transition-detail>
      <header>
        <div>
          <span>Transition</span>
          <h3>${escapeHtml(transition.outcome)}</h3>
        </div>
        <strong>${escapeHtml(probabilityFormula)}</strong>
      </header>
      <dl>
        <div><dt>From</dt><dd>${escapeHtml(transition.from_node)}</dd></div>
        <div><dt>To</dt><dd>${escapeHtml(transition.to_node)}</dd></div>
        <div><dt>Evidence status</dt><dd>${escapeHtml(humanize(transition.evidence.status))}</dd></div>
        <div><dt>Uncertainty</dt><dd>${percent(transition.evidence.uncertainty)}</dd></div>
      </dl>
      <section>
        <h4>Eligibility conditions</h4>
        <ul>${conditions}</ul>
      </section>
      <section>
        <h4>Runtime probability factors</h4>
        <ul>${factorRows}</ul>
      </section>
      <section>
        <h4>Atomic effects</h4>
        <ul>${effects}</ul>
      </section>
      <section class="interaction-transition-source">
        <h4>Probability provenance</h4>
        <strong>${escapeHtml(transition.evidence.source)}</strong>
        <span>Version ${escapeHtml(transition.evidence.version)}${transition.evidence.source_date ? ` · ${escapeHtml(transition.evidence.source_date)}` : ''}</span>
        ${transition.evidence.evidence_id ? `<span>Evidence ${escapeHtml(transition.evidence.evidence_id)}</span>` : ''}
      </section>
    </article>
  `;
}

function participantChangesMarkup(
  title: string,
  recipient: InteractionTreeChange['recipient'],
  changes: InteractionTreeChange[],
): string {
  const selected = changes.filter((change) => change.recipient === recipient);
  return `
    <section class="interaction-result-party" data-interaction-result-party="${recipient}">
      <div><h4>${escapeHtml(title)}</h4><span>${selected.length} changes</span></div>
      <ul>
        ${
          selected.length
            ? selected
                .map(
                  (change) => `
                    <li>
                      <span>${escapeHtml(humanize(change.field))}</span>
                      <strong>${escapeHtml(displayValue(change.before))} → ${escapeHtml(displayValue(change.after))}</strong>
                    </li>
                  `,
                )
                .join('')
            : '<li class="is-empty">No changes</li>'
        }
      </ul>
    </section>
  `;
}

function resultMarkup(result: InteractionTreeResult | null): string {
  if (!result) {
    return `
      <section class="interaction-result-empty" data-interaction-result>
        <h3>No evaluated outcome</h3>
        <p>Run the tree with an eligible actor, target, place, time, and evidenced probabilities to inspect atomic changes.</p>
      </section>
    `;
  }
  const evidence = result.path
    .map((step) => step.evidence.source)
    .filter((value, index, all) => all.indexOf(value) === index);
  return `
    <section class="interaction-result" data-interaction-result>
      <header>
        <div>
          <span>Atomic result · tick ${result.tick}</span>
          <h3>${escapeHtml(humanize(result.outcome))}</h3>
        </div>
        <strong>${escapeHtml(result.actor_before.agent_id)} → ${escapeHtml(result.target_before.agent_id)}</strong>
      </header>
      <div class="interaction-result-context">
        <span>${escapeHtml(result.receipt.place_id)}</span>
        <span>${escapeHtml(humanize(result.receipt.channel))}</span>
        <span>Day ${result.receipt.weekday} · ${result.receipt.hour.toFixed(2)}</span>
        <span>Seed ${result.seed}</span>
      </div>
      <div class="interaction-result-parties">
        ${participantChangesMarkup(`Actor · ${result.actor_before.agent_id}`, 'actor', result.changes)}
        ${participantChangesMarkup(`Target · ${result.target_before.agent_id}`, 'target', result.changes)}
        ${participantChangesMarkup(`Relationship · ${result.receipt.relationship_direction}`, 'relationship', result.changes)}
      </div>
      <footer>
        <span>Both participant and relationship updates commit together.</span>
        <span>Path evidence: ${evidence.map(escapeHtml).join(', ')}</span>
      </footer>
    </section>
  `;
}

export function mountInteractionTreeInspector(
  container: HTMLElement,
  options: InteractionTreeInspectorOptions,
): InteractionTreeInspectorController {
  const registry = new Map(
    [...(options.registry ?? []), options.definition].map((definition) => [
      definition.id,
      definition,
    ]),
  );
  let navigationPath = [options.definition.id];
  let definition = options.definition;
  let result = options.result ?? null;
  let destroyed = false;
  const loadingReferences = new Set<string>();
  const unavailableReferences = new Set<string>();
  let selectedTransitionId: string | null =
    options.selectedTransitionId ??
    result?.path.at(-1)?.transition_id ??
    definition.transitions[0]?.id ??
    null;

  const loadReferences = (source: InteractionTreeDefinition): void => {
    const references = source.nodes
      .map((node) => node.target_tree_id)
      .filter((treeId): treeId is string => Boolean(treeId));
    references.forEach((treeId) => {
      if (
        registry.has(treeId) ||
        loadingReferences.has(treeId) ||
        unavailableReferences.has(treeId)
      ) {
        return;
      }
      loadingReferences.add(treeId);
      void fetch(`/api/simulation/interaction-trees/${encodeURIComponent(treeId)}`)
        .then(async (response) => {
          if (!response.ok) throw new Error(`Interaction tree ${treeId} is unavailable`);
          const loaded = (await response.json()) as InteractionTreeDefinition;
          if (loaded.id !== treeId || !Array.isArray(loaded.nodes)) {
            throw new Error(`Interaction tree ${treeId} returned an invalid definition`);
          }
          registry.set(treeId, loaded);
          unavailableReferences.delete(treeId);
          loadReferences(loaded);
        })
        .catch(() => unavailableReferences.add(treeId))
        .finally(() => {
          loadingReferences.delete(treeId);
          if (!destroyed) render();
        });
    });
  };

  const render = (): void => {
    const selected =
      definition.transitions.find((item) => item.id === selectedTransitionId) ?? null;
    container.innerHTML = `
      <section class="interaction-tree-inspector" data-interaction-tree-inspector>
        ${navigationMarkup(navigationPath, registry)}
        <header class="interaction-tree-header">
          <div>
            <span>Two-agent decision tree</span>
            <h2>${escapeHtml(definition.name)}</h2>
            <p>Directed eligibility · ${escapeHtml(humanize(definition.co_location_policy))}</p>
          </div>
          <dl>
            <div><dt>Version</dt><dd>${escapeHtml(definition.version)}</dd></div>
            <div><dt>Channels</dt><dd>${definition.allowed_channels.map((channel) => escapeHtml(humanize(channel))).join(', ')}</dd></div>
          </dl>
        </header>
        <div class="interaction-tree-layout">
          ${treeMarkup(definition, registry, unavailableReferences, result, selectedTransitionId)}
          <aside>${transitionMarkup(selected)}</aside>
        </div>
        ${resultMarkup(result)}
      </section>
    `;
    container
      .querySelectorAll<HTMLButtonElement>('[data-interaction-transition]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          selectedTransitionId = button.dataset.interactionTransition ?? null;
          render();
        });
      });
    container
      .querySelectorAll<HTMLButtonElement>('[data-interaction-tree-reference]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          const treeId = button.dataset.interactionTreeReference;
          if (!treeId) return;
          const target = registry.get(treeId);
          if (!target) return;
          navigationPath = [...navigationPath, treeId];
          definition = target;
          selectedTransitionId =
            result?.path.filter((step) => step.tree_id === treeId).at(-1)?.transition_id ??
            target.transitions[0]?.id ??
            null;
          render();
        });
      });
    container
      .querySelector<HTMLButtonElement>('[data-interaction-tree-back]')
      ?.addEventListener('click', () => {
        if (navigationPath.length === 1) return;
        navigationPath = navigationPath.slice(0, -1);
        definition = registry.get(navigationPath.at(-1)!)!;
        selectedTransitionId = definition.transitions[0]?.id ?? null;
        render();
      });
    container
      .querySelectorAll<HTMLButtonElement>('[data-interaction-tree-jump-index]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          const index = Number(button.dataset.interactionTreeJumpIndex);
          if (!Number.isInteger(index) || index < 0 || index >= navigationPath.length) return;
          navigationPath = navigationPath.slice(0, index + 1);
          definition = registry.get(navigationPath[index])!;
          selectedTransitionId = definition.transitions[0]?.id ?? null;
          render();
        });
      });
    loadReferences(definition);
  };

  render();
  return {
    update(nextDefinition, nextResult = null) {
      registry.set(nextDefinition.id, nextDefinition);
      unavailableReferences.delete(nextDefinition.id);
      definition = nextDefinition;
      navigationPath = [nextDefinition.id];
      result = nextResult;
      selectedTransitionId =
        result?.path.at(-1)?.transition_id ?? definition.transitions[0]?.id ?? null;
      render();
    },
    openTree(treeId) {
      const target = registry.get(treeId);
      if (!target) throw new Error(`Unknown interaction tree ${treeId}`);
      const existing = navigationPath.indexOf(treeId);
      navigationPath =
        existing >= 0 ? navigationPath.slice(0, existing + 1) : [...navigationPath, treeId];
      definition = target;
      selectedTransitionId = target.transitions[0]?.id ?? null;
      render();
    },
    selectTransition(transitionId) {
      if (!definition.transitions.some((transition) => transition.id === transitionId)) {
        throw new Error(`Unknown interaction transition ${transitionId}`);
      }
      selectedTransitionId = transitionId;
      render();
    },
    destroy() {
      destroyed = true;
      container.replaceChildren();
    },
  };
}
