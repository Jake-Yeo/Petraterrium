import './prompt2-ui.css';
import { escapeHtml, formatPercent, parseFiniteNumber } from './prompt2-ui-utils';

export const GLOBAL_AGENT_TYPES = [
  { id: 'person', name: 'Person' },
  { id: 'caregiver', name: 'Caregiver' },
  { id: 'student', name: 'Student' },
  { id: 'worker', name: 'Worker' },
  { id: 'business_owner', name: 'Business owner' },
  { id: 'working_student', name: 'Working student' },
] as const;

export type GlobalAgentTypeId = (typeof GLOBAL_AGENT_TYPES)[number]['id'];

export type GlobalAgentTypeMix = Record<GlobalAgentTypeId, number>;

export interface AgentTypeMixState {
  mix: GlobalAgentTypeMix;
  total: number;
  valid: boolean;
}

export interface AgentTypeMixControlOptions {
  initialMix?: Partial<GlobalAgentTypeMix>;
  disabled?: boolean;
  onChange?: (state: AgentTypeMixState) => void;
}

const DEFAULT_MIX: GlobalAgentTypeMix = {
  person: 0.2,
  caregiver: 0.1,
  student: 0.15,
  worker: 0.35,
  business_owner: 0.1,
  working_student: 0.1,
};

export class AgentTypeMixControl {
  private mix: GlobalAgentTypeMix;
  private disabled: boolean;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: AgentTypeMixControlOptions = {},
  ) {
    this.mix = { ...DEFAULT_MIX, ...options.initialMix };
    this.disabled = options.disabled ?? false;
    this.host.addEventListener('input', this.onInput);
    this.render();
    this.emit();
  }

  value(): GlobalAgentTypeMix {
    return { ...this.mix };
  }

  state(): AgentTypeMixState {
    const total = Object.values(this.mix).reduce((sum, value) => sum + value, 0);
    return {
      mix: this.value(),
      total,
      valid: Math.abs(total - 1) <= 0.000001,
    };
  }

  setDisabled(disabled: boolean): void {
    this.disabled = disabled;
    this.render();
  }

  setMix(mix: Partial<GlobalAgentTypeMix>): void {
    for (const agentType of GLOBAL_AGENT_TYPES) {
      const value = mix[agentType.id];
      if (value !== undefined) this.mix[agentType.id] = this.clamp(value);
    }
    this.render();
    this.emit();
  }

  destroy(): void {
    this.host.removeEventListener('input', this.onInput);
    this.host.replaceChildren();
  }

  private readonly onInput = (event: Event): void => {
    const input = event.target instanceof HTMLInputElement ? event.target : null;
    const agentTypeId = input?.dataset.agentType as GlobalAgentTypeId | undefined;
    if (!input || !agentTypeId || !GLOBAL_AGENT_TYPES.some((item) => item.id === agentTypeId)) {
      return;
    }
    const parsed = parseFiniteNumber(input.value);
    if (parsed === null) return;
    this.mix[agentTypeId] = this.clamp(parsed);
    const counterpart = this.host.querySelector<HTMLInputElement>(
      `input[data-agent-type="${agentTypeId}"][data-mix-control="${input.dataset.mixControl === 'range' ? 'number' : 'range'}"]`,
    );
    if (counterpart) counterpart.value = String(this.mix[agentTypeId]);
    this.renderTotal();
    this.emit();
  };

  private clamp(value: number): number {
    return Math.min(1, Math.max(0, Math.round(value * 1000) / 1000));
  }

  private emit(): void {
    this.options.onChange?.(this.state());
  }

  private render(): void {
    this.host.className = 'prompt2-card agent-type-mix-control';
    this.host.innerHTML = `
      <header class="prompt2-card-heading">
        <div>
          <span class="prompt2-eyebrow">AGENT TYPE MIX</span>
          <h3>Global population roles</h3>
        </div>
        <output data-mix-total></output>
      </header>
      <p class="prompt2-help">Set a share for every global type. Launch is available only when the six shares total 100%.</p>
      <div class="agent-type-mix-rows">
        ${GLOBAL_AGENT_TYPES.map((agentType) => this.rowMarkup(agentType.id, agentType.name)).join('')}
      </div>
      <p class="prompt2-validation" data-mix-message role="status"></p>
    `;
    this.renderTotal();
  }

  private rowMarkup(id: GlobalAgentTypeId, name: string): string {
    const value = this.mix[id];
    const disabled = this.disabled ? 'disabled' : '';
    return `
      <div class="agent-type-mix-row">
        <label for="agent-type-range-${escapeHtml(id)}">
          <strong>${escapeHtml(name)}</strong>
          <span>${formatPercent(value)}</span>
        </label>
        <input id="agent-type-range-${escapeHtml(id)}" type="range" min="0" max="1" step="0.01" value="${value}" data-agent-type="${escapeHtml(id)}" data-mix-control="range" aria-label="${escapeHtml(name)} share slider" ${disabled}>
        <label class="agent-type-mix-number"><span class="sr-only">${escapeHtml(name)} share</span><input type="number" min="0" max="1" step="0.01" value="${value}" data-agent-type="${escapeHtml(id)}" data-mix-control="number" aria-label="${escapeHtml(name)} share" ${disabled}></label>
      </div>
    `;
  }

  private renderTotal(): void {
    const state = this.state();
    const output = this.host.querySelector<HTMLOutputElement>('[data-mix-total]');
    const message = this.host.querySelector<HTMLElement>('[data-mix-message]');
    if (output) {
      output.textContent = `Total ${formatPercent(state.total)}`;
      output.classList.toggle('is-invalid', !state.valid);
    }
    if (message) {
      message.classList.toggle('is-invalid', !state.valid);
      message.textContent = state.valid
        ? 'Mix is valid. All six shares total 100%.'
        : `Mix totals ${formatPercent(state.total)}. Adjust the shares until the total is 100%.`;
    }
    for (const agentType of GLOBAL_AGENT_TYPES) {
      const label = this.host.querySelector<HTMLElement>(
        `label[for="agent-type-range-${agentType.id}"] span`,
      );
      if (label) label.textContent = formatPercent(this.mix[agentType.id]);
    }
  }
}
