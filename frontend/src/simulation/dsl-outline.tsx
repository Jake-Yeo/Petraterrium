import { useMemo, useState, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { GraphNode, ProgramGraph } from './dsl-graph-view';

interface OutlineOptions {
  onSelect: (line: number) => void;
}

const label = (value: string): string =>
  value.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');

const OutlineComponent = ({
  graph,
  onSelect,
}: {
  graph?: ProgramGraph;
  onSelect: (line: number) => void;
}): ReactNode => {
  const [query, setQuery] = useState('');
  const slices = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const nodes = (graph?.nodes ?? []).filter((node) =>
      [node.id, node.level, node.vertical_slice, ...node.roles_exposed.map((role) => role.id)]
        .join(' ')
        .toLowerCase()
        .includes(normalized),
    );
    const grouped = new Map<string, Map<string, GraphNode[]>>();
    for (const node of nodes) {
      const levels = grouped.get(node.vertical_slice) ?? new Map<string, GraphNode[]>();
      const values = levels.get(node.level) ?? [];
      values.push(node);
      levels.set(node.level, values);
      grouped.set(node.vertical_slice, levels);
    }
    return grouped;
  }, [graph, query]);

  return (
    <>
      <header>
        <strong>Outline</strong>
        <input
          aria-label="Search DSL outline"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find block or role"
        />
      </header>
      <div>
        {slices.size === 0 ? (
          <p>No matching DSL blocks.</p>
        ) : (
          [...slices].map(([slice, levels]) => (
            <details key={slice} open>
              <summary>{label(slice)}</summary>
              {[...levels].map(([level, values]) => (
                <details key={level} open={Boolean(query)}>
                  <summary>
                    {label(level)} · {values.length}
                  </summary>
                  {values
                    .sort((left, right) => left.line - right.line)
                    .map((node) => (
                      <button
                        key={node.id}
                        type="button"
                        data-outline-line={node.line}
                        onClick={() => onSelect(node.line)}
                      >
                        <span>{node.id}</span>
                        <small>
                          {label(node.level)} · probability{' '}
                          {node.distribution_probability?.toFixed(4) ?? '—'} ·{' '}
                          {node.roles_exposed.length} role
                          {node.roles_exposed.length === 1 ? '' : 's'}
                        </small>
                      </button>
                    ))}
                </details>
              ))}
            </details>
          ))
        )}
      </div>
    </>
  );
};

export class DslOutline {
  private graph?: ProgramGraph;
  private readonly root: Root;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: OutlineOptions,
  ) {
    this.host.className = 'dsl-outline';
    this.root = createRoot(host);
    this.render();
  }

  destroy(): void {
    this.root.unmount();
  }

  setGraph(graph?: ProgramGraph | null): void {
    this.graph = graph ?? undefined;
    this.render();
  }

  private render(): void {
    this.root.render(<OutlineComponent graph={this.graph} onSelect={this.options.onSelect} />);
  }
}
