import './prompt2-ui.css';
import type { DslDurationDistribution } from './dsl-editor-model';
import { escapeHtml, formatNumber } from './prompt2-ui-utils';

export interface AgentTimedActionOccurrence {
  occurrence_id: string;
  action_id: string;
  action_name: string;
  category: string;
  mode: 'primary' | 'passive';
  duration: DslDurationDistribution;
  sampled_duration_hours: number;
  hours_in_tick: number;
  remaining_duration_hours: number;
  continuing_to_next_tick: boolean;
  interrupted: boolean;
  interruption_reason?: string | null;
}

export interface AgentTickTimeAccounting {
  tick: number;
  day: number;
  start_hour: number;
  tick_hours: number;
  actions: AgentTimedActionOccurrence[];
  interruptions?: Array<{
    interrupted_action: string;
    interrupting_action: string;
    remaining_hours: number;
    outcome: string;
  }>;
}

export interface AgentDayTimeAccounting {
  day: number;
  date: string;
  category_hours: Record<string, number>;
  ticks: AgentTickTimeAccounting[];
}

export interface AgentTimeAccountingData {
  agent_id: string;
  agent_label: string;
  days: AgentDayTimeAccounting[];
}

export class AgentTimeAccountingView {
  private data: AgentTimeAccountingData;
  private selectedDay: number;
  private selectedTick: number;

  constructor(
    private readonly host: HTMLElement,
    data: AgentTimeAccountingData,
  ) {
    this.data = structuredClone(data);
    this.selectedDay = data.days[0]?.day ?? 0;
    this.selectedTick = data.days[0]?.ticks[0]?.tick ?? 0;
    this.host.addEventListener('change', this.onChange);
    this.render();
  }

  update(data: AgentTimeAccountingData): void {
    this.data = structuredClone(data);
    if (!this.data.days.some((day) => day.day === this.selectedDay)) {
      this.selectedDay = this.data.days[0]?.day ?? 0;
    }
    const selectedDay = this.currentDay();
    if (!selectedDay?.ticks.some((tick) => tick.tick === this.selectedTick)) {
      this.selectedTick = selectedDay?.ticks[0]?.tick ?? 0;
    }
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('change', this.onChange);
    this.host.replaceChildren();
  }

  private readonly onChange = (event: Event): void => {
    const select = event.target instanceof HTMLSelectElement ? event.target : null;
    if (!select) return;
    if (select.name === 'time-accounting-day') {
      this.selectedDay = Number(select.value);
      this.selectedTick = this.currentDay()?.ticks[0]?.tick ?? 0;
    }
    if (select.name === 'time-accounting-tick') this.selectedTick = Number(select.value);
    this.render();
  };

  private currentDay(): AgentDayTimeAccounting | undefined {
    return this.data.days.find((day) => day.day === this.selectedDay);
  }

  private currentTick(): AgentTickTimeAccounting | undefined {
    return this.currentDay()?.ticks.find((tick) => tick.tick === this.selectedTick);
  }

  private render(): void {
    const day = this.currentDay();
    const tick = this.currentTick();
    this.host.className = 'prompt2-card agent-time-accounting';
    if (!day || !tick) {
      this.host.innerHTML = `<header class="prompt2-card-heading"><div><span class="prompt2-eyebrow">TIME ACCOUNTING</span><h3>Time accounting for ${escapeHtml(this.data.agent_label)}</h3></div></header><p class="time-accounting-empty">No recorded time accounting is available for this agent.</p>`;
      return;
    }
    const primaryUsed = tick.actions
      .filter((action) => action.mode === 'primary')
      .reduce((sum, action) => sum + action.hours_in_tick, 0);
    const remaining = Math.max(0, tick.tick_hours - primaryUsed);
    const overBudget = primaryUsed > tick.tick_hours + 0.000001;
    const dayTotal = Object.values(day.category_hours).reduce((sum, hours) => sum + hours, 0);
    const dayValid = Math.abs(dayTotal - 24) <= 0.000001;
    this.host.innerHTML = `
      <header class="prompt2-card-heading">
        <div><span class="prompt2-eyebrow">TIME ACCOUNTING</span><h3>Time accounting for ${escapeHtml(this.data.agent_label)}</h3><p class="prompt2-muted">Agent ${escapeHtml(this.data.agent_id)}</p></div>
        <div class="time-accounting-selectors">
          <label><span>Day</span><select name="time-accounting-day">${this.data.days.map((item) => `<option value="${item.day}" ${item.day === day.day ? 'selected' : ''}>Day ${item.day} · ${escapeHtml(item.date)}</option>`).join('')}</select></label>
          <label><span>Tick</span><select name="time-accounting-tick">${day.ticks.map((item) => `<option value="${item.tick}" ${item.tick === tick.tick ? 'selected' : ''}>Tick ${item.tick} · ${formatNumber(item.start_hour)}:00</option>`).join('')}</select></label>
        </div>
      </header>
      <section class="time-accounting-tick ${overBudget ? 'is-over-budget' : ''}" aria-label="Selected tick accounting">
        <div class="time-accounting-totals">
          <span><small>Tick budget</small><strong>${formatNumber(tick.tick_hours)} h</strong></span>
          <span><small>Primary time used</small><strong>${formatNumber(primaryUsed)} h</strong></span>
          <span><small>Time remaining</small><strong>${formatNumber(remaining)} h</strong></span>
          <span><small>Budget status</small><strong>${overBudget ? 'Rejected' : 'Valid'}</strong></span>
        </div>
        ${overBudget ? `<p class="time-accounting-budget-error" role="alert">Tick rejected: primary actions use ${formatNumber(primaryUsed)} hours, exceeding the ${formatNumber(tick.tick_hours)}-hour budget. ${escapeHtml(this.overBudgetActions(tick.actions, tick.tick_hours))}</p>` : ''}
        <div class="time-accounting-actions">${tick.actions.map((action) => this.actionMarkup(action)).join('') || '<p class="time-accounting-idle">No selected action. The tick remains idle/rest time.</p>'}</div>
        ${(tick.interruptions?.length ?? 0) ? `<section aria-label="Recorded interruptions"><h4>Interruptions</h4>${tick.interruptions!.map((item) => `<p class="time-action-interruption">${escapeHtml(item.interrupted_action)} interrupted by ${escapeHtml(item.interrupting_action)} · ${escapeHtml(item.outcome)} · ${formatNumber(item.remaining_hours)} h remaining</p>`).join('')}</section>` : ''}
      </section>
      <section class="time-accounting-day" aria-label="Selected day accounting">
        <header><div><span class="prompt2-eyebrow">DAY ${day.day}</span><h4>24-hour allocation</h4></div><strong class="${dayValid ? '' : 'is-invalid'}">${formatNumber(dayTotal)} / 24 h</strong></header>
        <div class="time-accounting-day-bar" aria-label="Day allocation">${Object.entries(
          day.category_hours,
        )
          .map(
            ([category, hours]) =>
              `<span style="width:${Math.max(0, (hours / 24) * 100)}%" title="${escapeHtml(category)} ${formatNumber(hours)} hours"></span>`,
          )
          .join('')}</div>
        <dl>${Object.entries(day.category_hours)
          .map(
            ([category, hours]) =>
              `<div><dt>${escapeHtml(category)}</dt><dd>${formatNumber(hours)} h</dd></div>`,
          )
          .join('')}</dl>
        <p class="prompt2-validation ${dayValid ? '' : 'is-invalid'}" role="status">${dayValid ? 'Recorded categories sum to exactly 24 hours.' : `Day total is ${formatNumber(dayTotal)} hours. The recorded day must sum to 24 hours.`}</p>
      </section>
    `;
  }

  private actionMarkup(action: AgentTimedActionOccurrence): string {
    const evidence = action.duration.evidence;
    const evidenceSources = evidence.source
      .split(';')
      .map((source) => source.trim())
      .filter(Boolean);
    const primarySource = evidenceSources[0] ?? evidence.source;
    const continuation = action.continuing_to_next_tick
      ? `<span class="time-action-continuing">Continues · ${formatNumber(action.remaining_duration_hours)} h remaining</span>`
      : '<span>Completes in this tick</span>';
    const interrupted = action.interrupted
      ? `<p class="time-action-interruption">Interrupted${action.interruption_reason ? `: ${escapeHtml(action.interruption_reason)}` : ''}</p>`
      : '';
    return `
      <article class="time-accounting-action mode-${action.mode}">
        <header><div><span class="time-action-mode">${escapeHtml(action.mode)}</span><h4>${escapeHtml(action.action_name)}</h4></div><strong>${formatNumber(action.hours_in_tick)} h in tick</strong></header>
        <div class="time-action-duration">
          <span><small>Minimum</small>${formatNumber(action.duration.min_hours)} h</span>
          <span><small>Median</small>${formatNumber(action.duration.median_hours)} h</span>
          <span><small>Maximum</small>${formatNumber(action.duration.max_hours)} h</span>
          <span><small>Sampled occurrence</small><strong>${formatNumber(action.sampled_duration_hours)} h</strong></span>
          <span><small>Shape</small>${escapeHtml(action.duration.shape)}</span>
        </div>
        <div class="time-action-evidence"><span>${escapeHtml(evidence.status)}</span><span>${escapeHtml(primarySource)}</span><span>Version ${escapeHtml(evidence.sourceVersion)}</span><span>Uncertainty ${formatNumber(evidence.uncertainty)}</span></div>
        ${evidenceSources.length > 1 ? `<details class="time-action-provenance"><summary>Full duration provenance (${evidenceSources.length} sources)</summary><p>${escapeHtml(evidence.source)}</p></details>` : ''}
        <footer>${continuation}</footer>
        ${interrupted}
      </article>
    `;
  }

  private overBudgetActions(actions: AgentTimedActionOccurrence[], tickHours: number): string {
    let used = 0;
    const overflowing: string[] = [];
    for (const action of actions.filter((item) => item.mode === 'primary')) {
      used += action.hours_in_tick;
      if (used > tickHours + 0.000001) {
        overflowing.push(
          `${action.action_name} (${formatNumber(action.hours_in_tick)} h in tick; ${formatNumber(action.sampled_duration_hours)} h sampled)`,
        );
      }
    }
    return overflowing.length ? `Over-budget actions: ${overflowing.join(', ')}.` : '';
  }
}
