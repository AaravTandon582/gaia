"use client";

import { useEffect } from "react";
import type L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { regionFromClick, type RegionSelection } from "@/lib/region";
import type { CatalogRegion } from "@/lib/api";

type RegionMapProps = {
  region: RegionSelection | null;
  regions: CatalogRegion[];
  onSelect: (region: RegionSelection) => void;
  onMapReady?: (map: L.Map) => void;
};

function MapReady({ onMapReady }: { onMapReady: (map: L.Map) => void }) {
  const map = useMap();
  useEffect(() => {
    onMapReady(map);
  }, [map, onMapReady]);
  return null;
}

function ClickToSelect({ onSelect }: { onSelect: RegionMapProps["onSelect"] }) {
  useMapEvents({
    click(event) {
      onSelect(regionFromClick(event.latlng.lat, event.latlng.lng));
    },
  });

  return null;
}

function FrameRegion({ region }: { region: RegionSelection | null }) {
  const map = useMap();

  useEffect(() => {
    if (!region) {
      return;
    }

    map.fitBounds(
      [
        [region.bounds.south, region.bounds.west],
        [region.bounds.north, region.bounds.east],
      ],
      { padding: [28, 28], maxZoom: 5 },
    );
  }, [map, region]);

  return null;
}

export default function RegionMap({
  region,
  regions,
  onSelect,
  onMapReady,
}: RegionMapProps) {
  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      minZoom={2}
      worldCopyJump
      className="h-full w-full cursor-crosshair"
    >
      <TileLayer
        attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
      />
      {regions.map((item) => <Rectangle key={item.id}
        bounds={[[item.bounds.south, item.bounds.west], [item.bounds.north, item.bounds.east]]}
        pathOptions={{ color: "#38bdf8", weight: 1, fillOpacity: 0.08 }}
        interactive={false}
      ><Tooltip permanent direction="center">{item.name}</Tooltip></Rectangle>)}
      <ClickToSelect onSelect={onSelect} />
      {onMapReady ? <MapReady onMapReady={onMapReady} /> : null}
      <FrameRegion region={region} />
      {region ? (
        <>
          <Rectangle
            interactive={false}
            bounds={[
              [region.bounds.south, region.bounds.west],
              [region.bounds.north, region.bounds.east],
            ]}
            pathOptions={{
              color: "#4da3ff",
              weight: 2,
              fillColor: "#4da3ff",
              fillOpacity: 0.18,
            }}
          />
          <CircleMarker
            interactive={false}
            center={[region.lat, region.lon]}
            radius={5}
            pathOptions={{
              color: "#e8f1f8",
              weight: 2,
              fillColor: "#4da3ff",
              fillOpacity: 1,
            }}
          />
        </>
      ) : null}
    </MapContainer>
  );
}
