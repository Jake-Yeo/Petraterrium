import { api } from '../api';
import type { RunDetail, StoryDetail } from '../contracts.generated';
import { escapeHtml } from '../views';

export class StoriesView {
  private run?: RunDetail;
  private active = false;

  constructor(
    private host: HTMLElement,
    private onPlace: (place: string, day: number) => void,
    private onAgent: (agentId: string) => void,
  ) {
    this.host.addEventListener('click', this.onClick);
  }

  async activate(run?: RunDetail): Promise<void> {
    this.active = true;
    this.run = run;
    await this.render();
  }

  deactivate(): void {
    this.active = false;
  }

  async setRun(run?: RunDetail): Promise<void> {
    this.run = run;
    if (this.active) await this.render();
  }

  private async render(): Promise<void> {
    if (!this.run) {
      this.host.innerHTML = '<section class="stories-empty"><p class="eyebrow">STORIES / RECORDED OUTPUT</p><h1>Run a world to open its newsroom.</h1><p>Every headline will link back to an exact snapshot, place, and synthetic population.</p></section>';
      return;
    }
    const result = await api.stories(this.run.run_id);
    this.host.innerHTML = `
      <section class="stories-header"><div><p class="eyebrow">WEEKLY NEWSROOM / ${escapeHtml(this.run.config.scenario.toUpperCase())}</p><h1>Stories from recorded state.</h1><p>Template numbers come directly from the engine. Click through to the place and agents beneath them.</p></div><span class="mono">${result.stories.length} STORIES</span></section>
      <div class="stories-layout"><div id="story-feed" class="story-feed">${result.stories
        .map((story) => `<button data-story-id="${escapeHtml(story.story_id)}"><span>DAY ${story.day} · ${escapeHtml(story.place)}</span><strong>${escapeHtml(story.headline)}</strong><small>${story.template ? 'Validated template' : 'Validated narrative'}</small></button>`)
        .join('') || '<p class="muted">No threshold event fired in this run.</p>'}</div><article id="story-reader" class="story-reader"><span class="small-label">SELECT A HEADLINE</span><h2>Every claim has a receipt.</h2></article></div>`;
  }

  private onClick = (event: MouseEvent): void => {
    const target = event.target as HTMLElement;
    const story = target.closest<HTMLElement>('[data-story-id]');
    const agent = target.closest<HTMLElement>('[data-story-agent]');
    if (story?.dataset.storyId) void this.openStory(story.dataset.storyId);
    if (agent?.dataset.storyAgent) this.onAgent(agent.dataset.storyAgent);
    const place = target.closest<HTMLElement>('[data-story-place]');
    if (place?.dataset.storyPlace)
      this.onPlace(place.dataset.storyPlace, Number(place.dataset.storyDay));
  };

  private async openStory(storyId: string): Promise<void> {
    if (!this.run) return;
    const detail = await api.story(storyId, this.run.run_id);
    this.renderReader(detail);
  }

  private renderReader(detail: StoryDetail): void {
    const target = this.host.querySelector<HTMLElement>('#story-reader')!;
    target.innerHTML = `
      <span class="small-label">DAY ${detail.story.day} / ${escapeHtml(detail.story.place)}</span>
      <h2>${escapeHtml(detail.story.headline)}</h2><p>${escapeHtml(detail.story.body)}</p>
      <dl>${Object.entries(detail.story.metrics).map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${Number(value).toLocaleString()}</dd></div>`).join('')}</dl>
      <button class="button secondary" data-story-place="${escapeHtml(detail.story.place)}" data-story-day="${detail.story.day}">Zoom to recorded place</button>
      <h3>Synthetic agents in this place</h3><div class="story-agents">${detail.agents.map((agent) => `<button data-story-agent="${escapeHtml(agent.agent_id)}"><i style="background:${escapeHtml(agent.color)}"></i>${escapeHtml(agent.agent_id.slice(0, 8))}<span>${escapeHtml(agent.state)} · ${escapeHtml(agent.log_tier)}</span></button>`).join('')}</div>
      <p class="story-receipt">Event ${escapeHtml(detail.story.event_id)} · Arc ${escapeHtml(detail.story.arc_id)} · ${detail.story.template ? 'template exact' : 'validated narrative'}</p>`;
  }
}
