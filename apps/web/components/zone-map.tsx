"use client";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import { absoluteTileUrl, type RasterLayer, type ZoneFeature } from "@/lib/api";

const MAP_STYLE =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "https://demotiles.maplibre.org/style.json";

export function ZoneMap({
  zone,
  rasterLayer,
  opacity,
  selectedLayer,
  availableLayers,
  onLayerChange
}: {
  zone: ZoneFeature | undefined;
  rasterLayer: RasterLayer | undefined;
  opacity: number;
  selectedLayer: RasterLayer["layer"];
  availableLayers: RasterLayer["layer"][];
  onLayerChange: (layer: RasterLayer["layer"]) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [39.5, 47.35],
      zoom: 7,
      attributionControl: false
    });
    mapRef.current.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "Sentinel-2 L2A через Earth Search STAC"
      }),
      "bottom-right"
    );

    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !zone) {
      return;
    }

    const updateZone = () => {
      const source = map.getSource("zone") as maplibregl.GeoJSONSource | undefined;
      const data = {
        type: "FeatureCollection",
        features: [zone]
      };

      if (source) {
        source.setData(data as GeoJSON.FeatureCollection);
      } else {
        map.addSource("zone", { type: "geojson", data: data as GeoJSON.FeatureCollection });
        map.addLayer({
          id: "zone-fill",
          type: "fill",
          source: "zone",
          paint: {
            "fill-color": "#d79b39",
            "fill-opacity": 0.16
          }
        });
        map.addLayer({
          id: "zone-outline",
          type: "line",
          source: "zone",
          paint: {
            "line-color": "#f2c46d",
            "line-width": 3
          }
        });
      }

      map.fitBounds(
        [
          [zone.bbox[0], zone.bbox[1]],
          [zone.bbox[2], zone.bbox[3]]
        ],
        { padding: 80, duration: 700 }
      );
    };

    if (map.isStyleLoaded()) {
      updateZone();
    } else {
      map.once("load", updateZone);
    }
  }, [zone]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const updateRaster = () => {
      if (map.getLayer("analysis-raster-layer")) {
        map.removeLayer("analysis-raster-layer");
      }
      if (map.getSource("analysis-raster")) {
        map.removeSource("analysis-raster");
      }
      if (!rasterLayer) {
        return;
      }

      map.addSource("analysis-raster", {
        type: "raster",
        tiles: [absoluteTileUrl(rasterLayer.tileUrl)],
        tileSize: 256,
        bounds: rasterLayer.bounds
      });
      map.addLayer(
        {
          id: "analysis-raster-layer",
          type: "raster",
          source: "analysis-raster",
          paint: {
            "raster-opacity": opacity
          }
        },
        map.getLayer("zone-fill") ? "zone-fill" : undefined
      );
    };

    if (map.isStyleLoaded()) {
      updateRaster();
    } else {
      map.once("load", updateRaster);
    }
  }, [rasterLayer, opacity]);

  return (
    <div className="map-panel">
      <div className="map-toolbar">
        <div className="layer-tabs" aria-label="Слои анализа">
          {(["rgb", "ndvi", "ndwi", "ndbi"] as const).map((layer) => (
            <button
              className={`tab ${selectedLayer === layer ? "active" : ""}`}
              disabled={!availableLayers.includes(layer)}
              key={layer}
              onClick={() => onLayerChange(layer)}
              type="button"
            >
              {layer.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="map-caption">Методическая bbox-зона WGS84</div>
      </div>
      <div ref={containerRef} className="map-container" />
    </div>
  );
}
