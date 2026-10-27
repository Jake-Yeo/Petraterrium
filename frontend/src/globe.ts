import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { AgentPoint, Country, DailySnapshot, PlaceSnapshot } from './contracts.generated';

type Marker = {
  country: Country;
  object: THREE.Group;
  disc: THREE.Mesh;
  ring: THREE.Mesh;
  label: HTMLDivElement;
};

type GlobeHandlers = {
  place: (place: string, day: number) => void;
  agent: (agentId: string) => void;
};

const continentOutlines = [
  [
    [-168, 72],
    [-138, 69],
    [-125, 58],
    [-128, 50],
    [-123, 40],
    [-116, 31],
    [-106, 24],
    [-98, 18],
    [-88, 21],
    [-82, 25],
    [-80, 32],
    [-70, 45],
    [-55, 52],
    [-64, 61],
    [-85, 70],
    [-110, 73],
    [-130, 70],
    [-168, 72],
  ],
  [
    [-81, 12],
    [-67, 10],
    [-51, 3],
    [-35, -7],
    [-42, -23],
    [-53, -34],
    [-68, -55],
    [-76, -43],
    [-71, -18],
    [-80, -1],
    [-81, 12],
  ],
  [
    [-52, 60],
    [-44, 60],
    [-20, 75],
    [-31, 83],
    [-54, 81],
    [-61, 70],
    [-52, 60],
  ],
  [
    [-17, 36],
    [0, 37],
    [10, 37],
    [23, 32],
    [33, 31],
    [43, 12],
    [51, 11],
    [43, -13],
    [35, -25],
    [20, -35],
    [12, -18],
    [9, 4],
    [-3, 5],
    [-17, 15],
    [-17, 36],
  ],
  [
    [-10, 36],
    [-9, 43],
    [-2, 49],
    [5, 52],
    [8, 57],
    [19, 60],
    [25, 71],
    [35, 70],
    [42, 62],
    [62, 68],
    [92, 77],
    [116, 73],
    [140, 68],
    [174, 62],
    [162, 52],
    [143, 43],
    [130, 33],
    [122, 21],
    [109, 20],
    [105, 6],
    [98, 13],
    [90, 22],
    [80, 7],
    [72, 21],
    [57, 25],
    [49, 30],
    [40, 41],
    [29, 41],
    [25, 35],
    [18, 40],
    [13, 46],
    [8, 43],
    [3, 43],
    [-10, 36],
  ],
  [
    [112, -11],
    [130, -12],
    [141, -10],
    [153, -26],
    [146, -39],
    [131, -32],
    [115, -34],
    [112, -21],
    [112, -11],
  ],
  [
    [-8, 50],
    [-6, 58],
    [-2, 59],
    [2, 52],
    [-8, 50],
  ],
  [
    [46, -13],
    [50, -18],
    [47, -26],
    [43, -21],
    [46, -13],
  ],
  [
    [130, 32],
    [140, 40],
    [143, 45],
    [146, 43],
    [141, 35],
    [130, 32],
  ],
  [
    [166, -35],
    [175, -40],
    [168, -47],
    [163, -44],
    [166, -35],
  ],
];

function position(latitude: number, longitude: number, radius: number): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(latitude);
  const theta = THREE.MathUtils.degToRad(longitude);
  return new THREE.Vector3(
    radius * Math.cos(phi) * Math.sin(theta),
    radius * Math.sin(phi),
    radius * Math.cos(phi) * Math.cos(theta),
  );
}

export class Globe {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(37, 1, 0.1, 100);
  private controls: OrbitControls;
  private markers: Marker[] = [];
  private observer: ResizeObserver;
  private intersectionObserver: IntersectionObserver;
  private frame = 0;
  private visible = true;
  private inViewport = true;
  private disposed = false;
  private projection = new THREE.Vector3();
  private reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private pointerStart?: { x: number; y: number };
  private agentCloud?: THREE.Points;
  private spotlightCloud?: THREE.Points;
  private agents: AgentPoint[] = [];
  private snapshot?: DailySnapshot;

  constructor(
    private host: HTMLElement,
    countries: Country[],
    private handlers?: GlobeHandlers,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x0b1119, 0);
    this.renderer.domElement.setAttribute(
      'aria-label',
      'Interactive globe. Drag to rotate; scroll to zoom. Country counts are also in the table below.',
    );
    this.renderer.domElement.setAttribute('role', 'img');
    host.prepend(this.renderer.domElement);
    this.camera.position.copy(position(30, 15, 4.2));
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.enablePan = false;
    this.controls.minDistance = 2.5;
    this.controls.maxDistance = 6;
    this.controls.autoRotate = !this.reducedMotion;
    this.controls.autoRotateSpeed = 0.12;
    this.scene.add(new THREE.AmbientLight(0xc2d1e2, 2));
    const light = new THREE.DirectionalLight(0xb0c8d0, 2.3);
    light.position.set(-3, 4, 5);
    this.scene.add(light);
    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(1, 72, 48),
      new THREE.MeshPhongMaterial({ color: 0x152b36, shininess: 7, specular: 0x203941 }),
    );
    this.scene.add(globe);
    this.addGraticule();
    this.addContinents();
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(1.04, 48, 32),
      new THREE.MeshBasicMaterial({
        color: 0x6eabb0,
        transparent: true,
        opacity: 0.06,
        side: THREE.BackSide,
      }),
    );
    this.scene.add(halo);
    for (const country of countries) this.addMarker(country);
    this.renderer.domElement.addEventListener('pointerdown', this.startPicking);
    this.renderer.domElement.addEventListener('pointerup', this.finishPicking);
    this.observer = new ResizeObserver(this.resize);
    this.observer.observe(host);
    this.intersectionObserver = new IntersectionObserver(([entry]) => {
      this.inViewport = entry.isIntersecting;
      this.setVisible(this.visible);
    });
    this.intersectionObserver.observe(host);
    document.addEventListener('visibilitychange', this.onVisibility);
    this.resize();
    this.animate();
  }

  private addGraticule(): void {
    const material = new THREE.LineBasicMaterial({
      color: 0x6e9299,
      transparent: true,
      opacity: 0.13,
    });
    for (let latitude = -75; latitude <= 75; latitude += 15) {
      const points = Array.from({ length: 121 }, (_, i) => position(latitude, i * 3, 1.002));
      this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
    }
    for (let longitude = 0; longitude < 360; longitude += 15) {
      const points = Array.from({ length: 91 }, (_, i) => position(-90 + i * 2, longitude, 1.002));
      this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
    }
  }

  private addContinents(): void {
    const vertices: number[] = [];
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x78a49e,
      transparent: true,
      opacity: 0.42,
    });
    for (const outline of continentOutlines) {
      const points = outline.map(([lon, lat]) => position(lat, lon, 1.006));
      this.scene.add(
        new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), lineMaterial),
      );
    }
    const inside = (lon: number, lat: number, polygon: number[][]): boolean => {
      let result = false;
      for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const [xi, yi] = polygon[i];
        const [xj, yj] = polygon[j];
        if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi)
          result = !result;
      }
      return result;
    };
    for (let lat = -57; lat < 81; lat += 2.2) {
      const spacing = 2.2 / Math.max(0.25, Math.cos(THREE.MathUtils.degToRad(lat)));
      for (let lon = -178; lon < 180; lon += spacing) {
        if (continentOutlines.some((polygon) => inside(lon, lat, polygon))) {
          vertices.push(...position(lat, lon, 1.008).toArray());
        }
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    this.scene.add(
      new THREE.Points(
        geometry,
        new THREE.PointsMaterial({
          color: 0x81a49a,
          size: 0.009,
          transparent: true,
          opacity: 0.48,
        }),
      ),
    );
  }

  private addMarker(country: Country): void {
    const object = new THREE.Group();
    object.position.copy(position(country.latitude, country.longitude, 1.027));
    object.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 0, 1),
      object.position.clone().normalize(),
    );
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(0.012, 24),
      new THREE.MeshBasicMaterial({ color: 0xb9e8b0, side: THREE.DoubleSide }),
    );
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.019, 0.021, 40),
      new THREE.MeshBasicMaterial({
        color: 0xb9e8b0,
        transparent: true,
        opacity: 0.5,
        side: THREE.DoubleSide,
      }),
    );
    object.add(disc, ring);
    this.scene.add(object);
    const label = document.createElement('div');
    label.className = `globe-label globe-label-${country.country.toLowerCase()}`;
    label.textContent = country.name;
    label.hidden = true;
    this.host.append(label);
    this.markers.push({ country, object, disc, ring, label });
  }

  update(snapshot: DailySnapshot | undefined): void {
    this.snapshot = snapshot;
    for (const place of snapshot?.places ?? []) {
      if (
        !this.markers.some((marker) => marker.country.country === place.country) &&
        place.latitude !== null &&
        place.longitude !== null
      ) {
        this.addMarker(this.countryFromPlace(place));
      }
    }
    for (const marker of this.markers) {
      const place = snapshot?.places.find((value) => value.country === marker.country.country);
      marker.object.visible = !!place;
      marker.label.hidden = !place;
      if (!place) continue;
      const metric = this.placeMetric(place);
      const magnitude = Math.sqrt(metric / marker.country.population);
      marker.disc.scale.setScalar(1 + magnitude * 9);
      marker.ring.scale.setScalar(1 + magnitude * 14);
      const color = new THREE.Color().lerpColors(
        new THREE.Color('#b9e8b0'),
        new THREE.Color('#f4a46a'),
        Math.min(1, magnitude * 3),
      );
      (marker.disc.material as THREE.MeshBasicMaterial).color.copy(color);
      (marker.ring.material as THREE.MeshBasicMaterial).color.copy(color);
      marker.label.textContent = `${marker.country.name} · ${metric.toLocaleString()}`;
    }
  }

  private countryFromPlace(place: PlaceSnapshot): Country {
    const firstState = Object.values(place.states)[0];
    const population = firstState
      ? Object.values(firstState).reduce((sum, value) => sum + value, 0)
      : place.susceptible + place.exposed + place.infected + place.recovered;
    return {
      country: place.country,
      name: place.country,
      population,
      latitude: place.latitude ?? 0,
      longitude: place.longitude ?? 0,
      fake: true,
    };
  }

  private placeMetric(place: PlaceSnapshot): number {
    if ('infected' in place.metrics) return place.metrics.infected;
    const firstState = Object.values(place.states)[0];
    return firstState ? Object.values(firstState)[1] ?? Object.values(firstState)[0] ?? 0 : 0;
  }

  showAgents(agents: AgentPoint[], place: string): void {
    this.clearAgents();
    this.agents = agents;
    const positions: number[] = [];
    const colors: number[] = [];
    for (const agent of agents) {
      positions.push(...position(agent.latitude, agent.longitude, 1.038).toArray());
      const color = new THREE.Color(agent.color);
      colors.push(color.r, color.g, color.b);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    this.agentCloud = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({ size: 0.018, vertexColors: true, transparent: true, opacity: 0.9 }),
    );
    this.scene.add(this.agentCloud);
    const spotlight = agents.filter((agent) => agent.log_tier === 'spotlight');
    const spotlightGeometry = new THREE.BufferGeometry().setFromPoints(
      spotlight.map((agent) => position(agent.latitude, agent.longitude, 1.044)),
    );
    this.spotlightCloud = new THREE.Points(
      spotlightGeometry,
      new THREE.PointsMaterial({ size: 0.035, color: 0xffffff, transparent: true, opacity: 0.8 }),
    );
    this.scene.add(this.spotlightCloud);
    const marker = this.markers.find((item) => item.country.country === place);
    if (marker) {
      this.camera.position.copy(marker.object.position.clone().normalize().multiplyScalar(2.55));
      this.controls.update();
    }
  }

  clearAgents(): void {
    for (const cloud of [this.agentCloud, this.spotlightCloud]) {
      if (!cloud) continue;
      this.scene.remove(cloud);
      cloud.geometry.dispose();
      (cloud.material as THREE.Material).dispose();
    }
    this.agentCloud = undefined;
    this.spotlightCloud = undefined;
    this.agents = [];
  }

  private startPicking = (event: PointerEvent): void => {
    this.pointerStart = { x: event.clientX, y: event.clientY };
  };

  private finishPicking = (event: PointerEvent): void => {
    if (
      !this.pointerStart ||
      Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y) > 5
    )
      return;
    const bounds = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    if (this.agentCloud) {
      this.raycaster.params.Points = { threshold: 0.035 };
      const agentHit = this.raycaster.intersectObject(this.agentCloud)[0];
      if (agentHit?.index !== undefined && this.agents[agentHit.index]) {
        this.handlers?.agent(this.agents[agentHit.index].agent_id);
        return;
      }
    }
    const markerHit = this.raycaster.intersectObjects(
      this.markers.map((marker) => marker.disc),
    )[0];
    if (!markerHit) return;
    const marker = this.markers.find((item) => item.disc === markerHit.object);
    if (marker && this.snapshot)
      this.handlers?.place(marker.country.country, this.snapshot.day);
  };

  private resize = (): void => {
    const width = this.host.clientWidth;
    const height = this.host.clientHeight;
    if (!width || !height) return;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  };

  private animate = (): void => {
    if (this.disposed || !this.visible || !this.inViewport || document.hidden) return;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    for (const marker of this.markers) {
      if (!marker.object.visible) continue;
      this.projection.copy(marker.object.position).project(this.camera);
      const front = marker.object.position.dot(this.camera.position) > 1;
      marker.label.style.visibility = front ? 'visible' : 'hidden';
      marker.label.style.left = `${((this.projection.x + 1) / 2) * this.host.clientWidth}px`;
      marker.label.style.top = `${((-this.projection.y + 1) / 2) * this.host.clientHeight}px`;
    }
    this.frame = requestAnimationFrame(this.animate);
  };

  setVisible(visible: boolean): void {
    this.visible = visible;
    cancelAnimationFrame(this.frame);
    if (visible && !document.hidden) {
      this.resize();
      this.animate();
    }
  }

  private onVisibility = (): void => this.setVisible(this.visible);

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.intersectionObserver.disconnect();
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.controls.dispose();
    this.renderer.domElement.removeEventListener('pointerdown', this.startPicking);
    this.renderer.domElement.removeEventListener('pointerup', this.finishPicking);
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
    this.renderer.domElement.remove();
    this.markers.forEach((marker) => marker.label.remove());
  }
}
