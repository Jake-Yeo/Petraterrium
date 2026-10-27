import './feature_styles.css';
import type { AtlasOverview, FieldCoverage } from '../contracts.generated';
import { escapeHtml as e } from '../views';

export interface FeatureDraft {
  id: string;
  name: string;
  label: string;
  kind: 'continuous' | 'categorical' | 'binary';
  definition: string;
  unit: string;
  minimum: string;
  maximum: string;
  categories: string[];
  coverageLevel: 'country' | 'city' | 'individual';
  outcomes: string[];
  createdAt: string;
}

interface FieldGuide {
  label: string;
  measure: string;
  columns: string;
  sources: string;
}

const STORAGE_KEY = 'petraterrium-feature-drafts-v2';
const LEGACY_STORAGE_KEY = 'petraterrium-feature-proposals-v1';
const ORDER = ['age_sex', 'income', 'education', 'ideology', 'household_size'];

const GUIDES: Record<string, FieldGuide> = {
  age_sex: {
    label: 'Age & sex',
    measure: 'Population share by age band and sex',
    columns: 'country_code or geonameid, age_band, sex, percent, reference_date',
    sources: 'National census, IPUMS, UN World Population Prospects',
  },
  income: {
    label: 'Income',
    measure: 'Household or personal income distribution in a defined currency and period',
    columns:
      'country_code or geonameid, income_band, percent, currency, income_period, reference_date',
    sources: 'National statistics office, IPUMS, household income survey',
  },
  education: {
    label: 'Education',
    measure: 'Population share by harmonized attainment level',
    columns: 'country_code or geonameid, isced_level, percent, reference_date',
    sources: 'National census, IPUMS, UNESCO Institute for Statistics',
  },
  ideology: {
    label: 'Ideology',
    measure: 'Weighted distribution on a documented ideology or party-alignment scale',
    columns:
      'country_code or geonameid, scale_name, response_value, percent, survey_weight, reference_date',
    sources: 'WVS, ESS, Pew, national election studies, official local election results',
  },
  household_size: {
    label: 'Household size',
    measure: 'Mean household size or household-size distribution',
    columns: 'country_code or geonameid, household_size, percent, reference_date',
    sources: 'National census, IPUMS, DHS, UN Household Size and Composition',
  },
};

const formatCount = (value: number): string => value.toLocaleString('en');
const formatPercent = (value: number): string => `${value.toFixed(1)}%`;

function guideFor(field: FieldCoverage): FieldGuide {
  return GUIDES[field.field];
}

function coverageStatus(field: FieldCoverage): string {
  if (field.missing === 0 && field.imputed === 0 && field.inherited === 0) return 'Complete direct';
  if (field.missing === 0) return 'No unresolved cities';
  return `${formatCount(field.missing)} unresolved`;
}

function statusWidth(count: number, total: number): string {
  return `${total ? (count / total) * 100 : 0}%`;
}

export function plannerSection(): string {
  return `
    <section class="atlas-section atlas-evidence-section" id="atlas-features" aria-labelledby="atlas-features-title">
      <div class="atlas-section-heading">
        <div>
          <p class="eyebrow">FIELD INVENTORY</p>
          <h2 id="atlas-features-title">What the atlas knows</h2>
          <p>Direct observations, inherited country archetypes, estimates, and unresolved gaps remain separate.</p>
        </div>
        <button class="button primary" data-atlas-action="add-feature">Add agent feature</button>
      </div>
      <div class="atlas-coverage-legend" aria-label="Coverage status legend">
        <span><i class="present"></i>Direct</span><span><i class="inherited"></i>Inherited</span><span><i class="imputed"></i>Imputed</span><span><i class="missing"></i>Missing</span>
      </div>
      <div id="atlas-feature-grid" class="atlas-feature-grid"><p class="muted">Loading…</p></div>
      <div id="atlas-priorities"><p class="muted">Loading…</p></div>
      <div class="atlas-draft-heading">
        <div><p class="eyebrow">CUSTOM FEATURES</p><h3>Feature data plans</h3></div>
        <span>Drafts stay label-only until validated distributions are supported and attached.</span>
      </div>
      <div id="atlas-feature-drafts"></div>
    </section>
    <dialog id="atlas-feature-dialog" class="atlas-dialog atlas-feature-dialog" aria-labelledby="atlas-feature-title">
      <div class="dialog-top">
        <span class="small-label">FEATURE EVIDENCE PLAN</span>
        <button class="icon-button" data-atlas-action="close-feature" aria-label="Close feature planner">×</button>
      </div>
      <h2 id="atlas-feature-title">Add agent feature</h2>
      <p class="dialog-subtitle">Define the measurement first. This creates collection templates and keeps the feature label-only; it does not invent a distribution or coefficient.</p>
      <div id="atlas-feature-body"></div>
    </dialog>
  `;
}

export function featureGrid(view: AtlasOverview): string {
  return view.summary.fields
    .slice()
    .sort((a, b) => ORDER.indexOf(a.field) - ORDER.indexOf(b.field))
    .map((field) => {
      const total = field.present + field.inherited + field.imputed + field.missing;
      const guide = guideFor(field);
      return `
        <article class="atlas-feature-card">
          <div class="atlas-feature-card-top">
            <div><strong>${e(guide.label)}</strong><span>${e(guide.measure)}</span></div>
            <span class="atlas-coverage-state">${e(coverageStatus(field))}</span>
          </div>
          <div class="atlas-coverage-bar" role="img" aria-label="${e(guide.label)} coverage: ${formatCount(field.present)} direct, ${formatCount(field.inherited)} inherited, ${formatCount(field.imputed)} imputed, ${formatCount(field.missing)} missing">
            <i class="present" style="width:${statusWidth(field.present, total)}"></i><i class="inherited" style="width:${statusWidth(field.inherited, total)}"></i><i class="imputed" style="width:${statusWidth(field.imputed, total)}"></i><i class="missing" style="width:${statusWidth(field.missing, total)}"></i>
          </div>
          <dl class="atlas-feature-stats">
            <div><dt>Direct</dt><dd>${formatCount(field.present)}<small> / ${formatPercent(field.direct_percent)}</small></dd></div>
            <div><dt>Inherited</dt><dd>${formatCount(field.inherited)}</dd></div>
            <div><dt>Imputed</dt><dd>${formatCount(field.imputed)}</dd></div>
            <div><dt>Missing</dt><dd>${formatCount(field.missing)}</dd></div>
          </dl>
          <p>Population covered: ${formatPercent(field.direct_population_percent)} direct · ${formatPercent(field.direct_plus_inherited_population_percent)} incl. inherited</p>
          <button class="text-button" data-atlas-action="filter-feature" data-field="${field.field}">View unresolved cities →</button>
        </article>`;
    })
    .join('');
}

export function priorityList(view: AtlasOverview): string {
  const ranked = view.summary.fields
    .map((field) => ({
      field,
      missingPopulation: Math.max(
        0,
        100 - field.direct_plus_inherited_population_percent - field.imputed_population_percent,
      ),
    }))
    .sort((a, b) => b.missingPopulation - a.missingPopulation || b.field.missing - a.field.missing);
  return `
    <section class="atlas-priority-panel" aria-labelledby="atlas-priority-title">
      <div class="atlas-priority-heading">
        <div><p class="eyebrow">COLLECTION QUEUE</p><h3 id="atlas-priority-title">Data needed</h3></div>
        <p>Ranked by unresolved population share, then missing city count.</p>
      </div>
      <div class="atlas-priority-list">
        ${ranked
          .map(({ field, missingPopulation }, index) => {
            const guide = guideFor(field);
            return `
              <article class="atlas-priority-row">
                <span class="atlas-priority-rank">${index + 1}</span>
                <div class="atlas-priority-name"><strong>${e(guide.label)}</strong><span>${formatPercent(missingPopulation)} of listed population unresolved · ${formatCount(field.missing)} cities missing</span></div>
                <div><small>Required columns</small><span class="mono">${e(guide.columns)}</span></div>
                <div><small>Look for</small><span>${e(guide.sources)}</span></div>
                <button class="button secondary" data-atlas-action="filter-feature" data-field="${field.field}">View gaps</button>
              </article>`;
          })
          .join('')}
      </div>
      <p class="atlas-priority-note">Behaviour models require individual records containing a trait and an outcome in the same rows. ${formatCount(view.summary.countries_with_fitted_behaviour)} countries currently have at least one fitted model.</p>
    </section>`;
}

export function featureForm(): string {
  return `
    <form id="atlas-feature-form">
      <div class="atlas-form-grid">
        <label>Display label<input name="label" required placeholder="Endurance" maxlength="80" /></label>
        <label>Feature key<input name="name" required placeholder="endurance" maxlength="60" autocomplete="off" /><small>Lowercase snake_case; stored as trait.&lt;key&gt;.</small></label>
        <label>Value type<select name="kind">
          <option value="continuous">Continuous number</option>
          <option value="categorical">Categories</option>
          <option value="binary">Yes / no</option>
        </select></label>
        <label>Smallest useful geography<select name="coverage_level">
          <option value="country">Country</option>
          <option value="city">City</option>
          <option value="individual">Individual records</option>
        </select></label>
      </div>
      <label class="atlas-notes-label">Measurement definition<textarea name="definition" required rows="3" maxlength="500" placeholder="What is measured, with which instrument and reference period?"></textarea></label>
      <div class="atlas-form-grid atlas-kind-fields" data-kind-fields="continuous">
        <label>Unit<input name="unit" placeholder="score" maxlength="40" /></label>
        <div class="atlas-range-fields"><label>Minimum<input name="minimum" inputmode="decimal" placeholder="0" /></label><label>Maximum<input name="maximum" inputmode="decimal" placeholder="100" /></label></div>
      </div>
      <label class="atlas-notes-label" data-kind-fields="categorical" hidden>Allowed categories<input name="categories" placeholder="low, medium, high" maxlength="300" /><small>Use stable labels that can be harmonized across sources.</small></label>
      <label class="atlas-notes-label">Outcomes to fit later <input name="outcomes" placeholder="evacuate, finish_race" maxlength="300" /><small>Optional snake_case outcome keys. Each coefficient still needs held-out validation.</small></label>
      <div class="atlas-evidence-gate">
        <strong>What changes after you create this plan</strong>
        <div><span>1</span><p><b>Distribution</b> tells the population generator how common each value is by geography.</p></div>
        <div><span>2</span><p><b>Joint trait + outcome rows</b> can fit a separate coefficient for each named outcome.</p></div>
        <div><span>3</span><p>The feature remains <b>label-only</b> until evidence is validated and attached.</p></div>
      </div>
      <p id="atlas-feature-error" class="form-error" role="alert" hidden></p>
      <div class="dialog-footer">
        <button type="button" class="button secondary" data-atlas-action="close-feature">Cancel</button>
        <button class="button primary" type="submit">Create data plan</button>
      </div>
    </form>
  `;
}

export function traitColumn(draft: FeatureDraft): string {
  return `trait.${draft.name}`;
}

function distributionColumns(draft: FeatureDraft): string[] {
  const geography =
    draft.coverageLevel === 'city' ? ['geonameid', 'country_code'] : ['country_code'];
  if (draft.coverageLevel === 'individual') {
    return [...geography, traitColumn(draft), 'survey_weight', 'observation_date'];
  }
  if (draft.kind === 'continuous') {
    return [
      ...geography,
      `${draft.name}_band_min`,
      `${draft.name}_band_max`,
      'percent',
      'observation_date',
    ];
  }
  return [...geography, traitColumn(draft), 'percent', 'observation_date'];
}

export function distributionTemplate(draft: FeatureDraft): string {
  return `${distributionColumns(draft).join(',')}\n`;
}

export function jointTemplate(draft: FeatureDraft): string {
  return `country_code,geonameid,${traitColumn(draft)},behaviour,outcome,survey_weight,observation_date\n`;
}

function measurementSummary(draft: FeatureDraft): string {
  if (draft.kind === 'continuous') return `${draft.minimum}–${draft.maximum} ${draft.unit}`;
  if (draft.kind === 'binary') return 'yes / no';
  return draft.categories.join(' · ');
}

export function featureDraftCards(drafts: FeatureDraft[]): string {
  if (!drafts.length) {
    return '<p class="atlas-empty">No custom feature plans yet. Add one when the model needs a measured trait that is not in the atlas.</p>';
  }
  return drafts
    .map((draft) => {
      const outcomes = draft.outcomes.length ? draft.outcomes.join(', ') : 'No outcomes named yet';
      return `
        <article class="atlas-feature-draft" data-feature-draft="${e(draft.id)}">
          <div class="atlas-draft-top">
            <div><strong>${e(draft.label)}</strong><span class="mono">${e(traitColumn(draft))} · ${e(draft.kind)} · ${e(draft.coverageLevel)}</span></div>
            <span class="field-status missing">Label-only</span>
          </div>
          <p>${e(draft.definition)}</p>
          <dl class="atlas-draft-facts">
            <div><dt>Values</dt><dd>${e(measurementSummary(draft))}</dd></div>
            <div><dt>Possible outcomes</dt><dd>${e(outcomes)}</dd></div>
          </dl>
          <div class="atlas-evidence-requirements">
            <div><span class="field-status missing">Distribution missing</span><p><b>Collect:</b> <span class="mono">${e(distributionColumns(draft).join(', '))}</span></p><small>Use one source version and document the sampling frame, date, geography, weights, and missingness.</small></div>
            <div><span class="field-status missing">${draft.outcomes.length ? 'Joint data missing' : 'Joint data not planned'}</span><p><b>To fit effects:</b> collect the trait and outcome in the same rows, with <span class="mono">behaviour, outcome, survey_weight</span>.</p><small>A different outcome requires its own fitted and held-out-tested coefficient.</small></div>
          </div>
          <div class="atlas-draft-actions">
            <button class="button secondary" data-atlas-action="download-distribution" data-id="${e(draft.id)}">Distribution CSV</button>
            <button class="button secondary" data-atlas-action="download-joint" data-id="${e(draft.id)}">Joint-data CSV</button>
            <button class="button secondary" data-atlas-action="import-for-feature" data-id="${e(draft.id)}">Import joint data…</button>
            <button class="text-button danger" data-atlas-action="delete-feature" data-id="${e(draft.id)}">Delete draft</button>
          </div>
        </article>`;
    })
    .join('');
}

function validDraft(value: unknown): value is FeatureDraft {
  if (!value || typeof value !== 'object') return false;
  const draft = value as Partial<FeatureDraft>;
  return (
    typeof draft.id === 'string' &&
    typeof draft.name === 'string' &&
    /^[a-z][a-z0-9_]*$/.test(draft.name) &&
    typeof draft.label === 'string' &&
    typeof draft.definition === 'string' &&
    typeof draft.unit === 'string' &&
    typeof draft.minimum === 'string' &&
    typeof draft.maximum === 'string' &&
    (draft.kind === 'continuous' || draft.kind === 'categorical' || draft.kind === 'binary') &&
    (draft.coverageLevel === 'country' ||
      draft.coverageLevel === 'city' ||
      draft.coverageLevel === 'individual') &&
    Array.isArray(draft.categories) &&
    draft.categories.every((category) => typeof category === 'string') &&
    Array.isArray(draft.outcomes) &&
    draft.outcomes.every((outcome) => typeof outcome === 'string')
  );
}

function migrateLegacy(): FeatureDraft[] {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Array<Record<string, unknown>>) : [];
    if (!Array.isArray(parsed)) return [];
    const migrated = parsed
      .filter((value) => typeof value.name === 'string' && /^[a-z][a-z0-9_]*$/.test(value.name))
      .map((value): FeatureDraft => {
        const kind: FeatureDraft['kind'] =
          value.kind === 'categorical' || value.kind === 'binary' ? value.kind : 'continuous';
        return {
          id: String(value.id ?? `feature-${Date.now()}`),
          name: String(value.name),
          label: String(value.label ?? value.name),
          kind,
          definition: String(value.notes ?? 'Definition required before collection.'),
          unit: '',
          minimum: String(value.minimum ?? ''),
          maximum: String(value.maximum ?? ''),
          categories: [],
          coverageLevel: 'country',
          outcomes: Array.isArray(value.usedBy) ? value.usedBy.map(String) : [],
          createdAt: String(value.createdAt ?? new Date().toISOString()),
        };
      });
    if (migrated.length) saveFeatureDrafts(migrated);
    localStorage.removeItem(LEGACY_STORAGE_KEY);
    return migrated;
  } catch {
    return [];
  }
}

export function loadFeatureDrafts(): FeatureDraft[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return migrateLegacy();
    const parsed = JSON.parse(raw) as unknown[];
    return Array.isArray(parsed) ? parsed.filter(validDraft) : [];
  } catch {
    return [];
  }
}

export function saveFeatureDrafts(drafts: FeatureDraft[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
}
