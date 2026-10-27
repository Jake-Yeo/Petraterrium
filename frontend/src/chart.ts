import type { DailySnapshot } from './contracts.generated';

export function infectedTotal(snapshot: DailySnapshot): number {
  return snapshot.places.reduce((total, place) => total + place.infected, 0);
}

export function primaryMetricName(snapshot: DailySnapshot): string {
  if (snapshot.places.some((place) => 'infected' in place.metrics)) return 'infected';
  const values = Object.values(snapshot.places[0]?.states ?? {})[0];
  return Object.keys(values ?? {})[1] ?? Object.keys(values ?? {})[0] ?? 'population';
}

export function metricTotal(snapshot: DailySnapshot, metric = primaryMetricName(snapshot)): number {
  return snapshot.places.reduce((total, place) => total + (place.metrics[metric] ?? 0), 0);
}

export class InfectionChart {
  private snapshots: DailySnapshot[] = [];
  private index = 0;
  private observer: ResizeObserver;

  constructor(
    private canvas: HTMLCanvasElement,
    private onSelect: (index: number) => void,
  ) {
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(canvas);
    canvas.addEventListener('pointerdown', this.select);
  }

  update(snapshots: DailySnapshot[], index: number): void {
    this.snapshots = snapshots;
    this.index = index;
    this.draw();
  }

  private select = (event: PointerEvent): void => {
    if (!this.snapshots.length) return;
    const rectangle = this.canvas.getBoundingClientRect();
    const ratio = Math.max(
      0,
      Math.min(1, (event.clientX - rectangle.left - 52) / (rectangle.width - 68)),
    );
    this.onSelect(Math.round(ratio * (this.snapshots.length - 1)));
  };

  private draw(): void {
    const context = this.canvas.getContext('2d');
    if (!context) return;
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height) return;
    const ratio = Math.min(devicePixelRatio, 2);
    this.canvas.width = width * ratio;
    this.canvas.height = height * ratio;
    context.scale(ratio, ratio);
    const left = 52,
      top = 10,
      right = width - 16,
      bottom = height - 24;
    const metric = this.snapshots[0] ? primaryMetricName(this.snapshots[0]) : '';
    const values = this.snapshots.map((snapshot) => metricTotal(snapshot, metric));
    const maximum = Math.max(10, ...values) * 1.12;
    const x = (index: number) => left + (index / Math.max(1, values.length - 1)) * (right - left);
    const y = (value: number) => bottom - (value / maximum) * (bottom - top);
    context.font = '10px ui-monospace, monospace';
    context.textAlign = 'right';
    for (let line = 0; line <= 3; line++) {
      const value = (maximum * line) / 3;
      const vertical = y(value);
      context.strokeStyle = '#ffffff0c';
      context.beginPath();
      context.moveTo(left, vertical);
      context.lineTo(right, vertical);
      context.stroke();
      context.fillStyle = '#75838d';
      context.fillText(
        Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value),
        left - 10,
        vertical + 3,
      );
    }
    if (!values.length) {
      context.textAlign = 'center';
      context.fillStyle = '#75838d';
      context.fillText(
        'Recorded state metrics will appear here',
        (left + right) / 2,
        (top + bottom) / 2,
      );
      return;
    }
    const area = context.createLinearGradient(0, top, 0, bottom);
    area.addColorStop(0, '#e9a37732');
    area.addColorStop(1, '#e9a37700');
    context.beginPath();
    context.moveTo(x(0), bottom);
    values.forEach((value, index) => context.lineTo(x(index), y(value)));
    context.lineTo(x(values.length - 1), bottom);
    context.closePath();
    context.fillStyle = area;
    context.fill();
    context.beginPath();
    values.forEach((value, index) =>
      index ? context.lineTo(x(index), y(value)) : context.moveTo(x(index), y(value)),
    );
    context.strokeStyle = '#e9a377';
    context.lineWidth = 1.8;
    context.stroke();
    context.strokeStyle = '#b5e7b18a';
    context.setLineDash([3, 4]);
    context.beginPath();
    context.moveTo(x(this.index), top);
    context.lineTo(x(this.index), bottom);
    context.stroke();
    context.setLineDash([]);
    context.beginPath();
    context.arc(x(this.index), y(values[this.index]), 3.5, 0, Math.PI * 2);
    context.fillStyle = '#b5e7b1';
    context.fill();
    context.fillStyle = '#75838d';
    for (let tick = 0; tick <= 4; tick++) {
      const index = Math.round(((values.length - 1) * tick) / 4);
      context.textAlign = tick === 0 ? 'left' : tick === 4 ? 'right' : 'center';
      context.fillText(`Day ${this.snapshots[index].day}`, x(index), height - 5);
    }
  }

  dispose(): void {
    this.observer.disconnect();
    this.canvas.removeEventListener('pointerdown', this.select);
  }
}
