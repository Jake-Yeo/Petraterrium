import './routines.css';

export type RoutineEvidenceStatus = 'measured' | 'user_defined' | 'illustrative' | 'unknown';

export interface RoutineSchedule {
  days: string[];
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  place_ids: string[];
  role_ids: string[];
}

export interface RoutineEvidence {
  status: RoutineEvidenceStatus;
  source_title: string | null;
  source_date: string | null;
  source_uri: string | null;
  note: string | null;
}

export interface RoutineStep {
  id: string;
  name: string;
  activity: string;
  schedule: RoutineSchedule;
  decision_tree_module_id: string | null;
}

export interface RoutineDefinition {
  id: string;
  name: string;
  agent_type_id: string;
  description: string | null;
  evidence: RoutineEvidence;
  steps: RoutineStep[];
}

export interface ResolvedRoutine {
  routine: RoutineDefinition;
  source_type_id: string;
  inherited: boolean;
  explicit_override: boolean;
  overridden_source_type_ids: string[];
}

export interface AgentRoutineDetail {
  agent_type_id: string;
  agent_type_name: string;
  routines: ResolvedRoutine[];
}

export interface RoutineDetailOptions {
  onBack?: () => void;
  onOpenDecisionTree?: (moduleId: string, step: RoutineStep, routine: ResolvedRoutine) => void;
}

const evidenceLabels: Record<RoutineEvidenceStatus, string> = {
  measured: 'Measured schedule',
  user_defined: 'User-defined schedule',
  illustrative: 'Illustrative · not measured',
  unknown: 'Evidence unknown',
};

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

function safeHttpUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : null;
  } catch {
    return null;
  }
}

function list(values: string[], className: string): string {
  return `<span class="${className}">${values
    .map((value) => `<i>${escapeHtml(value)}</i>`)
    .join('')}</span>`;
}

function scheduleTime(schedule: RoutineSchedule): string {
  return `${schedule.start_time}–${schedule.end_time}${schedule.ends_next_day ? ' next day' : ''}`;
}

function evidenceSource(evidence: RoutineEvidence): string {
  if (!evidence.source_title) {
    return '<span>No measured source attached</span>';
  }
  const sourceUrl = safeHttpUrl(evidence.source_uri);
  const title = sourceUrl
    ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(evidence.source_title)}</a>`
    : `<strong>${escapeHtml(evidence.source_title)}</strong>`;
  return `${title}${evidence.source_date ? `<span>${escapeHtml(evidence.source_date)}</span>` : ''}`;
}

export class RoutineDetailView {
  private detail: AgentRoutineDetail | null = null;

  private readonly onClick = (event: Event): void => {
    const target = event.target instanceof Element ? event.target : null;
    const back = target?.closest<HTMLButtonElement>('[data-routine-action="back"]');
    if (back) {
      this.options.onBack?.();
      return;
    }
    const trigger = target?.closest<HTMLButtonElement>('[data-decision-module-id]');
    if (!trigger || !this.detail) return;
    const moduleId = trigger.dataset.decisionModuleId;
    const routineId = trigger.dataset.routineId;
    const stepId = trigger.dataset.stepId;
    const routine = this.detail.routines.find((item) => item.routine.id === routineId);
    const step = routine?.routine.steps.find((item) => item.id === stepId);
    if (!moduleId || !routine || !step) return;
    this.options.onOpenDecisionTree?.(moduleId, step, routine);
    this.host.dispatchEvent(
      new CustomEvent('simulation:open-decision-tree', {
        bubbles: true,
        detail: {
          agentTypeId: this.detail.agent_type_id,
          moduleId,
          routineId,
          stepId,
        },
      }),
    );
  };

  constructor(
    private readonly host: HTMLElement,
    private readonly options: RoutineDetailOptions = {},
  ) {
    this.host.classList.add('routine-detail');
    this.host.addEventListener('click', this.onClick);
  }

  render(detail: AgentRoutineDetail): void {
    this.detail = detail;
    const back = this.options.onBack
      ? '<button type="button" class="routine-detail-back" data-routine-action="back">← Back</button>'
      : '';
    const routines = detail.routines.length
      ? detail.routines.map((routine) => this.renderRoutine(routine)).join('')
      : '<div class="routine-detail-empty"><strong>No routines assigned</strong><span>This agent type has no resolved schedule.</span></div>';
    this.host.innerHTML = `
      ${back}
      <header class="routine-detail-heading">
        <div><span class="small-label">TYPED SCHEDULE</span><h2>${escapeHtml(detail.agent_type_name)} routines</h2><p>Day, time, place, and role constraints determine when each step is available.</p></div>
        <span>${detail.routines.length} ${detail.routines.length === 1 ? 'routine' : 'routines'}</span>
      </header>
      <div class="routine-detail-list">${routines}</div>`;
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.classList.remove('routine-detail');
    this.host.replaceChildren();
    this.detail = null;
  }

  private renderRoutine(resolved: ResolvedRoutine): string {
    const routine = resolved.routine;
    const inheritance = resolved.inherited
      ? `<span class="routine-origin inherited">Inherited from ${escapeHtml(resolved.source_type_id)}</span>`
      : `<span class="routine-origin">Defined by ${escapeHtml(resolved.source_type_id)}</span>`;
    const override = resolved.explicit_override
      ? `<span class="routine-origin override">Overrides ${escapeHtml(resolved.overridden_source_type_ids.join(', ') || 'parent routine')}</span>`
      : '';
    const steps = routine.steps
      .map((step, index) => this.renderStep(resolved, step, index))
      .join('');
    return `
      <article class="routine-card" data-routine-id="${escapeHtml(routine.id)}">
        <header>
          <div><span class="small-label">${escapeHtml(routine.id)}</span><h3>${escapeHtml(routine.name)}</h3><p>${escapeHtml(routine.description ?? 'No description yet')}</p></div>
          <div class="routine-card-badges"><span class="routine-evidence ${escapeHtml(routine.evidence.status)}">${escapeHtml(evidenceLabels[routine.evidence.status])}</span>${inheritance}${override}</div>
        </header>
        <div class="routine-steps">${steps}</div>
        <footer>
          <div><span class="small-label">EVIDENCE</span>${evidenceSource(routine.evidence)}</div>
          ${routine.evidence.note ? `<p>${escapeHtml(routine.evidence.note)}</p>` : ''}
        </footer>
      </article>`;
  }

  private renderStep(resolved: ResolvedRoutine, step: RoutineStep, index: number): string {
    const schedule = step.schedule;
    const decision = step.decision_tree_module_id
      ? `<button type="button" class="routine-decision-call" data-decision-module-id="${escapeHtml(step.decision_tree_module_id)}" data-routine-id="${escapeHtml(resolved.routine.id)}" data-step-id="${escapeHtml(step.id)}" aria-label="Open ${escapeHtml(step.decision_tree_module_id)} decision tree"><span>Calls decision tree</span><strong>${escapeHtml(step.decision_tree_module_id)}</strong><b aria-hidden="true">↗</b></button>`
      : '<div class="routine-decision-empty"><span>Decision tree</span><strong>No module call</strong></div>';
    return `
      <section class="routine-step" aria-label="${escapeHtml(step.name)} schedule step">
        <div class="routine-step-index">${String(index + 1).padStart(2, '0')}</div>
        <div class="routine-step-body">
          <div class="routine-step-heading"><div><h4>${escapeHtml(step.name)}</h4><p>${escapeHtml(step.activity)}</p></div><strong>${escapeHtml(scheduleTime(schedule))}</strong></div>
          <div class="routine-constraint-grid">
            <div><span>Days</span>${list(schedule.days.map(titleCase), 'routine-days')}</div>
            <div><span>Places</span>${list(schedule.place_ids, 'routine-places')}</div>
            <div><span>Roles</span>${list(schedule.role_ids, 'routine-roles')}</div>
          </div>
          ${decision}
        </div>
      </section>`;
  }
}
