import './agent-type-proposal.css';

import type { AgentTypeGraphMemberDefinition } from './agent-type-graph';
import {
  applyBehaviorProposalInput,
  behaviorEditorMarkup,
  evidenceRequirementMarkup,
  isBehaviorProposal,
  validateAgentBehaviorProposalDraft,
} from './agent-behavior-proposal';
import type { AgentBehaviorProposalDraft } from './agent-behavior-proposal';

export * from './agent-behavior-proposal';

export type AgentTypeMemberKind = 'trait' | 'routine' | 'decision';

export interface AgentTypeOverrideDraft {
  member_kind: AgentTypeMemberKind;
  member_id: string;
  source_type_id: string;
}

export interface AgentTypeDefinitionDraft {
  id: string;
  name: string;
  description: string | null;
  parent_ids: string[];
  traits: AgentTypeGraphMemberDefinition[];
  routines: AgentTypeGraphMemberDefinition[];
  decisions: AgentTypeGraphMemberDefinition[];
  overrides: AgentTypeOverrideDraft[];
}

export interface AgentTypeProposalAudit {
  provider: 'openai_cli' | 'openai_api' | 'deterministic' | 'manual';
  model: string;
  generated_at: string;
  prompt_version: string;
}

export interface AgentTypeProposalBase {
  id: string;
  prompt: string;
  imported_feature_ids: string[];
  types: AgentTypeDefinitionDraft[];
  audit: AgentTypeProposalAudit;
  status: 'awaiting_confirmation';
  revision: number;
}

export interface AgentTypeProposalDraft extends AgentTypeProposalBase {
  schema_version: '1';
}

export type EditableAgentTypeProposalDraft = AgentTypeProposalDraft | AgentBehaviorProposalDraft;

export interface AgentTypeProposalPanelOptions {
  initialProposal?: EditableAgentTypeProposalDraft;
  requestProposal: (prompt: string) => Promise<EditableAgentTypeProposalDraft>;
  confirmProposal: (draft: EditableAgentTypeProposalDraft) => Promise<void>;
  onDraftChange?: (draft: EditableAgentTypeProposalDraft) => void;
  onCancel?: () => void;
}

export interface AgentTypeProposalPanelController {
  proposal(): EditableAgentTypeProposalDraft | null;
  replace(proposal: EditableAgentTypeProposalDraft): void;
  destroy(): void;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const draftMembers = (
  agentType: AgentTypeDefinitionDraft,
  kind: AgentTypeMemberKind,
): AgentTypeGraphMemberDefinition[] => {
  if (kind === 'trait') return agentType.traits;
  if (kind === 'routine') return agentType.routines;
  return agentType.decisions;
};

const identifierPattern = /^[a-z][a-z0-9_-]*$/;
export function validateAgentTypeProposalDraft(draft: EditableAgentTypeProposalDraft): string[] {
  const issues: string[] = [];
  if (!identifierPattern.test(draft.id)) issues.push('Proposal id must be a lowercase identifier.');
  if (!draft.prompt.trim()) issues.push('Proposal prompt is required.');
  if (!draft.types.length) issues.push('Add at least one agent type.');
  if (new Set(draft.imported_feature_ids).size !== draft.imported_feature_ids.length) {
    issues.push('Registry feature ids must be unique.');
  }
  const typeIds = draft.types.map((agentType) => agentType.id);
  const knownTypeIds = new Set(typeIds);
  if (knownTypeIds.size !== typeIds.length) issues.push('Agent type ids must be unique.');
  draft.types.forEach((agentType, typeIndex) => {
    const label = agentType.name.trim() || `Type ${typeIndex + 1}`;
    if (!identifierPattern.test(agentType.id)) {
      issues.push(`${label} needs a lowercase identifier.`);
    }
    if (!agentType.name.trim()) issues.push(`Type ${typeIndex + 1} needs a name.`);
    if (new Set(agentType.parent_ids).size !== agentType.parent_ids.length) {
      issues.push(`${label} has duplicate parents.`);
    }
    for (const parentId of agentType.parent_ids) {
      if (parentId === agentType.id) issues.push(`${label} cannot inherit from itself.`);
      else if (!knownTypeIds.has(parentId)) issues.push(`${label} has unknown parent ${parentId}.`);
    }
    for (const kind of ['trait', 'routine', 'decision'] as AgentTypeMemberKind[]) {
      const members = draftMembers(agentType, kind);
      const memberIds = members.map((member) => member.id);
      if (new Set(memberIds).size !== memberIds.length) {
        issues.push(`${label} has duplicate ${kind} ids.`);
      }
      members.forEach((member, memberIndex) => {
        const memberLabel = `${label} ${kind} ${memberIndex + 1}`;
        if (!identifierPattern.test(member.id)) issues.push(`${memberLabel} needs an id.`);
        if (!member.name.trim()) issues.push(`${memberLabel} needs a name.`);
        if (!member.definition.trim()) issues.push(`${memberLabel} needs a definition.`);
      });
    }
    agentType.overrides.forEach((override, overrideIndex) => {
      const overrideLabel = `${label} override ${overrideIndex + 1}`;
      if (!identifierPattern.test(override.member_id)) {
        issues.push(`${overrideLabel} needs a member id.`);
      }
      if (!knownTypeIds.has(override.source_type_id)) {
        issues.push(`${overrideLabel} needs a known source type.`);
      }
    });
    const overrideKeys = agentType.overrides.map(
      (override) => `${override.member_kind}:${override.member_id}`,
    );
    if (new Set(overrideKeys).size !== overrideKeys.length) {
      issues.push(`${label} has duplicate conflict overrides.`);
    }
  });
  const byId = new Map(draft.types.map((agentType) => [agentType.id, agentType]));
  const active: string[] = [];
  const complete = new Set<string>();
  const visit = (typeId: string): void => {
    if (active.includes(typeId)) {
      issues.push(
        `Inheritance cycle: ${[...active.slice(active.indexOf(typeId)), typeId].join(' → ')}`,
      );
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
  for (const typeId of typeIds) visit(typeId);
  if (isBehaviorProposal(draft)) issues.push(...validateAgentBehaviorProposalDraft(draft));
  return [...new Set(issues)];
}

const blankMember = (): AgentTypeGraphMemberDefinition => ({
  id: '',
  name: '',
  definition: '',
  description: null,
  source_feature_ids: [],
});

const blankType = (): AgentTypeDefinitionDraft => ({
  id: '',
  name: '',
  description: null,
  parent_ids: [],
  traits: [],
  routines: [],
  decisions: [],
  overrides: [],
});

function manualProposal(): AgentTypeProposalDraft {
  return {
    schema_version: '1',
    id: 'agent_types',
    prompt: 'Manually defined agent types',
    imported_feature_ids: [],
    types: [blankType()],
    audit: {
      provider: 'manual',
      model: 'human',
      generated_at: new Date().toISOString(),
      prompt_version: 'manual-v1',
    },
    status: 'awaiting_confirmation',
    revision: 0,
  };
}

const providerLabel = (provider: AgentTypeProposalAudit['provider']): string =>
  ({
    openai_cli: 'OpenAI CLI',
    openai_api: 'OpenAI API',
    deterministic: 'Deterministic parser',
    manual: 'Manual entry',
  })[provider];

function parentEditor(
  typeIndex: number,
  agentType: AgentTypeDefinitionDraft,
  types: AgentTypeDefinitionDraft[],
): string {
  const choices = types
    .map((candidate, parentIndex) => {
      if (parentIndex === typeIndex) return '';
      const checked = agentType.parent_ids.includes(candidate.id);
      return `<label><input type="checkbox" data-proposal-parent="${escapeHtml(candidate.id)}" data-type-index="${typeIndex}"${checked ? ' checked' : ''}>${escapeHtml(candidate.name || candidate.id || `Type ${parentIndex + 1}`)}</label>`;
    })
    .join('');
  return (
    choices ||
    '<span class="agent-type-proposal-empty">Add another type to create inheritance.</span>'
  );
}

function memberEditor(
  typeIndex: number,
  kind: AgentTypeMemberKind,
  members: AgentTypeGraphMemberDefinition[],
): string {
  const rows = members
    .map(
      (member, memberIndex) => `
        <div class="agent-type-proposal-member" data-proposal-member-row>
          <label>ID<input value="${escapeHtml(member.id)}" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" data-draft-field="id"></label>
          <label>Name<input value="${escapeHtml(member.name)}" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" data-draft-field="name"></label>
          <label class="is-wide">Definition<input value="${escapeHtml(member.definition)}" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" data-draft-field="definition"></label>
          <label class="is-wide">Description<input value="${escapeHtml(member.description ?? '')}" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" data-draft-field="description"></label>
          <label class="is-wide">Registry feature IDs<input value="${escapeHtml(member.source_feature_ids.join(', '))}" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" data-draft-field="source_feature_ids"></label>
          <button type="button" data-proposal-action="remove-member" data-type-index="${typeIndex}" data-member-kind="${kind}" data-member-index="${memberIndex}" aria-label="Remove ${kind} ${escapeHtml(member.name || member.id || String(memberIndex + 1))}">Remove</button>
        </div>
      `,
    )
    .join('');
  return `
    <section class="agent-type-proposal-members">
      <div><h4>${kind[0].toUpperCase()}${kind.slice(1)}s</h4><button type="button" data-proposal-action="add-member" data-type-index="${typeIndex}" data-member-kind="${kind}">Add ${kind}</button></div>
      ${rows || '<p class="agent-type-proposal-empty">None proposed.</p>'}
    </section>
  `;
}

function overrideEditor(
  typeIndex: number,
  agentType: AgentTypeDefinitionDraft,
  types: AgentTypeDefinitionDraft[],
): string {
  const rows = agentType.overrides
    .map(
      (override, overrideIndex) => `
        <div class="agent-type-proposal-override">
          <label>Kind<select data-type-index="${typeIndex}" data-override-index="${overrideIndex}" data-draft-field="member_kind">${(
            ['trait', 'routine', 'decision'] as AgentTypeMemberKind[]
          )
            .map(
              (kind) =>
                `<option value="${kind}"${kind === override.member_kind ? ' selected' : ''}>${kind}</option>`,
            )
            .join('')}</select></label>
          <label>Member ID<input value="${escapeHtml(override.member_id)}" data-type-index="${typeIndex}" data-override-index="${overrideIndex}" data-draft-field="member_id"></label>
          <label>Use source<select data-type-index="${typeIndex}" data-override-index="${overrideIndex}" data-draft-field="source_type_id">${types
            .filter((candidate) => candidate.id !== agentType.id)
            .map(
              (candidate) =>
                `<option value="${escapeHtml(candidate.id)}"${candidate.id === override.source_type_id ? ' selected' : ''}>${escapeHtml(candidate.name || candidate.id)}</option>`,
            )
            .join('')}</select></label>
          <button type="button" data-proposal-action="remove-override" data-type-index="${typeIndex}" data-override-index="${overrideIndex}">Remove</button>
        </div>
      `,
    )
    .join('');
  return `
    <section class="agent-type-proposal-members">
      <div><h4>Conflict overrides</h4><button type="button" data-proposal-action="add-override" data-type-index="${typeIndex}">Add override</button></div>
      ${rows || '<p class="agent-type-proposal-empty">No explicit conflict overrides.</p>'}
    </section>
  `;
}

function typeEditor(
  agentType: AgentTypeDefinitionDraft,
  typeIndex: number,
  types: AgentTypeDefinitionDraft[],
): string {
  return `
    <details class="agent-type-proposal-type" open>
      <summary><span>${escapeHtml(agentType.name || `New type ${typeIndex + 1}`)}</span><small>${agentType.parent_ids.length} parents · ${agentType.traits.length + agentType.routines.length + agentType.decisions.length} definitions</small></summary>
      <div class="agent-type-proposal-type-body">
        <div class="agent-type-proposal-fields">
          <label>ID<input value="${escapeHtml(agentType.id)}" data-type-index="${typeIndex}" data-draft-field="id"></label>
          <label>Name<input value="${escapeHtml(agentType.name)}" data-type-index="${typeIndex}" data-draft-field="name"></label>
          <label class="is-wide">Description<textarea data-type-index="${typeIndex}" data-draft-field="description">${escapeHtml(agentType.description ?? '')}</textarea></label>
        </div>
        <fieldset class="agent-type-proposal-parents"><legend>Inherits from</legend>${parentEditor(typeIndex, agentType, types)}</fieldset>
        ${memberEditor(typeIndex, 'trait', agentType.traits)}
        ${memberEditor(typeIndex, 'routine', agentType.routines)}
        ${memberEditor(typeIndex, 'decision', agentType.decisions)}
        ${overrideEditor(typeIndex, agentType, types)}
        <button class="agent-type-proposal-remove-type" type="button" data-proposal-action="remove-type" data-type-index="${typeIndex}">Remove agent type</button>
      </div>
    </details>
  `;
}

function auditMarkup(audit: AgentTypeProposalAudit): string {
  return `
    <div class="agent-type-proposal-audit">
      <span>Created via <strong>${providerLabel(audit.provider)}</strong></span>
      <span>Model <strong>${escapeHtml(audit.model)}</strong></span>
      <span>Prompt <strong>${escapeHtml(audit.prompt_version)}</strong></span>
      <span>${escapeHtml(audit.generated_at)}</span>
    </div>
  `;
}

export function mountAgentTypeProposalPanel(
  host: HTMLElement,
  options: AgentTypeProposalPanelOptions,
): AgentTypeProposalPanelController {
  let draft = options.initialProposal ? structuredClone(options.initialProposal) : null;
  let busy = false;
  let message = '';
  let behaviorJsonIssues: string[] = [];
  const root = document.createElement('section');
  root.className = 'agent-type-proposal';
  host.replaceChildren(root);

  const copy = (): EditableAgentTypeProposalDraft | null => (draft ? structuredClone(draft) : null);
  const notify = (): void => {
    if (draft) options.onDraftChange?.(structuredClone(draft));
  };
  const refreshRequirementCards = (): void => {
    if (!draft || !isBehaviorProposal(draft)) return;
    const behaviorDraft = draft;
    root.querySelectorAll<HTMLElement>('[data-requirement-id]').forEach((card) => {
      const requirement = behaviorDraft.evidence_requirements.find(
        (item) => item.id === card.dataset.requirementId,
      );
      if (requirement) card.outerHTML = evidenceRequirementMarkup(requirement);
    });
  };
  const refreshValidation = (): void => {
    if (!draft) return;
    const issues = [...validateAgentTypeProposalDraft(draft), ...behaviorJsonIssues];
    const validation = root.querySelector<HTMLElement>('[data-proposal-validation]');
    const confirm = root.querySelector<HTMLButtonElement>('[data-proposal-action="confirm"]');
    if (validation) {
      const blockedDecisionCount = isBehaviorProposal(draft)
        ? draft.evidence_requirements.filter(
            (item) => item.kind === 'decision_probability' && item.status === 'missing',
          ).length
        : 0;
      validation.innerHTML = issues.length
        ? `<strong>Resolve before confirmation</strong><ul>${issues.map((issue) => `<li>${escapeHtml(issue)}</li>`).join('')}</ul>`
        : `<span>Ready for explicit confirmation.${blockedDecisionCount ? ` ${blockedDecisionCount} decision ${blockedDecisionCount === 1 ? 'tree remains' : 'trees remain'} blocked and will be saved as draft work.` : ''}</span>`;
      validation.dataset.valid = String(!issues.length);
    }
    if (confirm) confirm.disabled = busy || Boolean(issues.length);
  };
  const render = (): void => {
    if (!draft) {
      root.innerHTML = `
        <div class="agent-type-proposal-start">
          <span class="agent-type-kicker">Agent type proposal</span>
          <h2>Define agent types</h2>
          <p>Describe the roles to create. Generated types remain a draft until you review and confirm them.</p>
          <label>Proposal request<textarea data-proposal-prompt placeholder="Create business, worker, student, and family roles from imported occupation and household data"></textarea></label>
          <div><button type="button" data-proposal-action="request"${busy ? ' disabled' : ''}>Propose from imported data</button><button type="button" data-proposal-action="manual"${busy ? ' disabled' : ''}>Start manually</button><button type="button" data-proposal-action="cancel">Cancel</button></div>
          <p class="agent-type-proposal-message" role="status">${escapeHtml(message)}</p>
        </div>
      `;
      return;
    }
    root.innerHTML = `
      <header class="agent-type-proposal-header">
        <div><span class="agent-type-kicker">Awaiting confirmation</span><h2>Review agent type proposal</h2><p>Edit every type, inheritance edge, and definition before saving.</p></div>
        <button type="button" data-proposal-action="add-type">Add agent type</button>
      </header>
      ${auditMarkup(draft.audit)}
      <div class="agent-type-proposal-context">
        <label>Proposal ID<input value="${escapeHtml(draft.id)}" data-proposal-field="id"></label>
        <label>Registry features used<input value="${escapeHtml(draft.imported_feature_ids.join(', '))}" data-proposal-field="imported_feature_ids"></label>
        <label class="is-wide">Original request<textarea data-proposal-field="prompt">${escapeHtml(draft.prompt)}</textarea></label>
      </div>
      <div class="agent-type-proposal-types">${draft.types.map((agentType, index) => typeEditor(agentType, index, draft!.types)).join('')}</div>
      ${isBehaviorProposal(draft) ? behaviorEditorMarkup(draft) : ''}
      <div class="agent-type-proposal-validation" data-proposal-validation></div>
      <p class="agent-type-proposal-message" role="status">${escapeHtml(message)}</p>
      <footer><button type="button" data-proposal-action="cancel">Cancel</button><button type="button" data-proposal-action="confirm"${busy ? ' disabled' : ''}>Confirm and save</button></footer>
    `;
    refreshValidation();
  };
  const changed = (): void => {
    message = '';
    notify();
    refreshRequirementCards();
    refreshValidation();
  };
  const onInput = (event: Event): void => {
    if (
      !draft ||
      !(
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      )
    )
      return;
    const control = event.target;
    const field = control.dataset.draftField;
    const typeIndex = Number(control.dataset.typeIndex);
    const agentType = draft.types[typeIndex];
    if (isBehaviorProposal(draft)) {
      const result = applyBehaviorProposalInput(draft, control);
      if (result.handled) {
        if (result.jsonIssueLabel) {
          behaviorJsonIssues = behaviorJsonIssues.filter(
            (issue) => !issue.startsWith(result.jsonIssueLabel!),
          );
        }
        if (result.jsonIssue) behaviorJsonIssues.push(result.jsonIssue);
        changed();
        return;
      }
    }
    if (control.dataset.proposalField === 'id') draft.id = control.value;
    else if (control.dataset.proposalField === 'prompt') draft.prompt = control.value;
    else if (control.dataset.proposalField === 'imported_feature_ids') {
      draft.imported_feature_ids = control.value
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
    } else if (agentType && control.dataset.memberKind && control.dataset.memberIndex) {
      const kind = control.dataset.memberKind as AgentTypeMemberKind;
      const member = draftMembers(agentType, kind)[Number(control.dataset.memberIndex)];
      if (!member || !field) return;
      if (field === 'source_feature_ids')
        member.source_feature_ids = control.value
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean);
      else if (field === 'id' || field === 'name' || field === 'definition')
        member[field] = control.value;
      else if (field === 'description') member.description = control.value.trim() || null;
    } else if (agentType && control.dataset.overrideIndex && field) {
      const override = agentType.overrides[Number(control.dataset.overrideIndex)];
      if (!override) return;
      if (field === 'member_kind') override.member_kind = control.value as AgentTypeMemberKind;
      else if (field === 'member_id' || field === 'source_type_id') override[field] = control.value;
    } else if (agentType && field) {
      if (field === 'id') {
        const previousId = agentType.id;
        agentType.id = control.value;
        for (const candidate of draft.types) {
          candidate.parent_ids = candidate.parent_ids.map((parentId) =>
            parentId === previousId ? control.value : parentId,
          );
          for (const override of candidate.overrides) {
            if (override.source_type_id === previousId) override.source_type_id = control.value;
          }
        }
        root.querySelectorAll<HTMLElement>('[data-proposal-parent]').forEach((parent) => {
          if (parent.dataset.proposalParent === previousId) {
            parent.dataset.proposalParent = control.value;
          }
        });
      } else if (field === 'name') agentType.name = control.value;
      else if (field === 'description') agentType.description = control.value.trim() || null;
    }
    changed();
  };
  const onChange = (event: Event): void => {
    if (!draft || !(event.target instanceof HTMLInputElement)) return;
    const parentId = event.target.dataset.proposalParent;
    const agentType = draft.types[Number(event.target.dataset.typeIndex)];
    if (!parentId || !agentType) return;
    agentType.parent_ids = event.target.checked
      ? [...new Set([...agentType.parent_ids, parentId])]
      : agentType.parent_ids.filter((candidate) => candidate !== parentId);
    changed();
  };
  const handleAction = async (action: string, control: HTMLElement): Promise<void> => {
    if (action === 'cancel') {
      options.onCancel?.();
      return;
    }
    if (action === 'manual') {
      draft = manualProposal();
      behaviorJsonIssues = [];
      message = '';
      render();
      notify();
      return;
    }
    if (action === 'request') {
      const prompt =
        root.querySelector<HTMLTextAreaElement>('[data-proposal-prompt]')?.value.trim() ?? '';
      if (!prompt) {
        message = 'Enter a proposal request.';
        render();
        return;
      }
      busy = true;
      message = 'Generating proposal…';
      render();
      try {
        draft = structuredClone(await options.requestProposal(prompt));
        behaviorJsonIssues = [];
        message = '';
        notify();
      } catch (error) {
        message = error instanceof Error ? error.message : String(error);
      } finally {
        busy = false;
        render();
      }
      return;
    }
    if (!draft) return;
    const typeIndex = Number(control.dataset.typeIndex);
    const agentType = draft.types[typeIndex];
    if (action === 'add-type') draft.types.push(blankType());
    else if (action === 'remove-type' && agentType) draft.types.splice(typeIndex, 1);
    else if (action === 'add-member' && agentType) {
      draftMembers(agentType, control.dataset.memberKind as AgentTypeMemberKind).push(
        blankMember(),
      );
    } else if (action === 'remove-member' && agentType) {
      draftMembers(agentType, control.dataset.memberKind as AgentTypeMemberKind).splice(
        Number(control.dataset.memberIndex),
        1,
      );
    } else if (action === 'add-override' && agentType) {
      agentType.overrides.push({
        member_kind: 'trait',
        member_id: '',
        source_type_id:
          agentType.parent_ids[0] ??
          draft.types.find((candidate) => candidate !== agentType)?.id ??
          '',
      });
    } else if (action === 'remove-override' && agentType) {
      agentType.overrides.splice(Number(control.dataset.overrideIndex), 1);
    } else if (action === 'confirm') {
      const issues = [...validateAgentTypeProposalDraft(draft), ...behaviorJsonIssues];
      if (issues.length) return;
      busy = true;
      message = 'Saving confirmed proposal…';
      render();
      try {
        await options.confirmProposal(structuredClone(draft));
        message = 'Proposal confirmed and saved.';
      } catch (error) {
        message = error instanceof Error ? error.message : String(error);
      } finally {
        busy = false;
        render();
      }
      return;
    } else return;
    render();
    notify();
  };
  const onClick = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const control = target.closest<HTMLElement>('[data-proposal-action]');
    if (control?.dataset.proposalAction) void handleAction(control.dataset.proposalAction, control);
  };
  root.addEventListener('input', onInput);
  root.addEventListener('change', onChange);
  root.addEventListener('click', onClick);
  render();
  return {
    proposal: copy,
    replace(nextProposal) {
      draft = structuredClone(nextProposal);
      behaviorJsonIssues = [];
      message = '';
      render();
      notify();
    },
    destroy() {
      root.removeEventListener('input', onInput);
      root.removeEventListener('change', onChange);
      root.removeEventListener('click', onClick);
      root.remove();
    },
  };
}
