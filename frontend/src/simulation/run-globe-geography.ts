import * as THREE from 'three';
import { feature } from 'topojson-client';
import topology from 'world-atlas/countries-110m.json';
import type { Feature, FeatureCollection, Geometry, MultiPolygon, Polygon } from 'geojson';

type CountryProperties = { name?: string };

const countryAliases: Record<string, string> = {
  'united states': 'united states of america',
  'russian federation': 'russia',
  'democratic republic of the congo': 'dem rep congo',
  'republic of the congo': 'congo',
  'south korea': 'south korea',
  'north korea': 'north korea',
};

const normalizedName = (value: string): string =>
  value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/gi, ' ')
    .trim()
    .toLowerCase();

const countries = feature(
  topology as never,
  topology.objects.countries as never,
) as unknown as FeatureCollection<Geometry, CountryProperties>;

const countryByName = new Map<string, Feature<Geometry, CountryProperties>>();
for (const country of countries.features) {
  const name = normalizedName(country.properties?.name ?? '');
  if (name) countryByName.set(name, country);
}

const globePosition = (latitude: number, longitude: number, radius: number): THREE.Vector3 => {
  const phi = THREE.MathUtils.degToRad(latitude);
  const theta = THREE.MathUtils.degToRad(longitude);
  return new THREE.Vector3(
    radius * Math.cos(phi) * Math.sin(theta),
    radius * Math.sin(phi),
    radius * Math.cos(phi) * Math.cos(theta),
  );
};

const unwrappedRing = (ring: number[][]): THREE.Vector2[] => {
  const result: THREE.Vector2[] = [];
  let previous: number | undefined;
  for (const coordinate of ring.slice(0, -1)) {
    let longitude = coordinate[0] ?? 0;
    const latitude = coordinate[1] ?? 0;
    if (previous !== undefined) {
      while (longitude - previous > 180) longitude -= 360;
      while (longitude - previous < -180) longitude += 360;
    }
    previous = longitude;
    result.push(new THREE.Vector2(longitude, latitude));
  }
  return result;
};

const polygonTriangles = (polygon: number[][][]): number[] => {
  if (!polygon.length) return [];
  const contour = unwrappedRing(polygon[0] ?? []);
  const holes = polygon.slice(1).map(unwrappedRing);
  if (contour.length < 3) return [];
  const vertices = [...contour, ...holes.flat()];
  const triangles = THREE.ShapeUtils.triangulateShape(contour, holes);
  const positions: number[] = [];
  for (const triangle of triangles) {
    for (const index of triangle) {
      const vertex = vertices[index]!;
      positions.push(...globePosition(vertex.y, vertex.x, 1.006).toArray());
    }
  }
  return positions;
};

const geometryPolygons = (geometry: Polygon | MultiPolygon): number[][][][] =>
  geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;

export const countrySurfaceGeometry = (countryName: string): THREE.BufferGeometry | null => {
  const requested = normalizedName(countryName);
  const resolved = countryAliases[requested] ?? requested;
  const country = countryByName.get(resolved);
  if (!country || (country.geometry.type !== 'Polygon' && country.geometry.type !== 'MultiPolygon'))
    return null;
  const positions = geometryPolygons(country.geometry).flatMap(polygonTriangles);
  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  return geometry;
};
