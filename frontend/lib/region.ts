export const REGION_HALF_SPAN = 5;

export type RegionBounds = {
  south: number;
  north: number;
  west: number;
  east: number;
};

export type RegionSelection = {
  lat: number;
  lon: number;
  bounds: RegionBounds;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function regionFromClick(
  lat: number,
  lon: number,
  halfSpan = REGION_HALF_SPAN,
): RegionSelection {
  lat = clamp(lat, -85, 85);
  lon = ((lon + 180) % 360 + 360) % 360 - 180;
  return {
    lat,
    lon,
    bounds: {
      south: clamp(lat - halfSpan, -90, 90),
      north: clamp(lat + halfSpan, -90, 90),
      west: clamp(lon - halfSpan, -180, 180),
      east: clamp(lon + halfSpan, -180, 180),
    },
  };
}

export function formatCoord(value: number, positive: string, negative: string) {
  const hemisphere = value >= 0 ? positive : negative;
  return `${Math.abs(value).toFixed(2)}°${hemisphere}`;
}
