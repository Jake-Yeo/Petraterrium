import type {
  ImportPreview,
  RunSummary,
  SourceCatalog,
  ValidationReport,
} from '../contracts.generated';
import { escapeHtml as e, scenarioLabel } from '../views';
import { labels } from './views';
const n = (value: number): string => value.toLocaleString('en');

export function importForm(
  runs: RunSummary[],
  sources: SourceCatalog,
  activeId?: string,
  sourceId = '',
): string {
  const options = runs
    .map(
      (run) =>
        `
    <option value="${run.run_id}" ${run.run_id === activeId ? 'selected' : ''}>
      ${e(scenarioLabel(run.config.scenario))} #${run.config.seed} · ${run.run_id.slice(0, 8)}
    </option>
  `,
    )
    .join('');
  return `
    <form id="atlas-import-form">
      <div class="atlas-form-grid">
        <label
          >Run scope<select name="run_id" required>
            ${options || '<option value="">Create a run first</option>'}
          </select></label
        ><label
          >Data kind<select name="kind">
            <option value="marginals">Marginals</option>
            <option value="behaviour">Behaviour survey</option>
            <option value="population">Population grid/density</option>
          </select></label
        ><label
          >Source loader<select name="source_id">
            <option value="">User upload / canonical schema</option>
            ${sources.sources.map((source) => `<option value="${source.source_id}" ${source.source_id === sourceId ? 'selected' : ''}>${e(source.name)}</option>`).join('')}
          </select></label
        ><label
          >Source label<input name="source" required placeholder="Survey or publication title" /></label
        ><label>Data date<input name="source_date" type="date" required /></label
        ><label>Publication date<input name="published_date" type="date" required /></label
        ><label
          >Source version<input
            name="version"
            required
            placeholder="Release / wave / revision" /></label
        ><label>Uploader<input name="uploader" value="local-user" required /></label
        ><label
          >Country ISO code, if absent in file<input
            name="country_code"
            placeholder="e.g. IT"
            maxlength="3" /></label
        ><label
          >Units<input name="unit" value="percent" list="atlas-units" /><datalist id="atlas-units">
            <option>percent</option>
            <option>USD/year</option>
            <option>persons_per_cell</option>
            <option>persons_per_km2</option>
          </datalist></label
        >
      </div>
      <label class="atlas-file-input"
        >Data file<input name="file" type="file" accept=".csv,.parquet,.json,.csv.gz,.zip,.tif,.tiff"
      /></label>
      <details class="atlas-source-url">
        <summary>Or load a source download URL</summary>
        <label
          >Approved source HTTPS URL<input
            name="source_url"
            type="url"
            placeholder="https://…" /></label
        ><label class="atlas-checkbox"
          ><input name="access_confirmed" type="checkbox" />I have access rights for this source.</label
        >
      </details>
      <label class="atlas-checkbox"
        ><input name="use_llm" type="checkbox" ${sources.llm_available ? 'checked' : ''} />Propose mappings with an LLM
        using headers and five sample rows${sources.llm_available ? '' : ' (API key not configured)'}</label
      ><label class="atlas-checkbox"
        ><input name="redistribution_allowed" type="checkbox" />This source allows redistribution. Keep
        unchecked for restricted microdata.</label
      >
      <p class="field-hint">
        Distribution values use percentages totaling 100. Use JSON objects or dotted columns such as
        age_sex.female_0_14. A mean income needs explicit currency/time units. Ambiguous columns must be
        resolved or explicitly ignored.
      </p>
      <p id="atlas-import-error" class="form-error" role="alert" hidden></p>
      <div class="dialog-footer">
        <button type="button" class="button secondary" data-atlas-action="close-import">Cancel</button
        ><button class="button primary" type="submit" ${runs.length ? '' : 'disabled'}>Preview & map</button>
      </div>
    </form>
  `;
}

export function mappingView(preview: ImportPreview): string {
  return `
    <p class="atlas-detail-note">
      ${e(preview.filename)} · ${n(preview.row_count)} rows · run ${preview.metadata.run_id.slice(0, 10)}<br />${e(preview.mapping_audit.message)}<br />Mapper:
      ${e(preview.mapping_audit.model)} · prompt ${e(preview.mapping_audit.prompt_version)} · estimated cost ${preview.mapping_audit.estimated_cost_usd === null ? 'unavailable' : '$' + preview.mapping_audit.estimated_cost_usd.toFixed(6)}
    </p>
    ${preview.metadata.processing_notes.map((note) => `<p class="atlas-detail-note">${e(note)}</p>`).join('')}
    <details>
      <summary>Five-row sample</summary>
      <pre class="atlas-sample">${e(JSON.stringify(preview.sample_rows, null, 2))}</pre>
    </details>
    <h3>Confirm every column</h3>
    <div class="table-scroll">
      <table class="atlas-mapping">
        <thead>
          <tr>
            <th>Uploaded column</th>
            <th>Canonical target</th>
            <th>Review</th>
          </tr>
        </thead>
        <tbody>
          ${preview.mappings.map((mapping, index) => `<tr><th>${e(mapping.column)}</th><td><input data-mapping-index="${index}" value="${e(mapping.ambiguous ? '?' : (mapping.target ?? ''))}" list="atlas-targets" aria-label="Map ${e(mapping.column)}" /></td><td>${mapping.ambiguous ? '<span class="field-status imputed">Ambiguous</span>' : 'Proposed'}<small>${e(mapping.reason)}</small></td></tr>`).join('')}
        </tbody>
      </table>
    </div>
    <datalist id="atlas-targets">${['geonameid', 'city', 'country_code', 'admin1', 'admin2', ...Object.keys(labels), 'unit', 'behaviour', 'outcome', 'survey_weight', 'observation_date', 'density_per_km2', 'trait.age', 'trait.income'].map((target) => `<option value="${target}"></option>`).join('')}</datalist>
    <p class="field-hint">
      Replace ? with the intended target, or clear it to explicitly ignore the column. No data is
      committed at this step.
    </p>
    <label class="atlas-checkbox"
      ><input id="atlas-mapping-confirmed" type="checkbox" />I reviewed the mappings, including units
      and geography.</label
    >
    <p id="atlas-import-error" class="form-error" role="alert" hidden></p>
    <div id="atlas-validation"></div>
    <div class="dialog-footer">
      <button class="button secondary" data-atlas-action="restart-import">Back</button
      ><button class="button primary" data-atlas-action="validate">Validate confirmed mapping</button
      ><button id="atlas-commit-button" class="button primary" data-atlas-action="commit" disabled>
        Commit to this run
      </button>
    </div>
  `;
}

export function validationView(report: ValidationReport): string {
  return `
    <div class="atlas-validation ${report.valid ? 'valid' : 'invalid'}">
      <h3>${report.valid ? 'Validation passed' : 'Write blocked'}</h3>
      <p>
        ${n(report.total_rows)} rows · ${n(report.observations)} usable observations · ${n(report.issues.length)}
        errors
      </p>
      ${report.issues.length ? `<div class="atlas-issues">${report.issues.map((issue) => `<p>Row ${issue.row} · ${e(issue.field)}: ${e(issue.message)}</p>`).join('')}</div>` : ''}
      <p>Missing values by field: ${Object.entries(report.missingness)
        .map(([field, count]) => `${labels[field] ?? field}: ${n(count)}`)
        .join(' · ')}</p>
    </div>
  `;
}
