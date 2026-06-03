export type ZoneFeature = {
  type: "Feature";
  properties: {
    slug: string;
    name: string;
    zoneType: string;
    boundarySource: string;
    bbox: [number, number, number, number];
  };
  bbox: [number, number, number, number];
  geometry: GeoJSON.Polygon;
};

export type Job = {
  id: string;
  zoneSlug: string;
  zoneName: string;
  year: number;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  stage: string;
  logs: string[];
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AnalysisResult = {
  analysisId: string;
  scene: null | {
    stacItemId: string;
    collection: string;
    datetime: string;
    cloudCover: number | null;
    tileId: string | null;
    referenceSceneId: string | null;
    referenceSceneFound: boolean;
    referenceNote: string | null;
  };
  stats: null | {
    meanNDVI: number;
    meanNDWI: number;
    meanNDBI: number;
    medianNDVI: number;
    medianNDWI: number;
    medianNDBI: number;
    validPixelRatio: number;
    rawScore: number;
    normalizedScore: number;
    classLabel: "благоприятное" | "удовлетворительное" | "напряженное" | "проблемное";
  };
  interpretation: string | null;
  rasterLayers: RasterLayer[];
};

export type RasterLayer = {
  analysisId: string;
  layer: "rgb" | "ndvi" | "ndwi" | "ndbi";
  path: string;
  min: number | null;
  max: number | null;
  nodata: number | null;
  crs: string;
  bounds: [number, number, number, number];
  tileUrl: string;
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function absoluteTileUrl(tileUrl: string): string {
  return tileUrl.startsWith("http") ? tileUrl : `${API_BASE}${tileUrl}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Ошибка API ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchZones(): Promise<{ features: ZoneFeature[] }> {
  return request("/api/zones/defaults");
}

export async function createAnalysis(zone: ZoneFeature, year: number): Promise<{ analysisId: string }> {
  return request("/api/analyses", {
    method: "POST",
    body: JSON.stringify({
      zoneSlug: zone.properties.slug,
      zoneName: zone.properties.name,
      geometry: zone.geometry,
      year,
      mode: "single",
      cloudCoverMax: 20,
      isCustomZone: false
    })
  });
}

export async function fetchJob(analysisId: string): Promise<Job> {
  return request(`/api/analyses/${analysisId}`);
}

export async function fetchResult(analysisId: string): Promise<AnalysisResult> {
  return request(`/api/analyses/${analysisId}/result`);
}
