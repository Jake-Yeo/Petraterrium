import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  simulationGlobeDetailLevelForDistance,
  simulationGlobeDistanceForDetailLevel,
  simulationGlobePlaceKey,
} from './run-globe-data';
import { countrySurfaceGeometry } from './run-globe-geography';
import type {
  SimulationGlobeAggregateRecord,
  SimulationGlobeAgentPoint,
  SimulationGlobeDetailLevel,
  SimulationGlobeDiagnostics,
  SimulationGlobePlaceLevel,
  SimulationGlobeViewportBounds,
} from './run-globe-types';

type AggregateLayer = {
  mesh: THREE.InstancedMesh<THREE.CircleGeometry, THREE.MeshBasicMaterial>;
  capacity: number;
  records: SimulationGlobeAggregateRecord[];
};

type CountrySurface = {
  mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
  country: SimulationGlobeAggregateRecord;
  region?: SimulationGlobeAggregateRecord;
};

type SimulationRunGlobeRendererHandlers = {
  place_selected: (record: SimulationGlobeAggregateRecord) => void;
  agent_selected: (agent: SimulationGlobeAgentPoint) => void;
  detail_level_changed: (detailLevel: SimulationGlobeDetailLevel) => void;
  viewport_changed: (
    detailLevel: 'city' | 'neighborhood',
    bounds: SimulationGlobeViewportBounds,
  ) => void;
};

const levels: SimulationGlobePlaceLevel[] = ['region', 'country', 'city'];
const levelRadius: Record<SimulationGlobePlaceLevel, number> = {
  region: 0.105,
  country: 0.055,
  city: 0.022,
};
const statePalette = ['#6fd6a7', '#82b5ed', '#e9bd70', '#dd7d78', '#b691df', '#6fd0d8'];

const globePosition = (latitude: number, longitude: number, radius: number): THREE.Vector3 => {
  const phi = THREE.MathUtils.degToRad(latitude);
  const theta = THREE.MathUtils.degToRad(longitude);
  return new THREE.Vector3(
    radius * Math.cos(phi) * Math.sin(theta),
    radius * Math.sin(phi),
    radius * Math.cos(phi) * Math.cos(theta),
  );
};

const longitudeWithin180 = (longitude: number): number =>
  ((((longitude + 180) % 360) + 360) % 360) - 180;

const stateColor = (state: string): THREE.Color => {
  let hash = 0;
  for (const character of state) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return new THREE.Color(statePalette[hash % statePalette.length]);
};

export class SimulationRunGlobeRenderer {
  readonly canvas: HTMLCanvasElement;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(38, 1, 0.05, 100);
  private readonly controls: OrbitControls;
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointer = new THREE.Vector2();
  private readonly aggregateLayers = new Map<SimulationGlobePlaceLevel, AggregateLayer>();
  private readonly countrySurfaces = new Map<string, CountrySurface>();
  private readonly selectionRing: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  private readonly resizeObserver: ResizeObserver;
  private readonly intersectionObserver: IntersectionObserver;
  private readonly themeObserver: MutationObserver;
  private agentCloud?: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial>;
  private agentPoints: SimulationGlobeAgentPoint[] = [];
  private detailLevel: SimulationGlobeDetailLevel = 'world';
  private selectedPlaceKey: string | null = null;
  private visible = true;
  private inViewport = true;
  private disposed = false;
  private requestedFrame = 0;
  private pointerStart?: { x: number; y: number };
  private renderCount = 0;
  private aggregateUploadCount = 0;
  private agentPointUploadCount = 0;
  private areaColorUploadCount = 0;
  private aggregateValues: ReadonlyMap<string, number | null> = new Map();
  private aggregateMinimum = 0;
  private aggregateMaximum = 1;

  constructor(
    private readonly host: HTMLElement,
    private readonly handlers: SimulationRunGlobeRendererHandlers,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.canvas = this.renderer.domElement;
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.canvas.className = 'simulation-run-globe-canvas';
    this.canvas.tabIndex = 0;
    this.canvas.setAttribute('role', 'application');
    this.canvas.setAttribute(
      'aria-label',
      '3D simulation globe. Drag to rotate, scroll to zoom, and select a place to inspect its recorded aggregate statistics.',
    );
    host.append(this.canvas);
    this.camera.position.set(0, 0, simulationGlobeDistanceForDetailLevel('world'));
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = false;
    this.controls.enablePan = false;
    this.controls.minDistance = 1.22;
    this.controls.maxDistance = 5.6;
    this.controls.rotateSpeed = 0.55;
    this.controls.zoomSpeed = 0.75;
    this.scene.add(new THREE.HemisphereLight(0xd7ece8, 0x17232b, 2.4));
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.8);
    directionalLight.position.set(-3, 4, 5);
    this.scene.add(directionalLight);
    this.scene.add(
      new THREE.Mesh(
        new THREE.SphereGeometry(1, 72, 48),
        new THREE.MeshPhongMaterial({
          color: 0x16313a,
          emissive: 0x081318,
          shininess: 7,
          specular: 0x34515b,
        }),
      ),
    );
    this.addGraticule();
    this.selectionRing = new THREE.Mesh(
      new THREE.RingGeometry(0.065, 0.078, 48),
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.92,
        depthTest: false,
      }),
    );
    this.selectionRing.visible = false;
    this.selectionRing.renderOrder = 4;
    this.scene.add(this.selectionRing);
    for (const level of levels) this.aggregateLayers.set(level, this.createLayer(level, 1));
    this.controls.addEventListener('change', this.handleControlsChange);
    this.controls.addEventListener('end', this.handleControlsEnd);
    this.canvas.addEventListener('pointerdown', this.handlePointerDown);
    this.canvas.addEventListener('pointerup', this.handlePointerUp);
    this.canvas.addEventListener('keydown', this.handleKeyDown);
    this.resizeObserver = new ResizeObserver(this.resize);
    this.resizeObserver.observe(host);
    this.intersectionObserver = new IntersectionObserver(([entry]) => {
      this.inViewport = entry?.isIntersecting ?? true;
      this.requestRender();
    });
    this.intersectionObserver.observe(host);
    this.themeObserver = new MutationObserver(() => this.refreshTheme());
    this.themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-theme', 'data-color-scheme'],
    });
    this.refreshTheme();
    this.resize();
  }

  private addGraticule(): void {
    const material = new THREE.LineBasicMaterial({
      color: 0x77949a,
      transparent: true,
      opacity: 0.17,
    });
    for (let latitude = -75; latitude <= 75; latitude += 15) {
      const points = Array.from({ length: 121 }, (_, index) =>
        globePosition(latitude, index * 3, 1.002),
      );
      this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
    }
    for (let longitude = 0; longitude < 360; longitude += 15) {
      const points = Array.from({ length: 91 }, (_, index) =>
        globePosition(-90 + index * 2, longitude, 1.002),
      );
      this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
    }
  }

  private createLayer(level: SimulationGlobePlaceLevel, capacity: number): AggregateLayer {
    const material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
      vertexColors: true,
    });
    const mesh = new THREE.InstancedMesh(new THREE.CircleGeometry(1, 32), material, capacity);
    mesh.count = 0;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.renderOrder = level === 'region' ? 1 : level === 'country' ? 2 : 3;
    this.scene.add(mesh);
    return { mesh, capacity, records: [] };
  }

  private ensureLayerCapacity(level: SimulationGlobePlaceLevel, required: number): AggregateLayer {
    const current = this.aggregateLayers.get(level)!;
    if (current.capacity >= Math.max(1, required)) return current;
    this.scene.remove(current.mesh);
    current.mesh.geometry.dispose();
    current.mesh.material.dispose();
    const nextCapacity = Math.max(required, current.capacity * 2);
    const next = this.createLayer(level, nextCapacity);
    this.aggregateLayers.set(level, next);
    return next;
  }

  updateAggregates(
    records: readonly SimulationGlobeAggregateRecord[],
    values: ReadonlyMap<string, number | null>,
  ): void {
    const finiteValues = [...values.values()].filter(
      (value): value is number => value !== null && Number.isFinite(value),
    );
    const minimum = finiteValues.length ? Math.min(...finiteValues) : 0;
    const maximum = finiteValues.length ? Math.max(...finiteValues) : 1;
    this.aggregateValues = values;
    this.aggregateMinimum = minimum;
    this.aggregateMaximum = maximum;
    for (const level of levels) {
      const levelRecords = records.filter((record) => record.place_level === level);
      const layer = this.ensureLayerCapacity(level, levelRecords.length);
      layer.records = [...levelRecords];
      layer.mesh.count = levelRecords.length;
      levelRecords.forEach((record, index) => {
        const position = globePosition(record.latitude, record.longitude, 1.012 + index * 1e-7);
        const orientation = new THREE.Quaternion().setFromUnitVectors(
          new THREE.Vector3(0, 0, 1),
          position.clone().normalize(),
        );
        const populationMagnitude = Math.max(0, Math.log10(Math.max(1, record.population)) - 2);
        const radius = levelRadius[level] * (0.8 + Math.min(1.4, populationMagnitude / 6));
        const matrix = new THREE.Matrix4().compose(
          position,
          orientation,
          new THREE.Vector3(radius, radius, radius),
        );
        layer.mesh.setMatrixAt(index, matrix);
        const value = values.get(simulationGlobePlaceKey(level, record.place_id)) ?? null;
        layer.mesh.setColorAt(index, this.aggregateColor(value, minimum, maximum));
      });
      layer.mesh.instanceMatrix.needsUpdate = true;
      if (layer.mesh.instanceColor) layer.mesh.instanceColor.needsUpdate = true;
    }
    this.updateCountrySurfaces(records);
    this.aggregateUploadCount += 1;
    this.applyLayerVisibility();
    this.updateSelectionRing();
    this.requestRender();
  }

  private updateCountrySurfaces(records: readonly SimulationGlobeAggregateRecord[]): void {
    const countries = records.filter((record) => record.place_level === 'country');
    const regions = new Map(
      records
        .filter((record) => record.place_level === 'region')
        .map((record) => [record.place_id, record]),
    );
    const active = new Set(countries.map((record) => record.place_id));
    for (const [placeId, surface] of this.countrySurfaces) {
      if (active.has(placeId)) continue;
      this.scene.remove(surface.mesh);
      surface.mesh.geometry.dispose();
      surface.mesh.material.dispose();
      this.countrySurfaces.delete(placeId);
    }
    for (const country of countries) {
      let surface = this.countrySurfaces.get(country.place_id);
      if (!surface) {
        const geometry = countrySurfaceGeometry(country.place_label);
        if (!geometry) continue;
        const material = new THREE.MeshBasicMaterial({
          color: '#65737b',
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.68,
          depthWrite: false,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.renderOrder = 1;
        this.scene.add(mesh);
        surface = { mesh, country };
        this.countrySurfaces.set(country.place_id, surface);
      }
      surface.country = country;
      surface.region = country.parent_place_id
        ? regions.get(country.parent_place_id)
        : undefined;
    }
  }

  private refreshCountrySurfaceColors(): void {
    for (const surface of this.countrySurfaces.values()) {
      const record =
        this.detailLevel === 'world' && surface.region ? surface.region : surface.country;
      const value =
        this.aggregateValues.get(simulationGlobePlaceKey(record.place_level, record.place_id)) ??
        null;
      surface.mesh.material.color.copy(
        this.aggregateColor(value, this.aggregateMinimum, this.aggregateMaximum),
      );
      surface.mesh.visible = this.detailLevel === 'world' || this.detailLevel === 'country';
      surface.mesh.material.opacity = this.detailLevel === 'world' ? 0.62 : 0.74;
    }
    this.areaColorUploadCount += 1;
  }

  private aggregateColor(value: number | null, minimum: number, maximum: number): THREE.Color {
    if (value === null || !Number.isFinite(value)) return new THREE.Color('#65737b');
    const normalized = maximum === minimum ? 0.5 : (value - minimum) / (maximum - minimum);
    const low = new THREE.Color('#55c9b0');
    const middle = new THREE.Color('#e4d26c');
    const high = new THREE.Color('#df735f');
    return normalized <= 0.5
      ? low.lerp(middle, normalized * 2)
      : middle.lerp(high, (normalized - 0.5) * 2);
  }

  private applyLayerVisibility(): void {
    const opacity: Record<SimulationGlobePlaceLevel, number> =
      this.detailLevel === 'world'
        ? { region: 0.84, country: 0.4, city: 0.16 }
        : this.detailLevel === 'country'
          ? { region: 0, country: 0.88, city: 0.25 }
          : { region: 0, country: 0, city: 0.92 };
    for (const level of levels) {
      const layer = this.aggregateLayers.get(level)!;
      layer.mesh.visible = opacity[level] > 0 && layer.mesh.count > 0;
      layer.mesh.material.opacity = opacity[level];
    }
    this.refreshCountrySurfaceColors();
  }

  selectPlace(level: SimulationGlobePlaceLevel, placeId: string): void {
    this.selectedPlaceKey = simulationGlobePlaceKey(level, placeId);
    this.updateSelectionRing();
    this.requestRender();
  }

  private updateSelectionRing(): void {
    const record = this.selectedRecord();
    if (!record) {
      this.selectionRing.visible = false;
      return;
    }
    const position = globePosition(record.latitude, record.longitude, 1.035);
    this.selectionRing.position.copy(position);
    this.selectionRing.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 0, 1),
      position.clone().normalize(),
    );
    const scale = record.place_level === 'region' ? 1.8 : record.place_level === 'city' ? 0.55 : 1;
    this.selectionRing.scale.setScalar(scale);
    this.selectionRing.visible = true;
  }

  private selectedRecord(): SimulationGlobeAggregateRecord | undefined {
    if (!this.selectedPlaceKey) return undefined;
    for (const layer of this.aggregateLayers.values()) {
      const record = layer.records.find(
        (item) =>
          simulationGlobePlaceKey(item.place_level, item.place_id) === this.selectedPlaceKey,
      );
      if (record) return record;
    }
    return undefined;
  }

  setAgentPoints(points: readonly SimulationGlobeAgentPoint[]): void {
    this.clearAgentPoints();
    this.agentPoints = [...points];
    if (!points.length) {
      this.agentPointUploadCount += 1;
      this.requestRender();
      return;
    }
    const positions: number[] = [];
    const colors: number[] = [];
    for (const point of points) {
      positions.push(...globePosition(point.latitude, point.longitude, 1.037).toArray());
      const color = point.color ? new THREE.Color(point.color) : stateColor(point.state);
      colors.push(color.r, color.g, color.b);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    this.agentCloud = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        size: this.detailLevel === 'neighborhood' ? 0.021 : 0.012,
        sizeAttenuation: true,
        vertexColors: true,
        transparent: true,
        opacity: 0.94,
        depthWrite: false,
      }),
    );
    this.agentCloud.renderOrder = 5;
    this.scene.add(this.agentCloud);
    this.agentPointUploadCount += 1;
    this.requestRender();
  }

  clearAgentPoints(): void {
    if (this.agentCloud) {
      this.scene.remove(this.agentCloud);
      this.agentCloud.geometry.dispose();
      this.agentCloud.material.dispose();
    }
    this.agentCloud = undefined;
    this.agentPoints = [];
  }

  setDetailLevel(detailLevel: SimulationGlobeDetailLevel): void {
    const direction = this.camera.position.clone().normalize();
    this.camera.position.copy(
      direction.multiplyScalar(simulationGlobeDistanceForDetailLevel(detailLevel)),
    );
    this.camera.lookAt(0, 0, 0);
    this.controls.update();
    this.updateDetailLevel();
    this.handleControlsEnd();
    this.requestRender();
  }

  focus(record: SimulationGlobeAggregateRecord, detailLevel?: SimulationGlobeDetailLevel): void {
    const distance = detailLevel
      ? simulationGlobeDistanceForDetailLevel(detailLevel)
      : this.camera.position.length();
    this.camera.position.copy(
      globePosition(record.latitude, record.longitude, 1).normalize().multiplyScalar(distance),
    );
    this.camera.lookAt(0, 0, 0);
    this.controls.update();
    this.updateDetailLevel();
    this.handleControlsEnd();
    this.requestRender();
  }

  private handleControlsChange = (): void => {
    this.updateDetailLevel();
    this.requestRender();
  };

  private handleControlsEnd = (): void => {
    if (this.detailLevel !== 'city' && this.detailLevel !== 'neighborhood') return;
    this.handlers.viewport_changed(this.detailLevel, this.viewportBounds());
  };

  private updateDetailLevel(): void {
    const next = simulationGlobeDetailLevelForDistance(this.camera.position.length());
    if (next === this.detailLevel) return;
    this.detailLevel = next;
    this.applyLayerVisibility();
    if (next !== 'city' && next !== 'neighborhood') this.clearAgentPoints();
    this.handlers.detail_level_changed(next);
  }

  private viewportBounds(): SimulationGlobeViewportBounds {
    const direction = this.camera.position.clone().normalize();
    const latitude = THREE.MathUtils.radToDeg(Math.asin(direction.y));
    const longitude = THREE.MathUtils.radToDeg(Math.atan2(direction.x, direction.z));
    const latitudeSpan = this.detailLevel === 'neighborhood' ? 2.5 : 16;
    const longitudeSpan =
      latitudeSpan / Math.max(0.25, Math.cos(THREE.MathUtils.degToRad(latitude)));
    return {
      north: Math.min(90, latitude + latitudeSpan),
      east: longitudeWithin180(longitude + longitudeSpan),
      south: Math.max(-90, latitude - latitudeSpan),
      west: longitudeWithin180(longitude - longitudeSpan),
    };
  }

  private handlePointerDown = (event: PointerEvent): void => {
    this.pointerStart = { x: event.clientX, y: event.clientY };
  };

  private handlePointerUp = (event: PointerEvent): void => {
    if (
      !this.pointerStart ||
      Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y) > 5
    )
      return;
    this.pick(event.clientX, event.clientY);
  };

  private handleKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    const bounds = this.canvas.getBoundingClientRect();
    this.pick(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
  };

  private pick(clientX: number, clientY: number): void {
    const bounds = this.canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    this.pointer.set(
      ((clientX - bounds.left) / bounds.width) * 2 - 1,
      -((clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    if (this.agentCloud && (this.detailLevel === 'city' || this.detailLevel === 'neighborhood')) {
      this.raycaster.params.Points = { threshold: 0.028 };
      const agentHit = this.raycaster.intersectObject(this.agentCloud)[0];
      if (agentHit?.index !== undefined) {
        const agent = this.agentPoints[agentHit.index];
        if (agent) {
          this.handlers.agent_selected(agent);
          return;
        }
      }
    }
    const order: SimulationGlobePlaceLevel[] =
      this.detailLevel === 'world'
        ? ['region', 'country', 'city']
        : this.detailLevel === 'country'
          ? ['country', 'city']
          : ['city'];
    for (const level of order) {
      const layer = this.aggregateLayers.get(level)!;
      if (!layer.mesh.visible) continue;
      const hit = this.raycaster.intersectObject(layer.mesh)[0];
      if (hit?.instanceId === undefined) continue;
      const record = layer.records[hit.instanceId];
      if (record) {
        this.handlers.place_selected(record);
        return;
      }
    }
    if (this.detailLevel === 'world' || this.detailLevel === 'country') {
      const surfaces = [...this.countrySurfaces.values()].filter((surface) => surface.mesh.visible);
      const hit = this.raycaster.intersectObjects(surfaces.map((surface) => surface.mesh))[0];
      if (hit) {
        const surface = surfaces.find((candidate) => candidate.mesh === hit.object);
        const record =
          this.detailLevel === 'world' && surface?.region ? surface.region : surface?.country;
        if (record) this.handlers.place_selected(record);
      }
    }
  }

  private resize = (): void => {
    const width = this.host.clientWidth;
    const height = this.host.clientHeight;
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  };

  private refreshTheme(): void {
    const root = document.documentElement;
    const light =
      root.dataset.theme === 'light' ||
      root.dataset.colorScheme === 'light' ||
      root.classList.contains('theme-light');
    const globe = this.scene.children.find(
      (child): child is THREE.Mesh<THREE.SphereGeometry, THREE.MeshPhongMaterial> =>
        child instanceof THREE.Mesh && child.geometry instanceof THREE.SphereGeometry,
    );
    if (globe) {
      globe.material.color.set(light ? '#d7e5e2' : '#16313a');
      globe.material.emissive.set(light ? '#82948f' : '#081318');
      globe.material.specular.set(light ? '#ffffff' : '#34515b');
    }
    this.requestRender();
  }

  private requestRender(): void {
    if (this.disposed || !this.visible || !this.inViewport || this.requestedFrame) return;
    this.requestedFrame = requestAnimationFrame(() => {
      this.requestedFrame = 0;
      if (this.disposed || !this.visible || !this.inViewport) return;
      this.renderer.render(this.scene, this.camera);
      this.renderCount += 1;
    });
  }

  setVisible(visible: boolean): void {
    this.visible = visible;
    if (!visible && this.requestedFrame) cancelAnimationFrame(this.requestedFrame);
    if (!visible) this.requestedFrame = 0;
    this.requestRender();
  }

  diagnostics(): SimulationGlobeDiagnostics {
    return {
      render_count: this.renderCount,
      aggregate_upload_count: this.aggregateUploadCount,
      agent_point_upload_count: this.agentPointUploadCount,
      area_color_upload_count: this.areaColorUploadCount,
      country_surface_count: this.countrySurfaces.size,
      displayed_agent_points: this.agentPoints.length,
      detail_level: this.detailLevel,
    };
  }

  dispose(): void {
    this.disposed = true;
    if (this.requestedFrame) cancelAnimationFrame(this.requestedFrame);
    this.controls.removeEventListener('change', this.handleControlsChange);
    this.controls.removeEventListener('end', this.handleControlsEnd);
    this.controls.dispose();
    this.canvas.removeEventListener('pointerdown', this.handlePointerDown);
    this.canvas.removeEventListener('pointerup', this.handlePointerUp);
    this.canvas.removeEventListener('keydown', this.handleKeyDown);
    this.resizeObserver.disconnect();
    this.intersectionObserver.disconnect();
    this.themeObserver.disconnect();
    this.scene.traverse((object) => {
      if (
        object instanceof THREE.Mesh ||
        object instanceof THREE.Line ||
        object instanceof THREE.Points
      ) {
        object.geometry.dispose();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => material.dispose());
      }
    });
    this.renderer.dispose();
    this.canvas.remove();
  }
}
