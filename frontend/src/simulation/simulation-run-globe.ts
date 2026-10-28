import './simulation-run-globe.css';
import {
  simulationGlobeActionIds,
  simulationGlobeDays,
  simulationGlobeFormatNumber,
  simulationGlobeFormatStatistic,
  simulationGlobePointInBounds,
  simulationGlobeRecordKey,
  simulationGlobeStatisticLabel,
  simulationGlobeStatisticValue,
  simulationGlobeViewportRequestKey,
} from './run-globe-data';
import { SimulationRunGlobeRenderer } from './simulation-run-globe-renderer';
import type {
  SimulationGlobeAggregateRecord,
  SimulationGlobeAgentPoint,
  SimulationGlobeAgentViewportRequest,
  SimulationGlobeDetailLevel,
  SimulationGlobeDiagnostics,
  SimulationGlobeEvidence,
  SimulationGlobePlaceLevel,
  SimulationGlobeSelection,
  SimulationGlobeStatistic,
  SimulationGlobeViewportBounds,
  SimulationRunGlobeOptions,
} from './run-globe-types';

const statisticOptions: Array<[SimulationGlobeStatistic, string]> = [
  ['unemployment_rate', 'Unemployment rate'],
  ['mean_income', 'Mean income'],
  ['population', 'Population'],
  ['action_rate', 'Action rate'],
];

const detailOptions: Array<[SimulationGlobeDetailLevel, string]> = [
  ['world', 'World'],
  ['country', 'Country'],
  ['city', 'City'],
  ['neighborhood', 'Neighborhood'],
];

const financeOrder = ['income', 'expenses', 'savings', 'debt'];

const element = <TagName extends keyof HTMLElementTagNameMap>(
  tagName: TagName,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[TagName] => {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const addSelectOption = (select: HTMLSelectElement, value: string, label: string): void => {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  select.append(option);
};

const titleCase = (value: string): string =>
  value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const evidenceText = (evidence: SimulationGlobeEvidence): string => {
  const uncertainty =
    evidence.uncertainty === null || evidence.uncertainty === undefined
      ? ''
      : ` · uncertainty ±${simulationGlobeFormatNumber(evidence.uncertainty * 100)} pp`;
  const date = evidence.source_date ? ` · ${evidence.source_date}` : '';
  return `${titleCase(evidence.status)} · ${evidence.source} · ${evidence.source_version}${date}${uncertainty}`;
};

export class SimulationRunGlobe {
  private records: SimulationGlobeAggregateRecord[];
  private days: number[] = [];
  private ticks: number[] = [];
  private actionIds: string[] = [];
  private statistic: SimulationGlobeStatistic;
  private actionId: string;
  private day: number;
  private tick: number;
  private readonly ticksPerDay: number;
  private detailLevel: SimulationGlobeDetailLevel = 'world';
  private selectedPlaceKey: string | null = null;
  private playbackTimer = 0;
  private agentRequestSequence = 0;
  private lastAgentRequestKey = '';
  private lastViewport?: {
    detailLevel: 'city' | 'neighborhood';
    bounds: SimulationGlobeViewportBounds;
  };
  private readonly playbackIntervalMs: number;
  private readonly root = element('section', 'simulation-run-globe');
  private readonly statisticSelect = element('select', 'simulation-run-globe-select');
  private readonly actionSelect = element('select', 'simulation-run-globe-select');
  private readonly actionControl = element('label', 'simulation-run-globe-control');
  private readonly detailSelect = element('select', 'simulation-run-globe-select');
  private readonly playButton = element('button', 'simulation-run-globe-play', 'Play');
  private readonly dayInput = element('input', 'simulation-run-globe-day');
  private readonly dayOutput = element('output', 'simulation-run-globe-day-output');
  private readonly sceneHost = element('div', 'simulation-run-globe-scene');
  private readonly legendLabel = element('strong');
  private readonly legendMinimum = element('span');
  private readonly legendMaximum = element('span');
  private readonly lodSummary = element('p', 'simulation-run-globe-lod-summary');
  private readonly detail = element('aside', 'simulation-run-globe-detail');
  private readonly liveRegion = element('p', 'simulation-run-globe-live');
  private readonly renderer: SimulationRunGlobeRenderer;
  private readonly options: SimulationRunGlobeOptions;

  constructor(
    private readonly host: HTMLElement,
    options: SimulationRunGlobeOptions,
  ) {
    this.options = options;
    this.records = this.validatedRecords(options.records);
    this.statistic = options.initial_statistic ?? 'unemployment_rate';
    this.actionIds = simulationGlobeActionIds(this.records);
    this.actionId =
      options.initial_action_id && this.actionIds.includes(options.initial_action_id)
        ? options.initial_action_id
        : (this.actionIds[0] ?? '');
    this.days = simulationGlobeDays(this.records);
    const initialDay =
      options.initial_day && this.days.includes(options.initial_day)
        ? options.initial_day
        : (this.days[0] ?? 1);
    this.ticksPerDay = Math.max(1, Math.round(options.ticks_per_day ?? 1));
    const recordedTicks = [...new Set(this.records.map((record) => record.tick))].sort(
      (left, right) => left - right,
    );
    this.ticks = options.total_ticks
      ? Array.from({ length: options.total_ticks }, (_, index) => index + 1)
      : recordedTicks;
    const initialDayTick = Math.max(
      ...this.records.filter((record) => record.day === initialDay).map((record) => record.tick),
    );
    this.tick =
      options.initial_tick && this.ticks.includes(options.initial_tick)
        ? options.initial_tick
        : initialDayTick;
    this.day = this.dayForTick(this.tick);
    this.playbackIntervalMs = Math.max(250, options.playback_interval_ms ?? 900);
    this.buildInterface();
    this.renderer = new SimulationRunGlobeRenderer(this.sceneHost, {
      place_selected: (record) => this.handlePlaceSelection(record),
      agent_selected: (agent) => this.handleAgentSelection(agent),
      detail_level_changed: (detailLevel) => this.handleDetailLevelChange(detailLevel),
      viewport_changed: (detailLevel, bounds) => this.handleViewportChange(detailLevel, bounds),
    });
    this.host.replaceChildren(this.root);
    this.bindEvents();
    this.updateControls();
    this.renderFrame();
    this.renderEmptyDetail();
  }

  private validatedRecords(
    records: readonly SimulationGlobeAggregateRecord[],
  ): SimulationGlobeAggregateRecord[] {
    if (!records.length) throw new Error('Simulation globe requires recorded aggregate statistics');
    const seen = new Set<string>();
    for (const record of records) {
      if (!Number.isInteger(record.day) || record.day < 1)
        throw new Error('Simulation globe aggregate days must be positive integers');
      if (!Number.isFinite(record.latitude) || record.latitude < -90 || record.latitude > 90)
        throw new Error(`${record.place_label} has an invalid aggregate latitude`);
      if (!Number.isFinite(record.longitude) || record.longitude < -180 || record.longitude > 180)
        throw new Error(`${record.place_label} has an invalid aggregate longitude`);
      const key = `${record.day}:${simulationGlobeRecordKey(record)}`;
      if (seen.has(key)) throw new Error(`Duplicate simulation globe aggregate ${key}`);
      seen.add(key);
    }
    return [...records];
  }

  private buildInterface(): void {
    this.root.dataset.simulationRunGlobe = '';
    const header = element('header', 'simulation-run-globe-heading');
    const headingText = element('div');
    headingText.append(
      element('span', 'simulation-run-globe-eyebrow', 'Recorded output'),
      element('h2', undefined, 'Simulation globe'),
      element(
        'p',
        undefined,
        'Explore recorded place aggregates over time. Globe values match the run statistics for the selected day.',
      ),
    );
    const dayBadge = element('div', 'simulation-run-globe-day-badge');
    dayBadge.append(element('span', undefined, 'Current time'), this.dayOutput);
    header.append(headingText, dayBadge);

    const toolbar = element('div', 'simulation-run-globe-toolbar');
    const statisticControl = this.control('Statistic', this.statisticSelect);
    this.statisticSelect.setAttribute('aria-label', 'Globe statistic');
    for (const [value, label] of statisticOptions)
      addSelectOption(this.statisticSelect, value, label);
    this.actionControl.append(element('span', undefined, 'DSL action'), this.actionSelect);
    this.actionSelect.setAttribute('aria-label', 'Action rate statistic');
    const detailControl = this.control('Map detail', this.detailSelect);
    this.detailSelect.setAttribute('aria-label', 'Map detail level');
    for (const [value, label] of detailOptions) addSelectOption(this.detailSelect, value, label);
    this.playButton.type = 'button';
    this.playButton.setAttribute('aria-label', 'Play simulation ticks');
    this.dayInput.type = 'range';
    this.dayInput.step = '1';
    this.dayInput.setAttribute('aria-label', 'Simulation tick');
    const timeline = element('label', 'simulation-run-globe-timeline');
    timeline.append(element('span', undefined, 'Tick'), this.dayInput);
    toolbar.append(statisticControl, this.actionControl, detailControl, this.playButton, timeline);

    const visualization = element('div', 'simulation-run-globe-visualization');
    const scenePanel = element('div', 'simulation-run-globe-scene-panel');
    const sceneOverlay = element('div', 'simulation-run-globe-scene-overlay');
    const legend = element('div', 'simulation-run-globe-legend');
    const gradient = element('span', 'simulation-run-globe-legend-gradient');
    const legendRange = element('span', 'simulation-run-globe-legend-range');
    legendRange.append(this.legendMinimum, this.legendMaximum);
    legend.append(this.legendLabel, gradient, legendRange);
    sceneOverlay.append(legend, this.lodSummary);
    scenePanel.append(this.sceneHost, sceneOverlay);
    this.detail.setAttribute('aria-label', 'Selected place aggregate statistics');
    visualization.append(scenePanel, this.detail);
    this.liveRegion.setAttribute('role', 'status');
    this.liveRegion.setAttribute('aria-live', 'polite');
    this.root.append(header, toolbar, visualization, this.liveRegion);
  }

  private control(label: string, control: HTMLElement): HTMLLabelElement {
    const wrapper = element('label', 'simulation-run-globe-control');
    wrapper.append(element('span', undefined, label), control);
    return wrapper;
  }

  private bindEvents(): void {
    this.statisticSelect.addEventListener('change', this.handleStatisticChange);
    this.actionSelect.addEventListener('change', this.handleActionChange);
    this.detailSelect.addEventListener('change', this.handleDetailControlChange);
    this.playButton.addEventListener('click', this.togglePlayback);
    this.dayInput.addEventListener('input', this.handleDayInput);
  }

  private updateControls(): void {
    this.statisticSelect.value = this.statistic;
    this.actionSelect.replaceChildren();
    for (const actionId of this.actionIds)
      addSelectOption(this.actionSelect, actionId, titleCase(actionId));
    this.actionSelect.value = this.actionId;
    this.actionSelect.disabled = this.actionIds.length === 0;
    this.actionControl.hidden = this.statistic !== 'action_rate';
    this.detailSelect.value = this.detailLevel;
    this.dayInput.min = '0';
    this.dayInput.max = String(Math.max(0, this.ticks.length - 1));
    this.dayInput.value = String(Math.max(0, this.ticks.indexOf(this.tick)));
    this.dayInput.disabled = this.ticks.length <= 1;
    this.playButton.disabled = this.ticks.length <= 1;
    this.playButton.textContent = this.playbackTimer ? 'Pause' : 'Play';
    this.playButton.setAttribute(
      'aria-label',
      this.playbackTimer ? 'Pause simulation ticks' : 'Play simulation ticks',
    );
    const record = this.frameRecords()[0];
    this.dayOutput.value = `Day ${this.day}${record?.date ? ` · ${record.date}` : ''} · tick ${this.tick}`;
    this.dayOutput.textContent = this.dayOutput.value;
  }

  private frameRecords(): SimulationGlobeAggregateRecord[] {
    return this.records.filter((record) => record.day === this.day);
  }

  private renderFrame(): void {
    const records = this.frameRecords();
    const values = new Map<string, number | null>();
    for (const record of records) {
      values.set(
        simulationGlobeRecordKey(record),
        simulationGlobeStatisticValue(record, this.statistic, this.actionId),
      );
    }
    this.renderer.updateAggregates(records, values);
    const finiteValues = [...values.values()].filter(
      (value): value is number => value !== null && Number.isFinite(value),
    );
    const minimum = finiteValues.length ? Math.min(...finiteValues) : null;
    const maximum = finiteValues.length ? Math.max(...finiteValues) : null;
    const incomeUnit =
      records.find((record) => record.finances.income)?.finances.income?.unit ?? '';
    this.legendLabel.textContent = simulationGlobeStatisticLabel(this.statistic, this.actionId);
    this.legendMinimum.textContent = simulationGlobeFormatStatistic(
      minimum,
      this.statistic,
      incomeUnit,
    );
    this.legendMaximum.textContent = simulationGlobeFormatStatistic(
      maximum,
      this.statistic,
      incomeUnit,
    );
    this.renderLodSummary();
    if (this.selectedPlaceKey) {
      const selected = records.find(
        (record) => simulationGlobeRecordKey(record) === this.selectedPlaceKey,
      );
      if (selected) this.renderDetail(selected);
      else this.renderEmptyDetail();
    }
    if (this.lastViewport) {
      void this.loadAgentViewport(this.lastViewport.detailLevel, this.lastViewport.bounds, true);
    }
  }

  private renderLodSummary(): void {
    const records = this.frameRecords();
    const regionCount = records.filter((record) => record.place_level === 'region').length;
    const countryCount = records.filter((record) => record.place_level === 'country').length;
    const cityCount = records.filter((record) => record.place_level === 'city').length;
    const agentCount = this.renderer?.diagnostics().displayed_agent_points ?? 0;
    this.lodSummary.textContent = `${titleCase(this.detailLevel)} detail · ${regionCount} region clusters · ${countryCount} country aggregates · ${cityCount} city aggregates${this.detailLevel === 'city' || this.detailLevel === 'neighborhood' ? ` · ${agentCount} viewport agents` : ''}`;
  }

  private handleStatisticChange = (): void => {
    this.setStatistic(this.statisticSelect.value as SimulationGlobeStatistic);
  };

  private handleActionChange = (): void => {
    this.actionId = this.actionSelect.value;
    this.renderFrame();
  };

  private handleDetailControlChange = (): void => {
    this.renderer.setDetailLevel(this.detailSelect.value as SimulationGlobeDetailLevel);
  };

  private handleDayInput = (): void => {
    const tick = this.ticks[Number(this.dayInput.value)];
    if (tick !== undefined) this.setTick(tick);
  };

  private togglePlayback = (): void => {
    if (this.playbackTimer) {
      this.pause();
      return;
    }
    this.play();
  };

  play(): void {
    if (this.playbackTimer || this.ticks.length <= 1) return;
    this.playbackTimer = window.setInterval(() => {
      const currentIndex = this.ticks.indexOf(this.tick);
      this.setTick(this.ticks[(currentIndex + 1) % this.ticks.length]!);
    }, this.playbackIntervalMs);
    this.updateControls();
  }

  pause(): void {
    if (this.playbackTimer) window.clearInterval(this.playbackTimer);
    this.playbackTimer = 0;
    this.updateControls();
  }

  setDay(day: number): void {
    if (!this.days.includes(day)) throw new Error(`Day ${day} is not present in globe aggregates`);
    const tick = Math.max(
      ...this.records.filter((record) => record.day === day).map((record) => record.tick),
    );
    this.setTick(tick);
  }

  setTick(tick: number): void {
    if (!this.ticks.includes(tick)) throw new Error(`Tick ${tick} is not recorded for this run`);
    if (this.tick === tick) return;
    const previousDay = this.day;
    this.tick = tick;
    this.day = this.dayForTick(tick);
    this.lastAgentRequestKey = '';
    this.updateControls();
    this.renderFrame();
    if (this.day !== previousDay) this.options.on_day_changed?.(this.day);
    this.options.on_tick_changed?.(tick);
    this.liveRegion.textContent = `Showing tick ${tick} with recorded day ${this.day} aggregates`;
  }

  private dayForTick(tick: number): number {
    if (this.options.total_ticks) return Math.min(this.days.at(-1) ?? 1, Math.ceil(tick / this.ticksPerDay));
    return this.records.find((record) => record.tick >= tick)?.day ?? this.days.at(-1) ?? 1;
  }

  setStatistic(statistic: SimulationGlobeStatistic, actionId?: string): void {
    this.statistic = statistic;
    if (actionId !== undefined) {
      if (!this.actionIds.includes(actionId)) throw new Error(`Action ${actionId} is not recorded`);
      this.actionId = actionId;
    }
    this.updateControls();
    this.renderFrame();
    this.liveRegion.textContent = `Globe colored by ${simulationGlobeStatisticLabel(statistic, this.actionId)}`;
  }

  setDetailLevel(detailLevel: SimulationGlobeDetailLevel): void {
    this.renderer.setDetailLevel(detailLevel);
  }

  private handleDetailLevelChange(detailLevel: SimulationGlobeDetailLevel): void {
    this.detailLevel = detailLevel;
    this.detailSelect.value = detailLevel;
    if (detailLevel !== 'city' && detailLevel !== 'neighborhood') {
      this.lastViewport = undefined;
      this.lastAgentRequestKey = '';
    }
    this.renderLodSummary();
    this.liveRegion.textContent = `${titleCase(detailLevel)} globe detail active`;
  }

  private handleViewportChange(
    detailLevel: 'city' | 'neighborhood',
    bounds: SimulationGlobeViewportBounds,
  ): void {
    this.lastViewport = { detailLevel, bounds };
    void this.loadAgentViewport(detailLevel, bounds, false);
  }

  private async loadAgentViewport(
    detailLevel: 'city' | 'neighborhood',
    bounds: SimulationGlobeViewportBounds,
    force: boolean,
  ): Promise<void> {
    if (!this.options.load_agent_points) {
      this.renderer.clearAgentPoints();
      this.renderLodSummary();
      return;
    }
    const frame = this.frameRecords();
    const firstRecord = frame[0];
    if (!firstRecord) return;
    const visibleCityIds = frame
      .filter(
        (record) =>
          record.place_level === 'city' &&
          record.latitude >= bounds.south &&
          record.latitude <= bounds.north &&
          (bounds.west <= bounds.east
            ? record.longitude >= bounds.west && record.longitude <= bounds.east
            : record.longitude >= bounds.west || record.longitude <= bounds.east),
      )
      .map((record) => record.place_id);
    const request: SimulationGlobeAgentViewportRequest = {
      run_id: firstRecord.run_id,
      day: this.day,
      tick: this.tick,
      detail_level: detailLevel,
      bounds,
      visible_city_ids: visibleCityIds,
    };
    const requestKey = simulationGlobeViewportRequestKey(request);
    if (!force && requestKey === this.lastAgentRequestKey) return;
    this.lastAgentRequestKey = requestKey;
    const sequence = ++this.agentRequestSequence;
    this.liveRegion.textContent = `Loading agents inside the ${titleCase(detailLevel)} viewport`;
    try {
      const response = await this.options.load_agent_points(request);
      if (sequence !== this.agentRequestSequence) return;
      const visibleCitySet = new Set(visibleCityIds);
      const points = response.points.filter(
        (point) =>
          simulationGlobePointInBounds(point, bounds) &&
          (!visibleCitySet.size || visibleCitySet.has(point.place_id)),
      );
      this.renderer.setAgentPoints(points);
      this.renderLodSummary();
      this.liveRegion.textContent = `${points.length} agents rendered in one GPU point cloud from ${response.total_in_bounds} viewport agents`;
    } catch (error) {
      if (sequence !== this.agentRequestSequence) return;
      this.renderer.clearAgentPoints();
      this.renderLodSummary();
      this.liveRegion.textContent = `Agent viewport could not be loaded: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  private handlePlaceSelection(record: SimulationGlobeAggregateRecord): void {
    this.selectedPlaceKey = simulationGlobeRecordKey(record);
    this.renderer.selectPlace(record.place_level, record.place_id);
    this.renderDetail(record);
    const selection: SimulationGlobeSelection = {
      level: record.place_level,
      place_id: record.place_id,
      day: this.day,
      tick: this.tick,
      record,
    };
    this.options.on_place_selected?.(selection);
    this.liveRegion.textContent = `${record.place_label} selected for day ${this.day}`;
  }

  private handleAgentSelection(agent: SimulationGlobeAgentPoint): void {
    this.options.on_agent_selected?.(agent);
    this.liveRegion.textContent = `${agent.agent_id} selected · ${titleCase(agent.state)}`;
  }

  selectPlace(level: SimulationGlobePlaceLevel, placeId: string): void {
    const record = this.frameRecords().find(
      (item) => item.place_level === level && item.place_id === placeId,
    );
    if (!record) throw new Error(`${level} ${placeId} is not present on day ${this.day}`);
    this.handlePlaceSelection(record);
  }

  focusPlace(
    level: SimulationGlobePlaceLevel,
    placeId: string,
    detailLevel?: SimulationGlobeDetailLevel,
  ): void {
    const record = this.frameRecords().find(
      (item) => item.place_level === level && item.place_id === placeId,
    );
    if (!record) throw new Error(`${level} ${placeId} is not present on day ${this.day}`);
    this.handlePlaceSelection(record);
    this.renderer.focus(record, detailLevel);
  }

  private renderEmptyDetail(): void {
    this.detail.replaceChildren();
    const empty = element('div', 'simulation-run-globe-detail-empty');
    empty.append(
      element('span', 'simulation-run-globe-eyebrow', 'Place details'),
      element('h3', undefined, 'Select a place on the globe'),
      element(
        'p',
        undefined,
        'Country and region selections show finances, employment, population, type mix, action rates, and their evidence status for this recorded day.',
      ),
    );
    this.detail.append(empty);
  }

  private renderDetail(record: SimulationGlobeAggregateRecord): void {
    this.detail.replaceChildren();
    const header = element('header', 'simulation-run-globe-detail-heading');
    header.append(
      element('span', 'simulation-run-globe-eyebrow', titleCase(record.place_level)),
      element('h3', undefined, record.place_label),
      element('p', undefined, `Day ${record.day} · ${record.date} · tick ${record.tick}`),
    );
    this.detail.append(header);
    const overview = element('section', 'simulation-run-globe-detail-section');
    overview.append(element('h4', undefined, 'Population and employment'));
    const overviewGrid = element('div', 'simulation-run-globe-stat-grid');
    overviewGrid.append(
      this.statCard(
        'Population',
        simulationGlobeFormatNumber(record.population),
        evidenceText(record.evidence.population),
        record.evidence.population.status,
      ),
      this.statCard(
        'Agents',
        simulationGlobeFormatNumber(record.agent_count),
        evidenceText(record.evidence.agent_type_mix),
        record.evidence.agent_type_mix.status,
      ),
    );
    if (record.employment) {
      overviewGrid.append(
        this.statCard(
          'Unemployment',
          `${simulationGlobeFormatNumber(record.employment.unemployment_rate * 100)}%`,
          `${simulationGlobeFormatNumber(record.employment.unemployed)} unemployed of ${simulationGlobeFormatNumber(record.employment.labour_force)} in the labour force · ${evidenceText(record.evidence.employment)}`,
          record.evidence.employment.status,
        ),
        this.statCard(
          'Employment',
          simulationGlobeFormatNumber(record.employment.employed),
          `Student ${simulationGlobeFormatNumber(record.employment.student_share * 100)}% · caregiver ${simulationGlobeFormatNumber(record.employment.caregiver_share * 100)}% · retired ${simulationGlobeFormatNumber(record.employment.retired_share * 100)}% · worker ${simulationGlobeFormatNumber(record.employment.worker_share * 100)}%`,
          record.evidence.employment.status,
        ),
      );
    }
    overview.append(overviewGrid);
    this.detail.append(overview);

    const finances = element('section', 'simulation-run-globe-detail-section');
    finances.append(element('h4', undefined, 'Finances'));
    const financeGrid = element('div', 'simulation-run-globe-stat-grid');
    for (const metricId of financeOrder) {
      const metric = record.finances[metricId];
      if (!metric) continue;
      const mean = metric.mean === null ? 'Unavailable' : simulationGlobeFormatNumber(metric.mean);
      const median =
        metric.median === null ? 'Unavailable' : simulationGlobeFormatNumber(metric.median);
      const total =
        metric.total === null ? 'Unavailable' : simulationGlobeFormatNumber(metric.total);
      financeGrid.append(
        this.statCard(
          titleCase(metricId),
          `${mean} ${metric.unit}`.trim(),
          `Mean · median ${median} · total ${total} · ${metric.basis} · ${metric.observations} observations · ${metric.source_ids.join(', ')}`,
          metric.evidence_status,
        ),
      );
    }
    finances.append(financeGrid);
    this.detail.append(finances);

    const types = element('section', 'simulation-run-globe-detail-section');
    types.append(element('h4', undefined, 'Agent type mix'));
    const typeList = element('div', 'simulation-run-globe-bars');
    for (const [agentType, share] of Object.entries(record.agent_type_shares).sort(
      ([left], [right]) => left.localeCompare(right),
    )) {
      const row = element('div', 'simulation-run-globe-bar');
      const labels = element('div');
      labels.append(
        element('span', undefined, titleCase(agentType)),
        element(
          'strong',
          undefined,
          `${simulationGlobeFormatNumber(share * 100)}% · ${simulationGlobeFormatNumber(record.agent_type_counts[agentType] ?? 0)}`,
        ),
      );
      const track = element('span', 'simulation-run-globe-bar-track');
      const fill = element('span', 'simulation-run-globe-bar-fill');
      fill.style.width = `${Math.max(0, Math.min(100, share * 100))}%`;
      track.append(fill);
      row.append(labels, track);
      typeList.append(row);
    }
    types.append(typeList, this.evidenceLine(record.evidence.agent_type_mix));
    this.detail.append(types);

    const actions = element('section', 'simulation-run-globe-detail-section');
    actions.append(element('h4', undefined, 'Action rates'));
    const actionList = element('dl', 'simulation-run-globe-action-list');
    for (const [actionId, rate] of Object.entries(record.action_rates_per_1000).sort(
      ([left], [right]) => left.localeCompare(right),
    )) {
      actionList.append(
        element('dt', undefined, titleCase(actionId)),
        element(
          'dd',
          undefined,
          `${simulationGlobeFormatNumber(rate)} per 1,000 · ${simulationGlobeFormatNumber(record.action_counts[actionId] ?? 0)} actions`,
        ),
      );
    }
    if (!Object.keys(record.action_rates_per_1000).length)
      actionList.append(
        element('dt', undefined, 'No actions'),
        element('dd', undefined, '0 recorded'),
      );
    actions.append(actionList, this.evidenceLine(record.evidence.action_rates));
    this.detail.append(actions);
  }

  private statCard(
    label: string,
    value: string,
    context: string,
    status: 'measured' | 'estimated',
  ): HTMLElement {
    const card = element('article', 'simulation-run-globe-stat');
    const heading = element('div');
    heading.append(
      element('span', undefined, label),
      element('span', `simulation-run-globe-evidence ${status}`, titleCase(status)),
    );
    card.append(heading, element('strong', undefined, value), element('p', undefined, context));
    return card;
  }

  private evidenceLine(evidence: SimulationGlobeEvidence): HTMLElement {
    const line = element('p', 'simulation-run-globe-evidence-line');
    line.append(
      element(
        'span',
        `simulation-run-globe-evidence ${evidence.status}`,
        titleCase(evidence.status),
      ),
      document.createTextNode(evidenceText(evidence).replace(/^\w+ · /, '')),
    );
    return line;
  }

  setRecords(records: readonly SimulationGlobeAggregateRecord[]): void {
    this.pause();
    this.records = this.validatedRecords(records);
    this.days = simulationGlobeDays(this.records);
    const recordedTicks = [...new Set(this.records.map((record) => record.tick))].sort(
      (left, right) => left - right,
    );
    this.ticks = this.options.total_ticks
      ? Array.from({ length: this.options.total_ticks }, (_, index) => index + 1)
      : recordedTicks;
    this.actionIds = simulationGlobeActionIds(this.records);
    if (!this.days.includes(this.day)) this.day = this.days[0]!;
    if (!this.ticks.includes(this.tick)) this.tick = this.ticks[0]!;
    this.day = this.dayForTick(this.tick);
    if (!this.actionIds.includes(this.actionId)) this.actionId = this.actionIds[0] ?? '';
    this.lastAgentRequestKey = '';
    this.updateControls();
    this.renderFrame();
  }

  setVisible(visible: boolean): void {
    this.renderer.setVisible(visible);
    if (!visible) this.pause();
  }

  diagnostics(): SimulationGlobeDiagnostics {
    return this.renderer.diagnostics();
  }

  dispose(): void {
    this.pause();
    this.agentRequestSequence += 1;
    this.statisticSelect.removeEventListener('change', this.handleStatisticChange);
    this.actionSelect.removeEventListener('change', this.handleActionChange);
    this.detailSelect.removeEventListener('change', this.handleDetailControlChange);
    this.playButton.removeEventListener('click', this.togglePlayback);
    this.dayInput.removeEventListener('input', this.handleDayInput);
    this.renderer.dispose();
    this.root.remove();
  }
}

export type {
  SimulationGlobeAggregateRecord,
  SimulationGlobeAgentPoint,
  SimulationGlobeAgentViewportRequest,
  SimulationGlobeAgentViewportResponse,
  SimulationGlobeDetailLevel,
  SimulationGlobeDiagnostics,
  SimulationGlobeEvidence,
  SimulationGlobeFinanceStatistic,
  SimulationGlobeSelection,
  SimulationGlobeStatistic,
  SimulationRunGlobeOptions,
} from './run-globe-types';
export {
  simulationGlobeRecordsFromRunStatistics,
  type SimulationGlobePlaceMetadata,
  type SimulationRunAggregateApiRecord,
} from './run-globe-adapter';
