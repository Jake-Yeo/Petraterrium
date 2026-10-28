import type { GraphNode, ProgramGraph } from './dsl-graph-view';

interface OutlineOptions {
  onSelect: (line: number) => void;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const label = (value: string): string =>
  value.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');

export class DslOutline {
  private graph?: ProgramGraph;
  private search = '';

  constructor(
    private readonly host: HTMLElement,
    private readonly options: OutlineOptions,
  ) {
    this.host.className = 'dsl-outline';
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('click', this.onClick);
  }

  destroy(): void {
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('click', this.onClick);
  }

  setGraph(graph?: ProgramGraph | null): void {
    this.graph = graph ?? undefined;
    this.render();
  }

  private render(): void {
    const query = this.search.trim().toLowerCase();
    const nodes = (this.graph?.nodes ?? []).filter((node) =>
      [node.id, node.level, node.vertical_slice, ...node.roles_exposed.map((role) => role.id)]
        .join(' ')
        .toLowerCase()
        .includes(query),
    );
    const slices = new Map<string, Map<string, GraphNode[]>>();
    for (const node of nodes) {
      const levels = slices.get(node.vertical_slice) ?? new Map<string, GraphNode[]>();
      const values = levels.get(node.level) ?? [];
      values.push(node);
      levels.set(node.level, values);
      slices.set(node.vertical_slice, levels);
    }
    this.host.innerHTML = `<header><strong>Outline</strong><input type="search" value="${escapeHtml(this.search)}" placeholder="Find block or role" aria-label="Search DSL outline"></header><div>${
      slices.size
        ? [...slices]
            .map(
              ([slice, levels]) =>
                `<details open><summary>${escapeHtml(label(slice))}</summary>${[...levels]
                  .map(
                    ([level, values]) =>
                      `<details${query ? ' open' : ''}><summary>${escapeHtml(label(level))} · ${values.length}</summary>${values
                        .sort((left, right) => left.line - right.line)
                        .map(
                          (node) =>
                            `<button type="button" data-outline-line="${node.line}"><span>${escapeHtml(node.id)}</span><small>${escapeHtml(label(node.level))} · ${node.roles_exposed.length} role${node.roles_exposed.length === 1 ? '' : 's'}</small></button>`,
                        )
                        .join('')}</details>`,
                  )
                  .join('')}</details>`,
            )
            .join('')
        : '<p>No matching DSL blocks.</p>'
    }</div>`;
  }

  private readonly onInput = (event: Event): void => {
    const input = (event.target as Element).closest<HTMLInputElement>('input');
    if (!input) return;
    this.search = input.value;
    this.render();
    this.host.querySelector<HTMLInputElement>('input')?.focus();
  };

  private readonly onClick = (event: MouseEvent): void => {
    const button = (event.target as Element).closest<HTMLButtonElement>('[data-outline-line]');
    if (button) this.options.onSelect(Number(button.dataset.outlineLine));
  };
}
