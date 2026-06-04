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
    thesisReferenceId: string | null;
    referenceDate: string | null;
    referenceTile: string | null;
    referenceMatchStatus:
      | "exact_id"
      | "same_date_tile"
      | "same_tile_near_date"
      | "alternative"
      | "not_found"
      | null;
    sceneSelectionReason: string | null;
    candidateCount: number | null;
    topCandidates: {
      itemId: string;
      date: string | null;
      tile: string | null;
      platform: string | null;
      cloudCover: number;
      estimatedCoverage: number;
      selectionScore: number;
      referenceMatchStatus: string;
    }[];
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
  coverage: null | {
    zoneAreaSqKm: number;
    rasterCoverageRatio: number;
    validPixelRatio: number;
    maskedPixelRatio: number;
    cloudMaskedPixelRatio: number;
    nodataPixelRatio: number;
    selectedSceneIntersectsZone: boolean;
    coverageWarning: string | null;
    methodNote: string;
  };
  interpretation: string | null;
  rasterLayers: RasterLayer[];
};

export type ComparisonChild = AnalysisResult & {
  year: number;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  stage: string;
  logs: string[];
  errorMessage: string | null;
};

export type ComparisonJob = {
  id: string;
  zoneSlug: string;
  zoneName: string;
  years: number[];
  status: "queued" | "running" | "partial" | "succeeded" | "failed";
  progress: number;
  stage: string;
  logs: string[];
  errorMessage: string | null;
  childAnalysisIds: Record<string, string>;
  children: Record<string, Job>;
  createdAt: string;
  updatedAt: string;
};

export type ComparisonRow = {
  metric: string;
  label: string;
  value2020: number | string | null;
  value2025: number | string | null;
  delta: number | null;
  percentChange: number | null;
  trend: "up" | "down" | "stable" | "changed" | "unknown";
};

export type ReferenceComparison = {
  title: string;
  note: string;
  rows: Record<string, unknown>[];
};

export type ComparisonResult = {
  comparisonId: string;
  zoneSlug: string;
  zoneName: string;
  years: number[];
  status: "queued" | "running" | "partial" | "succeeded" | "failed";
  children: Record<string, ComparisonChild>;
  comparisonTable: ComparisonRow[];
  warnings: string[];
  interpretation: string;
  referenceComparison: ReferenceComparison | null;
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

export type ReportCreated = {
  reportType: "analysis" | "comparison";
  id: string;
  status: "pending" | "queued" | "generating" | "ready" | "failed";
  pdfUrl: string | null;
  pdfPath: string | null;
  htmlPath: string | null;
  warnings: string[];
  errorMessage: string | null;
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function absoluteTileUrl(tileUrl: string): string {
  return tileUrl.startsWith("http") ? tileUrl : `${API_BASE}${tileUrl}`;
}

export function absoluteApiUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
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
    let detail: string | undefined;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      detail = parsed.detail;
    } catch {
      detail = undefined;
    }
    throw new Error(detail || text || `Ошибка API ${response.status}`);
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

export async function createComparison(
  zone: ZoneFeature
): Promise<{ comparisonId: string; childAnalysisIds: Record<string, string> }> {
  return request("/api/comparisons", {
    method: "POST",
    body: JSON.stringify({
      zoneSlug: zone.properties.slug,
      zoneName: zone.properties.name,
      geometry: zone.geometry,
      years: [2020, 2025],
      mode: "comparison",
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

export async function fetchComparison(comparisonId: string): Promise<ComparisonJob> {
  return request(`/api/comparisons/${comparisonId}`);
}

export async function fetchComparisonResult(comparisonId: string): Promise<ComparisonResult> {
  return request(`/api/comparisons/${comparisonId}/result`);
}

export async function createAnalysisReport(analysisId: string): Promise<ReportCreated> {
  return request(`/api/reports/analysis/${analysisId}`, {
    method: "POST"
  });
}

export async function createComparisonReport(comparisonId: string): Promise<ReportCreated> {
  return request(`/api/reports/comparison/${comparisonId}`, {
    method: "POST"
  });
}
