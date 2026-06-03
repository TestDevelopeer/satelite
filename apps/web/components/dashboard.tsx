"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, FlaskConical, MapPinned, Play, Satellite } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createAnalysis,
  fetchJob,
  fetchResult,
  fetchZones,
  type AnalysisResult,
  type Job,
  type RasterLayer
} from "@/lib/api";
import { ZoneMap } from "@/components/zone-map";

const statusLabels: Record<string, string> = {
  queued: "в очереди",
  running: "выполняется",
  succeeded: "готово",
  failed: "ошибка"
};

const layerLabels: Record<RasterLayer["layer"], string> = {
  rgb: "RGB",
  ndvi: "NDVI",
  ndwi: "NDWI",
  ndbi: "NDBI"
};

const legends: Record<RasterLayer["layer"], { label: string; color: string }[]> = {
  rgb: [
    { label: "Натуральные цвета", color: "#d8d2bd" },
    { label: "Валидные пиксели Sentinel-2", color: "#6e8f7c" }
  ],
  ndvi: [
    { label: "низкая растительность", color: "#79502f" },
    { label: "умеренная", color: "#d6ae4d" },
    { label: "высокая", color: "#8ebf55" },
    { label: "очень высокая", color: "#006837" }
  ],
  ndwi: [
    { label: "сухие/застроенные", color: "#744c2b" },
    { label: "слабое увлажнение", color: "#8fc7be" },
    { label: "вода/увлажнение", color: "#054861" }
  ],
  ndbi: [
    { label: "низкая застройка/минеральность", color: "#257056" },
    { label: "смешанные поверхности", color: "#efda8b" },
    { label: "высокая застройка/открытый грунт", color: "#8c3326" }
  ]
};

function formatNumber(value: number | null | undefined, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

export function Dashboard() {
  const zonesQuery = useQuery({ queryKey: ["zones"], queryFn: fetchZones });
  const [zoneSlug, setZoneSlug] = useState("rostov_on_don");
  const [year, setYear] = useState(2025);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [selectedLayer, setSelectedLayer] = useState<RasterLayer["layer"]>("rgb");
  const [layerOpacity, setLayerOpacity] = useState(0.72);

  const zones = useMemo(() => zonesQuery.data?.features ?? [], [zonesQuery.data?.features]);
  const selectedZone = useMemo(
    () => zones.find((zone) => zone.properties.slug === zoneSlug) ?? zones[0],
    [zoneSlug, zones]
  );

  useEffect(() => {
    if (!selectedZone && zones[0]) {
      setZoneSlug(zones[0].properties.slug);
    }
  }, [selectedZone, zones]);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedZone) {
        throw new Error("Зона еще не загружена.");
      }
      return createAnalysis(selectedZone, year);
    },
    onSuccess: (data) => setAnalysisId(data.analysisId)
  });

  const jobQuery = useQuery<Job>({
    queryKey: ["job", analysisId],
    queryFn: () => fetchJob(analysisId as string),
    enabled: Boolean(analysisId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 1800;
    }
  });

  const resultQuery = useQuery<AnalysisResult>({
    queryKey: ["result", analysisId],
    queryFn: () => fetchResult(analysisId as string),
    enabled: jobQuery.data?.status === "succeeded"
  });

  const job = jobQuery.data;
  const result = resultQuery.data;
  const stats = result?.stats;
  const rasterLayers = useMemo(() => result?.rasterLayers ?? [], [result?.rasterLayers]);
  const availableLayerKeys = useMemo(
    () => rasterLayers.map((layer) => layer.layer),
    [rasterLayers]
  );
  const selectedRasterLayer = rasterLayers.find((layer) => layer.layer === selectedLayer);

  useEffect(() => {
    if (rasterLayers.length > 0 && !selectedRasterLayer) {
      setSelectedLayer(rasterLayers[0].layer);
    }
  }, [rasterLayers, selectedRasterLayer]);

  return (
    <main className="app-shell">
      <aside className="left-panel" aria-label="Панель управления расчетом">
        <div className="brand">
          <h1>GeoEco Monitor</h1>
          <p>Публичный аналитический дашборд предварительной дистанционной оценки по Sentinel-2.</p>
        </div>

        <div className="field">
          <label htmlFor="zone">Территория анализа</label>
          <select
            className="select"
            id="zone"
            value={zoneSlug}
            onChange={(event) => setZoneSlug(event.target.value)}
          >
            {zones.map((zone) => (
              <option key={zone.properties.slug} value={zone.properties.slug}>
                {zone.properties.name}
              </option>
            ))}
          </select>
          <div className="microcopy">{selectedZone?.properties.zoneType ?? "Загрузка зон..."}</div>
        </div>

        <div className="field">
          <label htmlFor="year">Год анализа</label>
          <select
            className="select"
            id="year"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          >
            <option value={2020}>2020</option>
            <option value={2025}>2025</option>
          </select>
          <div className="microcopy">Период по умолчанию: 1 июня — 15 сентября.</div>
        </div>

        <button
          className="button primary"
          type="button"
          disabled={!selectedZone || createMutation.isPending || job?.status === "running"}
          onClick={() => createMutation.mutate()}
        >
          <Play size={17} />
          Запустить расчет
        </button>

        {createMutation.error ? (
          <div className="error" style={{ marginTop: 14 }}>
            {createMutation.error.message}
          </div>
        ) : null}

        <div className="field" style={{ marginTop: 18 }}>
          <div className="field-label">Растровый слой</div>
          <div className="layer-grid" aria-label="Переключатель растровых слоев">
            {(["rgb", "ndvi", "ndwi", "ndbi"] as const).map((layer) => (
              <button
                className={`mini-tab ${selectedLayer === layer ? "active" : ""}`}
                disabled={!availableLayerKeys.includes(layer)}
                key={layer}
                onClick={() => setSelectedLayer(layer)}
                type="button"
              >
                {layerLabels[layer]}
              </button>
            ))}
          </div>
          <div className="microcopy">
            {rasterLayers.length > 0
              ? "Слои построены из live Sentinel-2 расчета."
              : "Растровые слои появятся после успешного live-расчета."}
          </div>
        </div>

        <div className="field">
          <label htmlFor="opacity">Прозрачность слоя: {Math.round(layerOpacity * 100)}%</label>
          <input
            id="opacity"
            max="1"
            min="0"
            onChange={(event) => setLayerOpacity(Number(event.target.value))}
            step="0.05"
            type="range"
            value={layerOpacity}
          />
        </div>

        <div className="limitations" style={{ marginTop: 18 }}>
          Результат является предварительной дистанционной оценкой по спутниковым данным Sentinel-2 и
          не заменяет лабораторные измерения, санитарно-гигиеническую экспертизу и натурное
          обследование.
        </div>
      </aside>

      <ZoneMap
        availableLayers={availableLayerKeys}
        onLayerChange={setSelectedLayer}
        opacity={layerOpacity}
        rasterLayer={selectedRasterLayer}
        selectedLayer={selectedLayer}
        zone={selectedZone}
      />

      <aside className="right-panel" aria-label="Аналитическая панель">
        <section className="status-stack">
          <h2>
            <Activity size={18} /> Статус расчета
          </h2>
          <div className="metric">
            <span>Состояние</span>
            <strong>{job ? statusLabels[job.status] : "не запускался"}</strong>
            <div className="meta">{job?.progress ?? 0}% · {job?.stage ?? "ожидание действия"}</div>
          </div>
          {(job?.logs ?? ["ожидание запуска"]).slice(-7).map((log) => (
            <div className="status-row" key={log}>
              <span className={`dot ${log === job?.stage ? "active" : ""}`} />
              <span>{log}</span>
            </div>
          ))}
          {job?.errorMessage ? (
            <div className="error">
              <AlertTriangle size={16} /> {job.errorMessage}
            </div>
          ) : null}
        </section>

        <section className="status-stack" style={{ marginTop: 18 }}>
          <h2>
            <Satellite size={18} /> Сцена Sentinel-2
          </h2>
          <div className="meta">ID: {result?.scene?.stacItemId ?? "—"}</div>
          <div className="meta">Дата: {result?.scene?.datetime ?? "—"}</div>
          <div className="meta">Облачность: {formatNumber(result?.scene?.cloudCover, 1)}%</div>
          <div className="meta">Тайл: {result?.scene?.tileId ?? "—"}</div>
          {result?.scene?.referenceNote ? <div className="error">{result.scene.referenceNote}</div> : null}
        </section>

        <section className="cards" style={{ marginTop: 18 }}>
          <h2>
            <FlaskConical size={18} /> Индексы и класс
          </h2>
          <Metric label="NDVI" value={stats?.meanNDVI} />
          <Metric label="NDWI" value={stats?.meanNDWI} />
          <Metric label="NDBI" value={stats?.meanNDBI} />
          <div className="metric">
            <span>Итоговый предварительный класс</span>
            <strong className="class-badge">{stats?.classLabel ?? "—"}</strong>
            <div className="meta">Нормированная оценка: {formatNumber(stats?.normalizedScore)}</div>
          </div>
        </section>

        <section className="explain" style={{ marginTop: 18 }}>
          <h2>Интерпретация</h2>
          <p className="meta">
            {result?.interpretation ??
              "После live-расчета здесь появится rule-based интерпретация без утверждений о доказанном загрязнении."}
          </p>
        </section>

        <section className="explain" style={{ marginTop: 18 }}>
          <h2>Легенда слоя {layerLabels[selectedLayer]}</h2>
          <div className="legend-list">
            {legends[selectedLayer].map((item) => (
              <div className="legend-item" key={item.label}>
                <span className="legend-color" style={{ background: item.color }} />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
          {resultQuery.error ? <div className="error">{resultQuery.error.message}</div> : null}
        </section>
      </aside>

      <section className="bottom-panel">
        <div className="bottom-grid">
          <SummaryItem icon={<MapPinned size={17} />} label="Граница" value="bbox методики WGS84" />
          <SummaryItem label="Raw score" value={formatNumber(stats?.rawScore, 4)} />
          <SummaryItem
            label="Валидные пиксели"
            value={`${formatNumber(stats?.validPixelRatio ? stats.validPixelRatio * 100 : undefined, 1)}%`}
          />
          <SummaryItem label="Источник" value="Earth Search STAC / Sentinel-2 L2A" />
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="metric">
      <span>{label}, среднее значение</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}

function SummaryItem({
  icon,
  label,
  value
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="metric">
      <span>
        {icon} {label}
      </span>
      <strong style={{ fontSize: 16 }}>{value}</strong>
    </div>
  );
}
