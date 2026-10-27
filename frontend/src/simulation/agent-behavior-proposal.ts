import type { AgentTypeProposalBase } from './agent-type-proposal';

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const identifierPattern = /^[a-z][a-z0-9_-]*$/;

export type RoutineEvidenceStatus = 'measured' | 'user_defined' | 'illustrative' | 'unknown';
export type RoutineDay =
  'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday';

export interface RoutineScheduleDraft {
  days: RoutineDay[];
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  place_ids: string[];
  role_ids: string[];
}

export interface RoutineEvidenceDraft {
  status: RoutineEvidenceStatus;
  source_title: string | null;
  source_date: string | null;
  source_uri: string | null;
  note: string | null;
}

export interface RoutineStepProposalDraft {
  id: string;
  name: string;
  activity: string;
  decision_tree_module_id: string | null;
  schedule: RoutineScheduleDraft | null;
}

export interface RoutineProposalDraft {
  id: string;
  name: string;
  agent_type_id: string;
  description: string | null;
  source_feature_ids: string[];
  evidence: RoutineEvidenceDraft;
  steps: RoutineStepProposalDraft[];
}

export type DecisionTreeStatus = 'draft' | 'ready' | 'blocked' | 'deprecated';
export type DecisionTreeNodeKind = 'decision' | 'action' | 'terminal' | 'module_reference';

export interface DecisionTreeNodeDraft {
  id: string;
  label: string;
  kind: DecisionTreeNodeKind;
  description: string;
  target_module_id: string | null;
}

export interface DecisionTreeEdgeDraft {
  id: string;
  from_node: string;
  to_node: string;
  label: string;
  condition: string;
  decision_id: string | null;
  evidence_edge_id: string | null;
}

export interface DecisionTreeModuleDraft {
  id: string;
  version: string;
  name: string;
  description: string;
  entry_node: string;
  nodes: DecisionTreeNodeDraft[];
  edges: DecisionTreeEdgeDraft[];
  source: string;
  status: DecisionTreeStatus;
}

export interface DecisionTreeDefinitionDraft {
  id: string;
  version: string;
  name: string;
  description: string;
  root_module_id: string;
  agent_type_ids: string[];
  place_ids: string[];
  source: string;
  status: DecisionTreeStatus;
}

export interface DecisionTreeRegistryDraft {
  version: string;
  trees: DecisionTreeDefinitionDraft[];
  modules: DecisionTreeModuleDraft[];
}

export type DecisionPlaceScope = 'global' | 'region' | 'country' | 'city';

export interface DecisionEdgeInputPlanDraft {
  tree_id: string;
  module_id: string;
  edge_id: string;
  source_feature_ids: string[];
  outcome: string;
  population_scope: string;
  place_scope: DecisionPlaceScope;
  time_scope: string;
  decision_id: string | null;
  evidence_edge_id: string | null;
}

export interface BehaviorEvidenceRequirementDraft {
  id: string;
  kind: 'routine_schedule' | 'decision_probability';
  status: 'matched' | 'missing';
  target_id: string;
  source_feature_ids: string[];
  outcome: string;
  population_scope: string;
  place_scope: DecisionPlaceScope;
  time_scope: string;
  accepted_bases: Array<'measured' | 'user_defined' | 'measured_joint' | 'fitted_model'>;
  required_fields: string[];
  matched_evidence_ids: string[];
  message: string;
}

export interface AgentBehaviorProposalDraft extends AgentTypeProposalBase {
  schema_version: '2';
  routine_drafts: RoutineProposalDraft[];
  decision_tree_drafts: DecisionTreeRegistryDraft;
  decision_inputs: DecisionEdgeInputPlanDraft[];
  evidence_requirements: BehaviorEvidenceRequirementDraft[];
}

const timePattern = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/;
const routineDays: RoutineDay[] = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
];
const treeStatuses = new Set<DecisionTreeStatus>(['draft', 'ready', 'blocked', 'deprecated']);
const placeScopes = new Set<DecisionPlaceScope>(['global', 'region', 'country', 'city']);

export const isBehaviorProposal = (draft: {
  schema_version: '1' | '2';
}): draft is AgentBehaviorProposalDraft => draft.schema_version === '2';

const nonEmptyStrings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string' && item.trim().length > 0);

const minuteOfDay = (value: string): number => {
  const [hours, minutes] = value.split(':').map(Number);
  return hours * 60 + minutes;
};

const scheduleIssues = (schedule: RoutineScheduleDraft | null, label: string): string[] => {
  if (!schedule) return [`${label} needs a schedule.`];
  const issues: string[] = [];
  if (!schedule.days.length) issues.push(`${label} needs at least one day.`);
  if (!schedule.days.every((day) => routineDays.includes(day))) {
    issues.push(`${label} has an unknown day.`);
  }
  if (!timePattern.test(schedule.start_time)) issues.push(`${label} needs a valid start time.`);
  if (!timePattern.test(schedule.end_time)) issues.push(`${label} needs a valid end time.`);
  if (timePattern.test(schedule.start_time) && timePattern.test(schedule.end_time)) {
    const start = minuteOfDay(schedule.start_time);
    const end = minuteOfDay(schedule.end_time);
    if (start === end) issues.push(`${label} start and end times must differ.`);
    else if (schedule.ends_next_day && end >= start) {
      issues.push(`${label} next-day end must be earlier than its start.`);
    } else if (!schedule.ends_next_day && end <= start) {
      issues.push(`${label} end must be after its start or marked next day.`);
    }
  }
  if (!schedule.place_ids.length) issues.push(`${label} needs at least one place ID.`);
  if (!schedule.role_ids.length) issues.push(`${label} needs at least one role ID.`);
  for (const [field, values] of [
    ['days', schedule.days],
    ['place IDs', schedule.place_ids],
    ['role IDs', schedule.role_ids],
  ] as const) {
    if (new Set(values).size !== values.length) issues.push(`${label} has duplicate ${field}.`);
  }
  return issues;
};

export const validateAgentBehaviorProposalDraft = (draft: AgentBehaviorProposalDraft): string[] => {
  const issues: string[] = [];
  draft.routine_drafts.forEach((routine, routineIndex) => {
    const label = routine.name || `Routine ${routineIndex + 1}`;
    if (!identifierPattern.test(routine.id)) issues.push(`${label} needs a lowercase identifier.`);
    if (!identifierPattern.test(routine.agent_type_id)) {
      issues.push(`${label} needs a valid agent type ID.`);
    }
    if (!['measured', 'user_defined'].includes(routine.evidence.status)) {
      issues.push(`${label} needs measured or user-defined schedule evidence.`);
    }
    if (
      routine.evidence.status === 'measured' &&
      (!routine.evidence.source_title?.trim() || !routine.evidence.source_date?.trim())
    ) {
      issues.push(`${label} measured evidence needs a source title and date.`);
    }
    routine.steps.forEach((step, stepIndex) => {
      const stepLabel = `${label} · ${step.name || `step ${stepIndex + 1}`}`;
      if (!identifierPattern.test(step.id)) issues.push(`${stepLabel} needs a lowercase ID.`);
      if (!step.activity.trim()) issues.push(`${stepLabel} needs an activity.`);
      if (step.decision_tree_module_id && !identifierPattern.test(step.decision_tree_module_id)) {
        issues.push(`${stepLabel} has an invalid decision module ID.`);
      }
      issues.push(...scheduleIssues(step.schedule, stepLabel));
    });
  });
  const registry = draft.decision_tree_drafts;
  if (!registry || typeof registry.version !== 'string' || !registry.version.trim()) {
    issues.push('Decision-tree drafts need a version.');
  }
  if (!registry || !Array.isArray(registry.trees) || !Array.isArray(registry.modules)) {
    issues.push('Decision-tree drafts need tree and module arrays.');
  } else {
    registry.trees.forEach((tree, index) => {
      if (!tree || typeof tree !== 'object') {
        issues.push(`Decision tree ${index + 1} must be an object.`);
        return;
      }
      if (
        typeof tree?.id !== 'string' ||
        typeof tree?.root_module_id !== 'string' ||
        !identifierPattern.test(tree.id) ||
        !identifierPattern.test(tree.root_module_id)
      ) {
        issues.push(`Decision tree ${index + 1} needs valid tree and root module IDs.`);
      }
      if (!treeStatuses.has(tree.status))
        issues.push(`Decision tree ${tree.id} has invalid status.`);
    });
    registry.modules.forEach((module, index) => {
      if (!module || typeof module !== 'object') {
        issues.push(`Decision module ${index + 1} must be an object.`);
        return;
      }
      if (
        typeof module?.id !== 'string' ||
        typeof module?.entry_node !== 'string' ||
        !identifierPattern.test(module.id) ||
        !identifierPattern.test(module.entry_node)
      ) {
        issues.push(`Decision module ${index + 1} needs valid module and entry node IDs.`);
      }
      if (!Array.isArray(module.nodes) || !Array.isArray(module.edges)) {
        issues.push(`Decision module ${module.id} needs node and edge arrays.`);
      }
      if (!treeStatuses.has(module.status)) {
        issues.push(`Decision module ${module.id} has invalid status.`);
      }
    });
  }
  if (!Array.isArray(draft.decision_inputs)) {
    issues.push('Decision input plans must be an array.');
  } else {
    draft.decision_inputs.forEach((plan, index) => {
      if (!plan || typeof plan !== 'object') {
        issues.push(`Decision input ${index + 1} must be an object.`);
        return;
      }
      if (
        typeof plan?.tree_id !== 'string' ||
        typeof plan?.module_id !== 'string' ||
        typeof plan?.edge_id !== 'string' ||
        !identifierPattern.test(plan.tree_id) ||
        !identifierPattern.test(plan.module_id) ||
        !identifierPattern.test(plan.edge_id)
      ) {
        issues.push(`Decision input ${index + 1} needs valid tree, module, and edge IDs.`);
      }
      if (!Array.isArray(plan.source_feature_ids) || !nonEmptyStrings(plan.source_feature_ids)) {
        issues.push(`Decision input ${index + 1} has an invalid feature ID.`);
      }
      if (
        typeof plan.outcome !== 'string' ||
        typeof plan.population_scope !== 'string' ||
        typeof plan.time_scope !== 'string' ||
        !plan.outcome.trim() ||
        !plan.population_scope.trim() ||
        !plan.time_scope.trim()
      ) {
        issues.push(`Decision input ${index + 1} needs outcome, population, and time scopes.`);
      }
      if (!placeScopes.has(plan.place_scope)) {
        issues.push(`Decision input ${index + 1} has an invalid place scope.`);
      }
      if ((plan.decision_id === null) !== (plan.evidence_edge_id === null)) {
        issues.push(`Decision input ${index + 1} has an incomplete evidence link.`);
      }
    });
  }
  return issues;
};

function routineStepEditor(
  routineIndex: number,
  step: RoutineStepProposalDraft,
  stepIndex: number,
): string {
  const schedule = step.schedule;
  return `
    <section class="agent-type-proposal-routine-step" data-routine-step>
      <div class="agent-type-proposal-fields">
        <label>Step ID<input value="${escapeHtml(step.id)}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-step-field="id"></label>
        <label>Step name<input value="${escapeHtml(step.name)}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-step-field="name"></label>
        <label class="is-wide">Activity<input value="${escapeHtml(step.activity)}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-step-field="activity"></label>
        <label class="is-wide">Decision module ID<input value="${escapeHtml(step.decision_tree_module_id ?? '')}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-step-field="decision_tree_module_id" placeholder="Optional module ID"></label>
      </div>
      <div class="agent-type-proposal-schedule" data-schedule-present="${String(schedule !== null)}">
        <div class="agent-type-proposal-section-heading"><div><h4>Confirmed schedule</h4><p>${schedule ? 'Review every field before confirmation.' : 'No schedule was inferred. Enter observed or explicitly user-defined timing.'}</p></div></div>
        <fieldset class="agent-type-proposal-days"><legend>Days</legend>${routineDays
          .map(
            (day) =>
              `<label><input type="checkbox" aria-label="${day}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-day="${day}"${schedule?.days.includes(day) ? ' checked' : ''}>${day.slice(0, 3)}</label>`,
          )
          .join('')}</fieldset>
        <div class="agent-type-proposal-schedule-grid">
          <label>Start time<input type="time" value="${escapeHtml(schedule?.start_time ?? '')}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-field="start_time"></label>
          <label>End time<input type="time" value="${escapeHtml(schedule?.end_time ?? '')}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-field="end_time"></label>
          <label class="agent-type-proposal-checkbox"><input type="checkbox" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-field="ends_next_day"${schedule?.ends_next_day ? ' checked' : ''}>Ends next day</label>
          <label class="is-wide">Place IDs<input value="${escapeHtml(schedule?.place_ids.join(', ') ?? '')}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-field="place_ids" placeholder="assigned_workplace"></label>
          <label class="is-wide">Role IDs<input value="${escapeHtml(schedule?.role_ids.join(', ') ?? '')}" data-routine-index="${routineIndex}" data-step-index="${stepIndex}" data-schedule-field="role_ids" placeholder="worker"></label>
        </div>
      </div>
    </section>
  `;
}

function routineEditor(routine: RoutineProposalDraft, routineIndex: number): string {
  const evidence = routine.evidence;
  return `
    <details class="agent-type-proposal-routine" open>
      <summary><span>${escapeHtml(routine.name)}</span><small>${routine.steps.length} ${routine.steps.length === 1 ? 'step' : 'steps'} · ${escapeHtml(evidence.status.replace('_', ' '))}</small></summary>
      <div class="agent-type-proposal-routine-body">
        <div class="agent-type-proposal-fields">
          <label>Routine ID<input value="${escapeHtml(routine.id)}" data-routine-index="${routineIndex}" data-routine-field="id"></label>
          <label>Agent type ID<input value="${escapeHtml(routine.agent_type_id)}" data-routine-index="${routineIndex}" data-routine-field="agent_type_id"></label>
          <label>Name<input value="${escapeHtml(routine.name)}" data-routine-index="${routineIndex}" data-routine-field="name"></label>
          <label>Registry feature IDs<input value="${escapeHtml(routine.source_feature_ids.join(', '))}" data-routine-index="${routineIndex}" data-routine-field="source_feature_ids"></label>
          <label class="is-wide">Description<textarea data-routine-index="${routineIndex}" data-routine-field="description">${escapeHtml(routine.description ?? '')}</textarea></label>
        </div>
        <section class="agent-type-proposal-provenance">
          <div class="agent-type-proposal-section-heading"><div><h4>Schedule evidence</h4><p>Choose measured only with a named source and date. User-defined records this review as the provenance.</p></div></div>
          <div class="agent-type-proposal-fields">
            <label>Evidence status<select data-routine-index="${routineIndex}" data-evidence-field="status">${(
              ['unknown', 'illustrative', 'measured', 'user_defined'] as RoutineEvidenceStatus[]
            )
              .map(
                (status) =>
                  `<option value="${status}"${status === evidence.status ? ' selected' : ''}>${status.replace('_', ' ')}</option>`,
              )
              .join('')}</select></label>
            <label>Source date<input type="date" value="${escapeHtml(evidence.source_date ?? '')}" data-routine-index="${routineIndex}" data-evidence-field="source_date"></label>
            <label>Source title<input value="${escapeHtml(evidence.source_title ?? '')}" data-routine-index="${routineIndex}" data-evidence-field="source_title"></label>
            <label>Source URI<input value="${escapeHtml(evidence.source_uri ?? '')}" data-routine-index="${routineIndex}" data-evidence-field="source_uri"></label>
            <label class="is-wide">Evidence note<textarea data-routine-index="${routineIndex}" data-evidence-field="note">${escapeHtml(evidence.note ?? '')}</textarea></label>
          </div>
        </section>
        ${routine.steps
          .map((step, stepIndex) => routineStepEditor(routineIndex, step, stepIndex))
          .join('')}
      </div>
    </details>
  `;
}

export function evidenceRequirementMarkup(requirement: BehaviorEvidenceRequirementDraft): string {
  const blocked = requirement.status === 'missing';
  const heading =
    requirement.kind === 'decision_probability' && blocked
      ? 'Blocked: missing decision evidence'
      : `${requirement.status === 'matched' ? 'Matched' : 'Missing'} ${requirement.kind.replace('_', ' ')}`;
  return `
    <article class="agent-type-proposal-requirement" data-requirement-id="${escapeHtml(requirement.id)}" data-requirement-status="${requirement.status}" data-requirement-kind="${requirement.kind}">
      <header><strong>${escapeHtml(heading)}</strong><span>${escapeHtml(requirement.target_id)}</span></header>
      <p>${escapeHtml(requirement.message)}</p>
      <dl>
        <div><dt>Imported features</dt><dd>${escapeHtml(requirement.source_feature_ids.join(', ') || 'None linked')}</dd></div>
        <div><dt>Outcome</dt><dd>${escapeHtml(requirement.outcome)}</dd></div>
        <div><dt>Population</dt><dd>${escapeHtml(requirement.population_scope)}</dd></div>
        <div><dt>Place</dt><dd>${escapeHtml(requirement.place_scope)}</dd></div>
        <div><dt>Time</dt><dd>${escapeHtml(requirement.time_scope)}</dd></div>
        <div><dt>Accepted evidence</dt><dd>${escapeHtml(requirement.accepted_bases.join(', '))}</dd></div>
        <div class="is-wide"><dt>Required fields</dt><dd>${escapeHtml(requirement.required_fields.join(', '))}</dd></div>
        <div class="is-wide"><dt>Matched evidence IDs</dt><dd>${escapeHtml(requirement.matched_evidence_ids.join(', ') || 'None')}</dd></div>
      </dl>
    </article>
  `;
}

export function behaviorEditorMarkup(draft: AgentBehaviorProposalDraft): string {
  const blocked = draft.evidence_requirements.filter(
    (item) => item.kind === 'decision_probability' && item.status === 'missing',
  ).length;
  return `
    <section class="agent-type-proposal-behavior" data-behavior-proposal>
      <header class="agent-type-proposal-section-heading"><div><span class="agent-type-kicker">Behavior registries</span><h3>Routines and decision drafts</h3><p>Schedules require human-supplied timing and provenance. Missing decision probabilities stay unknown; ${blocked} blocked ${blocked === 1 ? 'requirement will' : 'requirements will'} be saved as draft work.</p></div></header>
      <div class="agent-type-proposal-routines">${draft.routine_drafts.length ? draft.routine_drafts.map(routineEditor).join('') : '<p class="agent-type-proposal-empty">No routines proposed.</p>'}</div>
      <section class="agent-type-proposal-json-editors">
        <div class="agent-type-proposal-section-heading"><div><h4>Decision-tree topology</h4><p>Edit topology and evidence input plans directly. A missing probability is never treated as known.</p></div></div>
        <label>Decision tree drafts JSON<textarea data-behavior-json="decision_tree_drafts" spellcheck="false">${escapeHtml(JSON.stringify(draft.decision_tree_drafts, null, 2))}</textarea></label>
        <label>Decision input plans JSON<textarea data-behavior-json="decision_inputs" spellcheck="false">${escapeHtml(JSON.stringify(draft.decision_inputs, null, 2))}</textarea></label>
      </section>
      <section class="agent-type-proposal-requirements">
        <div class="agent-type-proposal-section-heading"><div><h4>Evidence requirements</h4><p>Matched evidence can execute. Missing decision evidence remains blocked and contributes no probability or coefficient.</p></div></div>
        ${draft.evidence_requirements.length ? draft.evidence_requirements.map(evidenceRequirementMarkup).join('') : '<p class="agent-type-proposal-empty">No evidence requirements reported.</p>'}
      </section>
    </section>
  `;
}

const blankSchedule = (): RoutineScheduleDraft => ({
  days: [],
  start_time: '',
  end_time: '',
  ends_next_day: false,
  place_ids: [],
  role_ids: [],
});

const commaSeparatedValues = (value: string): string[] => [
  ...new Set(
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  ),
];

const routineEvidenceComplete = (routine: RoutineProposalDraft): boolean =>
  ['measured', 'user_defined'].includes(routine.evidence.status) &&
  (routine.evidence.status !== 'measured' ||
    Boolean(routine.evidence.source_title?.trim() && routine.evidence.source_date?.trim()));

const synchronizeRoutineRequirements = (draft: AgentBehaviorProposalDraft): void => {
  const requirements = draft.evidence_requirements.filter(
    (item) => item.kind === 'routine_schedule',
  );
  let requirementIndex = 0;
  for (const routine of draft.routine_drafts) {
    for (const step of routine.steps) {
      const requirement = requirements[requirementIndex];
      requirementIndex += 1;
      if (!requirement) continue;
      const matched = routineEvidenceComplete(routine) && !scheduleIssues(step.schedule, '').length;
      requirement.id = `routine-${routine.id}-${step.id}`;
      requirement.target_id = `${routine.id}.${step.id}`;
      requirement.source_feature_ids = [...routine.source_feature_ids];
      requirement.outcome = step.activity;
      requirement.population_scope = `agent type ${routine.agent_type_id}`;
      requirement.status = matched ? 'matched' : 'missing';
      requirement.message = matched
        ? 'Schedule supplied with measured provenance or explicit human definition'
        : 'Need days, start and end time, place ids, role ids, and either measured source provenance or explicit human definition';
    }
  }
};

export interface BehaviorProposalInputResult {
  handled: boolean;
  jsonIssueLabel?: string;
  jsonIssue?: string;
}

export function applyBehaviorProposalInput(
  draft: AgentBehaviorProposalDraft,
  control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
): BehaviorProposalInputResult {
  if (control.dataset.behaviorJson) {
    const jsonField = control.dataset.behaviorJson as 'decision_tree_drafts' | 'decision_inputs';
    const jsonIssueLabel =
      jsonField === 'decision_tree_drafts'
        ? 'Decision tree drafts JSON'
        : 'Decision input plans JSON';
    try {
      const value: unknown = JSON.parse(control.value);
      if (jsonField === 'decision_tree_drafts') {
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
          throw new Error('expected an object');
        }
        draft.decision_tree_drafts = value as DecisionTreeRegistryDraft;
      } else {
        if (!Array.isArray(value)) throw new Error('expected an array');
        draft.decision_inputs = value as DecisionEdgeInputPlanDraft[];
      }
      return { handled: true, jsonIssueLabel };
    } catch (error) {
      return {
        handled: true,
        jsonIssueLabel,
        jsonIssue: `${jsonIssueLabel} is invalid: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }
  if (control.dataset.routineIndex === undefined) return { handled: false };
  const routine = draft.routine_drafts[Number(control.dataset.routineIndex)];
  const step = routine?.steps[Number(control.dataset.stepIndex)];
  const routineField = control.dataset.routineField;
  const stepField = control.dataset.stepField;
  const evidenceField = control.dataset.evidenceField;
  const scheduleField = control.dataset.scheduleField;
  const scheduleDay = control.dataset.scheduleDay as RoutineDay | undefined;
  if (!routine) return { handled: true };
  if (routineField === 'id' || routineField === 'name' || routineField === 'agent_type_id') {
    routine[routineField] = control.value;
  } else if (routineField === 'description') {
    routine.description = control.value.trim() || null;
  } else if (routineField === 'source_feature_ids') {
    routine.source_feature_ids = commaSeparatedValues(control.value);
  } else if (evidenceField === 'status') {
    routine.evidence.status = control.value as RoutineEvidenceStatus;
  } else if (
    evidenceField === 'source_title' ||
    evidenceField === 'source_date' ||
    evidenceField === 'source_uri' ||
    evidenceField === 'note'
  ) {
    routine.evidence[evidenceField] = control.value.trim() || null;
  } else if (step && (stepField === 'id' || stepField === 'name' || stepField === 'activity')) {
    step[stepField] = control.value;
  } else if (step && stepField === 'decision_tree_module_id') {
    step.decision_tree_module_id = control.value.trim() || null;
  } else if (step && (scheduleField || scheduleDay)) {
    step.schedule ??= blankSchedule();
    if (scheduleDay && control instanceof HTMLInputElement) {
      step.schedule.days = control.checked
        ? [...new Set([...step.schedule.days, scheduleDay])]
        : step.schedule.days.filter((day) => day !== scheduleDay);
    } else if (scheduleField === 'ends_next_day' && control instanceof HTMLInputElement) {
      step.schedule.ends_next_day = control.checked;
    } else if (scheduleField === 'place_ids' || scheduleField === 'role_ids') {
      step.schedule[scheduleField] = commaSeparatedValues(control.value);
    } else if (scheduleField === 'start_time' || scheduleField === 'end_time') {
      step.schedule[scheduleField] = control.value;
    }
  }
  synchronizeRoutineRequirements(draft);
  return { handled: true };
}
