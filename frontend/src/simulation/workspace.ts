import type { DecisionEvidenceRegistryView, RunDetail } from '../contracts.generated';
import { DecisionGraphView } from '../decision-graph/main';
import { MarkovChainBuilder } from '../markov-builder/main';
import { AtlasPopulationGenerator } from './atlas-population';
import {
  mountAgentTypeGraph,
  type AgentTypeGraphController,
  type AgentTypeGraphNode,
} from './agent-type-graph';
import type { AgentStateSystem } from './agent-state-view';
import {
  mountAgentTypeProposalPanel,
  type AgentTypeProposalAudit,
  type AgentTypeProposalDraft,
  type AgentTypeProposalPanelController,
} from './agent-type-proposal';
import {
  prepareAgentDecisionContext,
  renderDecisionContextLimitations,
} from './agent-decision-context';
import {
  InitialAgentsView,
  type InitialAgentDetail,
  type InitialAgentRoutineLink,
} from './initial-agents';
import {
  createInitialPopulationHttpClient,
  InitialPopulationEditor,
  type InitialPopulationDraft,
} from './initial-population';
import {
  mountInteractionTreeInspector,
  type InteractionTreeDefinition,
  type InteractionTreeInspectorController,
} from './interaction-trees';
import { InteractionProgramEditor } from './interaction-program';
import { renderDecisionEvidence, type EvaluatedDecisionProbability } from './decision-evidence';
import { DefaultDslResetControl } from './default-dsl-reset';
import { CoefficientPromotionPanel } from './coefficient-promotion-panel';
import { SimulationRunPanel } from './run-panel';
import { RoutineDetailView, type AgentRoutineDetail } from './routines';
import {
  mountDecisionTreeNavigator,
  type DecisionTreeNavigatorController,
  type DecisionTreeEdgeSelection,
  type DecisionTreeRegistryDefinition,
  type TreeRegistryValidation,
} from './tree-navigator';
import './workspace.css';

export type SimulationSection = 'graph' | 'agents' | 'trees' | 'run';

interface AgentTypeRegistryResponse {
  configured: boolean;
  confirmed: { audit: AgentTypeProposalAudit } | null;
  resolved: { types: AgentTypeGraphNode[] };
}

interface DecisionTreeRegistryResponse {
  registry: DecisionTreeRegistryDefinition;
  validation: TreeRegistryValidation;
}

interface InteractionTreeSummary {
  id: string;
  name: string;
  version: string;
  node_count: number;
  transition_count: number;
  co_location_policy: 'required' | 'remote_allowed';
  allowed_channels: string[];
}

type DecisionTreeMode = 'browse' | 'build' | 'interactions' | 'program';

export interface SimulationWorkspaceOptions {
  onSectionChange: (section: SimulationSection) => void;
  onError: (error: unknown) => void;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

async function responseBody<T>(response: Response): Promise<T> {
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
        ? body.detail
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export class SimulationWorkspace {
  private section: SimulationSection = 'graph';
  private active = true;
  private run?: RunDetail;
  private agentTypes: AgentTypeGraphNode[] = [];
  private agentTypeAudit?: AgentTypeProposalAudit;
  private agentStateSystem?: AgentStateSystem;
  private agentTypeGraph?: AgentTypeGraphController;
  private proposalPanel?: AgentTypeProposalPanelController;
  private initialAgents?: InitialAgentsView;
  private atlasPopulationGenerator?: AtlasPopulationGenerator;
  private populationEditor?: InitialPopulationEditor;
  private routineDetail?: RoutineDetailView;
  private routineRequestVersion = 0;
  private treeNavigator?: DecisionTreeNavigatorController;
  private decisionAgent?: InitialAgentDetail;
  private interactionTreeInspector?: InteractionTreeInspectorController;
  private interactionProgramEditor?: InteractionProgramEditor;
  private interactionTreeRegistry: InteractionTreeDefinition[] = [];
  private interactionTreeRequestVersion = 0;
  private treesMode: DecisionTreeMode = 'browse';
  private readonly runPanel: SimulationRunPanel;
  private readonly coefficientPromotionPanel: CoefficientPromotionPanel;
  private readonly decisionGraph: DecisionGraphView;
  private readonly decisionTrees: MarkovChainBuilder;
  private readonly defaultDslReset: DefaultDslResetControl;

  constructor(private readonly options: SimulationWorkspaceOptions) {
    const graphHost = this.element('simulation-graph-view');
    graphHost.innerHTML = this.graphShell();
    this.decisionGraph = new DecisionGraphView(
      graphHost.querySelector<HTMLElement>('[data-recorded-action-graph]')!,
    );
    this.defaultDslReset = new DefaultDslResetControl(
      graphHost.querySelector<HTMLElement>('[data-default-dsl-reset]')!,
      { onRestored: () => this.refreshAfterDefaultReset() },
    );
    const treeHost = this.element('simulation-trees-view');
    treeHost.innerHTML = this.treeShell();
    this.decisionTrees = new MarkovChainBuilder(
      treeHost.querySelector<HTMLElement>('[data-decision-tree-builder]')!,
      { onConfirmed: () => this.loadDecisionTrees() },
    );
    this.runPanel = new SimulationRunPanel(this.element('rust-run-panel'));
    this.coefficientPromotionPanel = new CoefficientPromotionPanel(
      this.element('coefficient-promotion-panel'),
    );
    document.addEventListener('click', this.onClick);
    void this.loadAgentTypes();
    this.show('graph');
  }

  show(section: SimulationSection): void {
    this.section = section;
    document.querySelectorAll<HTMLButtonElement>('[data-simulation-section]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.simulationSection === section));
    });
    for (const value of ['graph', 'agents', 'trees', 'run'] as SimulationSection[]) {
      this.element(`simulation-${value === 'agents' ? 'agents' : value}-view`).hidden =
        value !== section;
    }
    this.decisionGraph.deactivate();
    this.runPanel.deactivate();
    if (this.active && section === 'graph') void this.activateGraph();
    if (this.active && section === 'agents') this.activateAgents();
    if (this.active && section === 'trees') void this.activateTrees();
    if (this.active && section === 'run') this.runPanel.activate();
    this.options.onSectionChange(section);
  }

  activate(): void {
    this.active = true;
    this.show(this.section);
  }

  currentSection(): SimulationSection {
    return this.section;
  }

  deactivate(): void {
    this.active = false;
    this.decisionGraph.deactivate();
    this.runPanel.deactivate();
  }

  setRun(run?: RunDetail): void {
    this.run = run;
    void this.decisionGraph.setRun(run).catch(this.options.onError);
  }

  selectAgent(agentId: string): void {
    this.decisionGraph.selectAgent(agentId);
    this.showRecordedActions();
    this.show('graph');
  }

  destroy(): void {
    document.removeEventListener('click', this.onClick);
    this.agentTypeGraph?.destroy();
    this.proposalPanel?.destroy();
    this.initialAgents?.dispose();
    this.atlasPopulationGenerator?.destroy();
    this.populationEditor?.destroy();
    this.routineRequestVersion += 1;
    this.routineDetail?.destroy();
    this.treeNavigator?.destroy();
    this.interactionTreeRequestVersion += 1;
    this.interactionTreeInspector?.destroy();
    this.interactionProgramEditor?.destroy();
    this.runPanel.dispose();
    this.coefficientPromotionPanel.dispose();
    this.defaultDslReset.dispose();
    this.decisionGraph.deactivate();
    this.decisionTrees.destroy();
  }

  private element<T extends HTMLElement = HTMLElement>(id: string): T {
    const value = document.getElementById(id);
    if (!value) throw new Error(`Missing simulation interface element ${id}`);
    return value as T;
  }

  private graphShell(): string {
    return `
      <div class="simulation-graph-header">
        <div><span class="small-label">GLOBAL TYPE SYSTEM</span><h1>Agents and decisions</h1><p>Inspect reusable agent types, inherited definitions, and recorded action paths.</p></div>
        <div><button class="button secondary" type="button" data-simulation-graph-mode="types" aria-pressed="true">Agent types</button><button class="button secondary" type="button" data-simulation-graph-mode="actions" aria-pressed="false">Recorded actions</button><button class="button primary" type="button" data-simulation-workspace-action="add-agent-type">Add agent type</button></div>
      </div>
      <div data-default-dsl-reset></div>
      <div data-agent-type-workspace>
        <div data-agent-type-status class="simulation-graph-status" role="status">Loading agent types…</div>
        <div data-agent-type-graph></div>
      </div>
      <div data-recorded-action-graph hidden></div>
      <div data-agent-type-proposal></div>`;
  }

  private async refreshAfterDefaultReset(): Promise<void> {
    this.decisionAgent = undefined;
    this.interactionTreeRegistry = [];
    await Promise.all([
      this.loadAgentTypes(),
      this.initialAgents?.refresh(),
      this.runPanel.refreshDefaults(),
    ]);
    if (this.section === 'trees') await this.activateTrees();
  }

  private treeShell(): string {
    return `
      <div class="simulation-agent-tools" role="tablist" aria-label="Decision tree sections">
        <button type="button" role="tab" aria-selected="true" data-simulation-trees-mode="browse">Browse trees</button>
        <button type="button" role="tab" aria-selected="false" data-simulation-trees-mode="build">Build a tree</button>
        <button type="button" role="tab" aria-selected="false" data-simulation-trees-mode="interactions">Interaction trees</button>
        <button type="button" role="tab" aria-selected="false" data-simulation-trees-mode="program">Interaction program</button>
      </div>
      <div data-decision-tree-browser><div class="simulation-tree-loading" role="status">Loading decision trees…</div></div>
      <div data-decision-tree-builder hidden></div>
      <div data-interaction-tree-browser hidden></div>
      <div data-interaction-program-editor hidden></div>`;
  }

  private async activateTrees(): Promise<void> {
    if (this.treesMode === 'interactions') await this.loadInteractionTrees();
    else if (this.treesMode === 'program') await this.loadInteractionProgram();
    else if (this.treesMode === 'build') await this.decisionTrees.activate();
    else await this.loadDecisionTrees();
  }

  private async loadDecisionTrees(selectedTreeId?: string): Promise<void> {
    const host = this.element('simulation-trees-view').querySelector<HTMLElement>(
      '[data-decision-tree-browser]',
    )!;
    try {
      const [treeResponse, evidenceResponse] = await Promise.all([
        fetch('/api/simulation/decision-trees'),
        fetch('/api/simulation/decision-evidence'),
      ]);
      const [value, evidence] = await Promise.all([
        responseBody<DecisionTreeRegistryResponse>(treeResponse),
        responseBody<DecisionEvidenceRegistryView>(evidenceResponse),
      ]);
      this.treeNavigator?.destroy();
      this.treeNavigator = mountDecisionTreeNavigator(host, {
        registry: value.registry,
        validation: value.validation,
        evidenceTemplates: evidence.registry?.templates ?? [],
        initialTreeId: selectedTreeId,
        initialAgentTypeId: this.decisionAgent?.agent_types[0],
        renderEdgeEvidence: (evidenceHost, selection) =>
          this.renderDecisionEdgeEvidence(evidenceHost, selection),
      });
    } catch (error) {
      host.innerHTML = `<div class="simulation-tree-loading error" role="alert">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
    }
  }

  private showTreesMode(mode: DecisionTreeMode): void {
    this.treesMode = mode;
    if (mode !== 'program') {
      this.interactionProgramEditor?.destroy();
      this.interactionProgramEditor = undefined;
    }
    if (mode !== 'interactions') {
      this.interactionTreeRequestVersion += 1;
      this.interactionTreeInspector?.destroy();
      this.interactionTreeInspector = undefined;
    }
    const host = this.element('simulation-trees-view');
    host.querySelector<HTMLElement>('[data-decision-tree-browser]')!.hidden = mode !== 'browse';
    host.querySelector<HTMLElement>('[data-decision-tree-builder]')!.hidden = mode !== 'build';
    host.querySelector<HTMLElement>('[data-interaction-tree-browser]')!.hidden =
      mode !== 'interactions';
    host.querySelector<HTMLElement>('[data-interaction-program-editor]')!.hidden =
      mode !== 'program';
    host.querySelectorAll<HTMLButtonElement>('[data-simulation-trees-mode]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.simulationTreesMode === mode));
    });
    if (mode === 'build') void this.decisionTrees.activate();
    else if (mode === 'browse') {
      void this.loadDecisionTrees();
    } else {
      if (mode === 'interactions') void this.loadInteractionTrees();
      else void this.loadInteractionProgram();
    }
  }

  private async loadInteractionProgram(): Promise<void> {
    const host = this.element('simulation-trees-view').querySelector<HTMLElement>(
      '[data-interaction-program-editor]',
    )!;
    this.interactionProgramEditor?.destroy();
    this.interactionProgramEditor = new InteractionProgramEditor(host);
    await this.interactionProgramEditor.mount();
  }

  private async loadInteractionTrees(selectedTreeId?: string): Promise<void> {
    const host = this.element('simulation-trees-view').querySelector<HTMLElement>(
      '[data-interaction-tree-browser]',
    )!;
    const version = ++this.interactionTreeRequestVersion;
    this.interactionTreeInspector?.destroy();
    this.interactionTreeInspector = undefined;
    this.interactionTreeRegistry = [];
    host.innerHTML =
      '<div class="simulation-tree-loading" role="status">Loading interaction trees…</div>';
    try {
      const response = await fetch('/api/simulation/interaction-trees');
      const summaries = await responseBody<InteractionTreeSummary[]>(response);
      if (version !== this.interactionTreeRequestVersion) return;
      if (!Array.isArray(summaries)) throw new Error('The interaction tree list is invalid.');
      if (!summaries.length) {
        host.innerHTML = `
          <div class="simulation-interaction-tree-empty">
            <span class="small-label">TWO-AGENT DECISIONS</span>
            <h2>No interaction trees yet</h2>
            <p>Registered interaction trees will appear here with their evidence, conditions, and atomic effects on both agents.</p>
          </div>`;
        return;
      }
      this.interactionTreeRegistry = await Promise.all(
        summaries.map(async (summary) => {
          const response = await fetch(
            `/api/simulation/interaction-trees/${encodeURIComponent(summary.id)}`,
          );
          return responseBody<InteractionTreeDefinition>(response);
        }),
      );
      if (version !== this.interactionTreeRequestVersion) return;
      const selected = summaries.find((summary) => summary.id === selectedTreeId) ?? summaries[0];
      host.innerHTML = `
        <div class="simulation-interaction-tree-heading">
          <div><span class="small-label">TWO-AGENT DECISIONS</span><h2>Interaction trees</h2><p>Inspect registered eligibility, evidenced probabilities, and atomic changes to each participant and their relationship.</p></div>
          <strong>${summaries.length.toLocaleString('en')} registered</strong>
        </div>
        <div class="simulation-interaction-tree-browser">
          <nav aria-label="Registered interaction trees">
            ${summaries
              .map(
                (summary) => `
                  <button type="button" data-interaction-tree-id="${escapeHtml(summary.id)}" aria-pressed="${summary.id === selected.id}">
                    <span><strong>${escapeHtml(summary.name)}</strong><small>Version ${escapeHtml(summary.version)}</small></span>
                    <span>${summary.node_count.toLocaleString('en')} nodes · ${summary.transition_count.toLocaleString('en')} transitions</span>
                  </button>`,
              )
              .join('')}
          </nav>
          <div data-interaction-tree-inspector-host><div class="simulation-tree-loading" role="status">Loading ${escapeHtml(selected.name)}…</div></div>
        </div>`;
      await this.loadInteractionTreeDefinition(selected.id);
    } catch (error) {
      if (version !== this.interactionTreeRequestVersion) return;
      host.innerHTML = `<div class="simulation-tree-loading error" role="alert"><span>${escapeHtml(error instanceof Error ? error.message : String(error))}</span><button type="button" class="button secondary" data-simulation-workspace-action="retry-interaction-trees">Retry</button></div>`;
    }
  }

  private async loadInteractionTreeDefinition(treeId: string): Promise<void> {
    const host = this.element('simulation-trees-view').querySelector<HTMLElement>(
      '[data-interaction-tree-browser]',
    )!;
    const inspectorHost = host.querySelector<HTMLElement>('[data-interaction-tree-inspector-host]');
    if (!inspectorHost) return;
    const version = ++this.interactionTreeRequestVersion;
    this.interactionTreeInspector?.destroy();
    this.interactionTreeInspector = undefined;
    inspectorHost.innerHTML =
      '<div class="simulation-tree-loading" role="status">Loading interaction tree…</div>';
    host.querySelectorAll<HTMLButtonElement>('[data-interaction-tree-id]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.interactionTreeId === treeId));
    });
    try {
      let definition = this.interactionTreeRegistry.find((tree) => tree.id === treeId);
      if (!definition) {
        const response = await fetch(
          `/api/simulation/interaction-trees/${encodeURIComponent(treeId)}`,
        );
        definition = await responseBody<InteractionTreeDefinition>(response);
        this.interactionTreeRegistry.push(definition);
      }
      if (version !== this.interactionTreeRequestVersion) return;
      this.interactionTreeInspector = mountInteractionTreeInspector(inspectorHost, {
        definition,
        registry: this.interactionTreeRegistry,
      });
    } catch (error) {
      if (version !== this.interactionTreeRequestVersion) return;
      inspectorHost.innerHTML = `<div class="simulation-tree-loading error" role="alert">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
    }
  }

  private async openDecisionTree(treeId: string, agent?: InitialAgentDetail): Promise<void> {
    if (agent) this.decisionAgent = agent;
    this.show('trees');
    this.showTreesMode('browse');
    await this.loadDecisionTrees(treeId);
  }

  private async renderDecisionEdgeEvidence(
    host: HTMLElement,
    selection: DecisionTreeEdgeSelection,
  ): Promise<void> {
    const agent = this.decisionAgent;
    if (!agent) {
      host.innerHTML =
        '<div class="simulation-decision-agent-empty"><strong>Select an initial agent</strong><p>Open an agent’s decision tree to evaluate this transition against that person’s traits and place.</p><button type="button" class="button secondary" data-simulation-workspace-action="select-decision-agent">Open Initial Agents</button></div>';
      return;
    }
    const decisionId = selection.edge.decision_id;
    const edgeId = selection.edge.evidence_edge_id;
    if (!decisionId || !edgeId) return;
    const prepared = prepareAgentDecisionContext(agent, selection.evidence);
    const response = await fetch(
      `/api/simulation/decision-evidence/${encodeURIComponent(decisionId)}/edges/${encodeURIComponent(edgeId)}/evaluate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prepared.request),
      },
    );
    const evaluation = await responseBody<EvaluatedDecisionProbability>(response);
    if (!host.isConnected) return;
    host.innerHTML = `<div class="simulation-decision-agent-context"><span>Evaluated for</span><strong>${escapeHtml(agent.agent_id)}</strong><small>${escapeHtml(agent.city)} · ${escapeHtml(agent.country)}</small></div><div data-decision-context-limitations></div><div data-decision-evidence-receipt></div>`;
    renderDecisionContextLimitations(
      host.querySelector<HTMLElement>('[data-decision-context-limitations]')!,
      prepared.limitations,
    );
    renderDecisionEvidence(
      host.querySelector<HTMLElement>('[data-decision-evidence-receipt]')!,
      evaluation,
    );
  }

  private async loadAgentTypes(): Promise<void> {
    const status = this.element('simulation-graph-view').querySelector<HTMLElement>(
      '[data-agent-type-status]',
    )!;
    status.hidden = false;
    status.textContent = 'Loading agent types…';
    try {
      const [registryResponse, stateResponse] = await Promise.all([
        fetch('/api/simulation/agent-types'),
        fetch('/api/simulation/agent-state-system'),
      ]);
      const [registry, stateSystem] = await Promise.all([
        responseBody<AgentTypeRegistryResponse>(registryResponse),
        responseBody<AgentStateSystem>(stateResponse),
      ]);
      this.agentTypes = registry.resolved.types;
      this.agentTypeAudit = registry.confirmed?.audit;
      this.agentStateSystem = stateSystem;
      status.textContent = registry.configured
        ? `${this.agentTypes.length} global agent types configured`
        : 'No global agent types yet. Add one manually or request an AI proposal.';
      this.renderAgentTypeGraph();
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : String(error);
      status.classList.add('error');
    }
  }

  private renderAgentTypeGraph(): void {
    const host =
      this.element('simulation-graph-view').querySelector<HTMLElement>('[data-agent-type-graph]')!;
    this.agentTypeGraph?.destroy();
    this.agentTypeGraph = mountAgentTypeGraph(host, {
      types: this.agentTypes,
      audit: this.agentTypeAudit,
      stateSystem: this.agentStateSystem,
      renderDecisionTree: (target, agentType) =>
        this.renderAgentTypeDecisionTree(target, agentType),
    });
  }

  private renderAgentTypeDecisionTree(
    target: HTMLElement,
    agentType: AgentTypeGraphNode,
  ): () => void {
    let disposed = false;
    let navigator: DecisionTreeNavigatorController | undefined;
    target.innerHTML =
      '<div class="simulation-tree-loading" role="status">Loading decision trees…</div>';
    void Promise.all([
      fetch('/api/simulation/decision-trees'),
      fetch('/api/simulation/decision-evidence'),
    ])
      .then(async ([treeResponse, evidenceResponse]) =>
        Promise.all([
          responseBody<DecisionTreeRegistryResponse>(treeResponse),
          responseBody<DecisionEvidenceRegistryView>(evidenceResponse),
        ]),
      )
      .then(([value, evidence]) => {
        if (disposed) return;
        navigator = mountDecisionTreeNavigator(target, {
          registry: value.registry,
          validation: value.validation,
          evidenceTemplates: evidence.registry?.templates ?? [],
          initialAgentTypeId: agentType.id,
          renderEdgeEvidence: (evidenceHost, selection) =>
            this.renderDecisionEdgeEvidence(evidenceHost, selection),
        });
      })
      .catch((error: unknown) => {
        if (disposed) return;
        target.innerHTML = `<div class="simulation-tree-loading error" role="alert">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
      });
    return () => {
      disposed = true;
      navigator?.destroy();
    };
  }

  private async activateGraph(): Promise<void> {
    const actions = this.element('simulation-graph-view').querySelector<HTMLElement>(
      '[data-recorded-action-graph]',
    )!;
    if (!actions.hidden) await this.decisionGraph.activate(this.run);
  }

  private activateAgents(): void {
    if (this.initialAgents) return;
    const host = this.element('simulation-agents-view');
    host.innerHTML = `
      <div class="simulation-agent-tools" role="tablist" aria-label="Initial agent sections">
        <button type="button" role="tab" aria-selected="true" data-simulation-agents-mode="browse">Browse agents</button>
        <button type="button" role="tab" aria-selected="false" data-simulation-agents-mode="setup">Population setup</button>
      </div>
      <div data-initial-agents-list></div>
      <div data-routine-detail hidden></div>
      <div data-initial-population-setup hidden>
        <div data-atlas-population-generator></div>
        <details class="simulation-manual-population">
          <summary>Advanced manual household editor</summary>
          <div data-initial-population-editor></div>
        </details>
      </div>`;
    this.initialAgents = new InitialAgentsView(
      host.querySelector<HTMLElement>('[data-initial-agents-list]')!,
      undefined,
      {
        onOpenRoutine: (routine, agent) => void this.openRoutine(routine, agent),
        onOpenDecisionTree: (tree, agent) => void this.openDecisionTree(tree.tree_id, agent),
        stateCatalog: () => this.agentStateSystem?.agent_states,
      },
    );
  }

  private async openRoutine(
    routine: InitialAgentRoutineLink,
    agent: InitialAgentDetail,
  ): Promise<void> {
    const host = this.element('simulation-agents-view');
    const detailHost = host.querySelector<HTMLElement>('[data-routine-detail]')!;
    const version = ++this.routineRequestVersion;
    this.decisionAgent = agent;
    this.routineDetail?.destroy();
    this.routineDetail = undefined;
    host.querySelector<HTMLElement>('[data-initial-agents-list]')!.hidden = true;
    host.querySelector<HTMLElement>('[data-initial-population-setup]')!.hidden = true;
    detailHost.hidden = false;
    detailHost.innerHTML =
      '<div class="simulation-tree-loading" role="status">Loading routine…</div>';
    host.querySelectorAll<HTMLButtonElement>('[data-simulation-agents-mode]').forEach((button) => {
      button.setAttribute('aria-selected', 'false');
    });
    try {
      const response = await fetch(
        `/api/simulation/routines/agent-types/${encodeURIComponent(routine.agent_type)}`,
      );
      const detail = await responseBody<AgentRoutineDetail>(response);
      if (version !== this.routineRequestVersion) return;
      this.routineDetail = new RoutineDetailView(detailHost, {
        onBack: () => this.showAgentsMode('browse'),
        onOpenDecisionTree: (moduleId) =>
          void this.openDecisionModule(moduleId, agent).catch(this.options.onError),
      });
      this.routineDetail.render(detail);
    } catch (error) {
      if (version !== this.routineRequestVersion) return;
      detailHost.innerHTML = `<div class="simulation-tree-loading error" role="alert"><span>${escapeHtml(error instanceof Error ? error.message : String(error))}</span><button type="button" class="button secondary" data-simulation-workspace-action="back-routine">Back to agent</button></div>`;
    }
  }

  private async openDecisionModule(moduleId: string, agent: InitialAgentDetail): Promise<void> {
    const response = await fetch('/api/simulation/decision-trees');
    const value = await responseBody<DecisionTreeRegistryResponse>(response);
    const modules = new Map(value.registry.modules.map((module) => [module.id, module]));
    const reachesModule = (rootModuleId: string): boolean => {
      const pending = [rootModuleId];
      const visited = new Set<string>();
      while (pending.length) {
        const current = pending.pop()!;
        if (current === moduleId) return true;
        if (visited.has(current)) continue;
        visited.add(current);
        const module = modules.get(current);
        for (const node of module?.nodes ?? []) {
          if (node.target_module_id) pending.push(node.target_module_id);
        }
      }
      return false;
    };
    const tree =
      value.registry.trees.find(
        (candidate) =>
          candidate.agent_type_ids.some((agentTypeId) => agent.agent_types.includes(agentTypeId)) &&
          reachesModule(candidate.root_module_id),
      ) ?? value.registry.trees.find((candidate) => reachesModule(candidate.root_module_id));
    if (!tree) throw new Error(`No decision tree uses routine module ${moduleId}.`);
    await this.openDecisionTree(tree.id, agent);
  }

  private showRecordedActions(): void {
    const graph = this.element('simulation-graph-view');
    graph.querySelector<HTMLElement>('[data-agent-type-workspace]')!.hidden = true;
    graph.querySelector<HTMLElement>('[data-recorded-action-graph]')!.hidden = false;
    graph.querySelectorAll<HTMLButtonElement>('[data-simulation-graph-mode]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.simulationGraphMode === 'actions'));
    });
  }

  private showAgentTypes(): void {
    const graph = this.element('simulation-graph-view');
    graph.querySelector<HTMLElement>('[data-agent-type-workspace]')!.hidden = false;
    graph.querySelector<HTMLElement>('[data-recorded-action-graph]')!.hidden = true;
    this.decisionGraph.deactivate();
    graph.querySelectorAll<HTMLButtonElement>('[data-simulation-graph-mode]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.simulationGraphMode === 'types'));
    });
  }

  private openProposal(): void {
    this.proposalPanel?.destroy();
    const host = this.element('simulation-graph-view').querySelector<HTMLElement>(
      '[data-agent-type-proposal]',
    )!;
    this.proposalPanel = mountAgentTypeProposalPanel(host, {
      requestProposal: async (prompt) => {
        const response = await fetch('/api/simulation/agent-types/proposals', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt }),
        });
        return responseBody<AgentTypeProposalDraft>(response);
      },
      confirmProposal: async (draft) => {
        const response = await fetch('/api/simulation/agent-types/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ draft, user_confirmed: true }),
        });
        await responseBody(response);
        this.proposalPanel?.destroy();
        this.proposalPanel = undefined;
        await this.loadAgentTypes();
      },
      onCancel: () => {
        this.proposalPanel?.destroy();
        this.proposalPanel = undefined;
      },
    });
  }

  private onClick = (event: MouseEvent): void => {
    const section = (event.target as HTMLElement).closest<HTMLElement>('[data-simulation-section]')
      ?.dataset.simulationSection as SimulationSection | undefined;
    if (section) {
      this.show(section);
      return;
    }
    const mode = (event.target as HTMLElement).closest<HTMLElement>('[data-simulation-graph-mode]')
      ?.dataset.simulationGraphMode;
    if (mode === 'actions') {
      this.showRecordedActions();
      void this.decisionGraph.activate(this.run).catch(this.options.onError);
      return;
    }
    if (mode === 'types') {
      this.showAgentTypes();
      return;
    }
    const action = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-simulation-workspace-action]',
    )?.dataset.simulationWorkspaceAction;
    if (action === 'add-agent-type') this.openProposal();
    if (action === 'retry-interaction-trees') void this.loadInteractionTrees();
    if (action === 'back-routine') this.showAgentsMode('browse');
    if (action === 'select-decision-agent') this.show('agents');
    if (action === 'open-decision-trees') {
      this.show('trees');
      this.showTreesMode('browse');
    }
    const agentsMode = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-simulation-agents-mode]',
    )?.dataset.simulationAgentsMode;
    if (agentsMode) this.showAgentsMode(agentsMode === 'setup' ? 'setup' : 'browse');
    const treesMode = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-simulation-trees-mode]',
    )?.dataset.simulationTreesMode;
    if (
      treesMode === 'browse' ||
      treesMode === 'build' ||
      treesMode === 'interactions' ||
      treesMode === 'program'
    ) {
      this.showTreesMode(treesMode);
    }
    const interactionTreeId = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-interaction-tree-id]',
    )?.dataset.interactionTreeId;
    if (interactionTreeId) void this.loadInteractionTreeDefinition(interactionTreeId);
  };

  private showAgentsMode(mode: 'browse' | 'setup'): void {
    const host = this.element('simulation-agents-view');
    this.routineRequestVersion += 1;
    host.querySelector<HTMLElement>('[data-initial-agents-list]')!.hidden = mode !== 'browse';
    host.querySelector<HTMLElement>('[data-initial-population-setup]')!.hidden = mode !== 'setup';
    host.querySelector<HTMLElement>('[data-routine-detail]')!.hidden = true;
    host.querySelectorAll<HTMLButtonElement>('[data-simulation-agents-mode]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.simulationAgentsMode === mode));
    });
    if (mode === 'setup' && !this.atlasPopulationGenerator) {
      this.atlasPopulationGenerator = new AtlasPopulationGenerator(
        host.querySelector<HTMLElement>('[data-atlas-population-generator]')!,
        {
          agentTypes: () =>
            this.agentTypes.map((agentType) => ({
              id: agentType.id,
              name: agentType.name,
            })),
          onGenerated: () => {
            void this.initialAgents?.refresh();
          },
        },
      );
      this.atlasPopulationGenerator.mount();
    }
    if (mode === 'setup' && !this.populationEditor) {
      this.populationEditor = new InitialPopulationEditor(
        host.querySelector<HTMLElement>('[data-initial-population-editor]')!,
        {
          draft: this.emptyPopulationDraft(),
          client: createInitialPopulationHttpClient(),
          onSaved: () => {
            void this.initialAgents?.refresh();
            this.showAgentsMode('browse');
          },
        },
      );
      this.populationEditor.mount();
    }
  }

  private emptyPopulationDraft(): InitialPopulationDraft {
    return {
      population_id: 'initial-population',
      version: 'draft-1',
      seed: 42,
      target_agents: 1,
      evidence: [
        {
          evidence_id: 'user-household-draft',
          source: 'User-defined household draft',
          source_version: 'draft-1',
          observed_at: new Date().toISOString().slice(0, 10),
          licence: 'User supplied',
          place: 'Unknown',
          status: 'unknown',
          fields: ['age', 'sex', 'household_composition'],
          uncertainty: 'No imported joint evidence attached',
          url: null,
        },
      ],
      household_templates: [
        {
          template_id: 'household-1',
          place: 'Unknown',
          country: 'Unknown',
          region: null,
          city: 'Unknown',
          neighbourhood: null,
          latitude: 0,
          longitude: 0,
          weight: 1,
          evidence_id: 'user-household-draft',
          members: [
            {
              member_id: 'person-1',
              age: 0,
              sex: 'unknown',
              relationship_to_reference: 'self',
              agent_types: ['person'],
              traits: {},
              states: {},
              field_evidence: {},
            },
          ],
        },
      ],
    };
  }
}
