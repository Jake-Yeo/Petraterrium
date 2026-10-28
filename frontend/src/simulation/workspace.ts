import type { RunDetail } from '../contracts.generated';
import { TextDslEditor } from './text-dsl-editor';
import './workspace.css';

export type SimulationSection = 'graph' | 'agents' | 'trees' | 'globe' | 'run';

export interface SimulationWorkspaceOptions {
  onSectionChange: (section: SimulationSection) => void;
  onError: (error: unknown) => void;
}

export class SimulationWorkspace {
  private readonly editor: TextDslEditor;
  private active = true;

  constructor(private readonly options: SimulationWorkspaceOptions) {
    const host = document.getElementById('simulation-graph-view');
    if (!host) throw new Error('Missing DSL code workspace');
    this.editor = new TextDslEditor(host, {
      onError: (error) => this.options.onError(error),
    });
    this.show('graph');
  }

  show(_section: SimulationSection): void {
    document
      .querySelectorAll<HTMLElement>('.simulation-section')
      .forEach((section) => (section.hidden = section.id !== 'simulation-graph-view'));
    document.querySelectorAll<HTMLButtonElement>('[data-simulation-section]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.simulationSection === 'graph'));
    });
    if (this.active) this.editor.activate();
    this.options.onSectionChange('graph');
  }

  currentSection(): SimulationSection {
    return 'graph';
  }

  activate(): void {
    this.active = true;
    this.editor.activate();
  }

  deactivate(): void {
    this.active = false;
    this.editor.deactivate();
  }

  setRun(_run?: RunDetail): void {}

  selectAgent(_agentId: string): void {
    this.show('graph');
  }

  destroy(): void {
    this.editor.destroy();
  }
}
