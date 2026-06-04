"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpenText,
  Download,
  FileText,
  FlaskConical,
  Gauge,
  GitCompare,
  Info,
  MapPinned,
  Play,
  Route,
  Satellite
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  absoluteApiUrl,
  createAnalysis,
  createAnalysisReport,
  createComparison,
  createComparisonReport,
  fetchComparison,
  fetchComparisonResult,
  fetchJob,
  fetchResult,
  fetchZones,
  type AnalysisResult,
  type ComparisonJob,
  type ComparisonResult,
  type Job,
  type RasterLayer,
  type ReportCreated
} from "@/lib/api";
import { ZoneMap } from "@/components/zone-map";

const statusLabels: Record<string, string> = {
  queued: "в очереди",
  running: "выполняется",
  partial: "частично готово",
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

function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function Dashboard() {
  const zonesQuery = useQuery({ queryKey: ["zones"], queryFn: fetchZones });
  const [zoneSlug, setZoneSlug] = useState("rostov_on_don");
  const [mode, setMode] = useState<"single" | "comparison">("single");
  const [year, setYear] = useState(2025);
  const [comparisonYear, setComparisonYear] = useState<2020 | 2025>(2025);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [comparisonId, setComparisonId] = useState<string | null>(null);
  const [selectedLayer, setSelectedLayer] = useState<RasterLayer["layer"]>("rgb");
  const [layerOpacity, setLayerOpacity] = useState(0.72);
  const [demoPrepared, setDemoPrepared] = useState(false);

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryComparisonId = params.get("comparisonId");
    if (!queryComparisonId) {
      return;
    }
    const queryYear = Number(params.get("comparisonYear"));
    setMode("comparison");
    setComparisonId(queryComparisonId);
    if (queryYear === 2020 || queryYear === 2025) {
      setComparisonYear(queryYear);
    }
  }, []);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedZone) {
        throw new Error("Зона еще не загружена.");
      }
      return createAnalysis(selectedZone, year);
    },
    onSuccess: (data) => {
      setAnalysisId(data.analysisId);
      setComparisonId(null);
      analysisReportMutation.reset();
      comparisonReportMutation.reset();
    }
  });

  const createComparisonMutation = useMutation({
    mutationFn: async () => {
      if (!selectedZone) {
        throw new Error("Зона еще не загружена.");
      }
      return createComparison(selectedZone);
    },
    onSuccess: (data) => {
      setComparisonId(data.comparisonId);
      setAnalysisId(null);
      setComparisonYear(2025);
      analysisReportMutation.reset();
      comparisonReportMutation.reset();
    }
  });

  const analysisReportMutation = useMutation<ReportCreated>({
    mutationFn: () => createAnalysisReport(analysisId as string)
  });

  const comparisonReportMutation = useMutation<ReportCreated>({
    mutationFn: () => createComparisonReport(comparisonId as string)
  });

  const jobQuery = useQuery<Job>({
    queryKey: ["job", analysisId],
    queryFn: () => fetchJob(analysisId as string),
    enabled: mode === "single" && Boolean(analysisId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 1800;
    }
  });

  const resultQuery = useQuery<AnalysisResult>({
    queryKey: ["result", analysisId],
    queryFn: () => fetchResult(analysisId as string),
    enabled: mode === "single" && jobQuery.data?.status === "succeeded"
  });

  const comparisonQuery = useQuery<ComparisonJob>({
    queryKey: ["comparison", comparisonId],
    queryFn: () => fetchComparison(comparisonId as string),
    enabled: mode === "comparison" && Boolean(comparisonId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "partial" || status === "failed" ? false : 1800;
    }
  });

  const comparisonResultQuery = useQuery<ComparisonResult>({
    queryKey: ["comparison-result", comparisonId],
    queryFn: () => fetchComparisonResult(comparisonId as string),
    enabled:
      mode === "comparison" &&
      Boolean(comparisonId) &&
      ["succeeded", "partial", "failed"].includes(comparisonQuery.data?.status ?? "")
  });

  const job = jobQuery.data;
  const comparison = comparisonQuery.data;
  const comparisonResult = comparisonResultQuery.data;
  const comparisonChild = comparisonResult?.children[String(comparisonYear)];
  const result = mode === "comparison" ? comparisonChild : resultQuery.data;
  const stats = result?.stats;
  const coverage = result?.coverage;
  const rasterLayers = useMemo(() => result?.rasterLayers ?? [], [result?.rasterLayers]);
  const availableLayerKeys = useMemo(
    () => rasterLayers.map((layer) => layer.layer),
    [rasterLayers]
  );
  const selectedRasterLayer = rasterLayers.find((layer) => layer.layer === selectedLayer);
  const activeMapYear = mode === "comparison" ? comparisonYear : year;
  const mapStatusText = selectedRasterLayer
    ? `На карте: ${activeMapYear} · ${layerLabels[selectedLayer]} · live-тайлы Sentinel-2`
    : rasterLayers.length > 0
      ? `Слой ${layerLabels[selectedLayer]} отсутствует для выбранного года. Выберите доступный слой.`
      : mode === "comparison" && comparison?.status === "running"
        ? "Слой появится после завершения child-расчета и подготовки тайлов."
        : "Слой появится после завершения расчета и подготовки тайлов.";
  const comparisonHighlights = useMemo(
    () => (comparisonResult ? buildComparisonHighlights(comparisonResult.comparisonTable) : []),
    [comparisonResult]
  );
  const canCreateAnalysisReport =
    mode === "single" &&
    Boolean(analysisId) &&
    job?.status === "succeeded" &&
    Boolean(resultQuery.data);
  const canCreateComparisonReport =
    mode === "comparison" &&
    Boolean(comparisonId) &&
    Boolean(comparisonResult) &&
    ["succeeded", "partial"].includes(comparison?.status ?? "");

  useEffect(() => {
    if (rasterLayers.length > 0 && !selectedRasterLayer) {
      setSelectedLayer(rasterLayers[0].layer);
    }
  }, [rasterLayers, selectedRasterLayer]);

  function prepareDemoScenario() {
    setZoneSlug("rostov_on_don");
    setMode("comparison");
    setComparisonYear(2025);
    setAnalysisId(null);
    setComparisonId(null);
    setSelectedLayer("rgb");
    setDemoPrepared(true);
    analysisReportMutation.reset();
    comparisonReportMutation.reset();
  }

  return (
    <main className="app-shell">
      <aside className="left-panel" aria-label="Панель управления расчетом">
        <div className="brand">
          <h1>GeoEco Monitor</h1>
          <p>
            Публичный аналитический дашборд предварительной дистанционной оценки территорий по
            Sentinel-2 L2A.
          </p>
          <nav className="product-links" aria-label="Навигация по проекту">
            <Link href="/methodology">
              <BookOpenText size={15} /> Методика
            </Link>
            <Link href="/about">
              <Info size={15} /> О проекте
            </Link>
          </nav>
        </div>

        <section className="intro-panel" aria-label="Краткое описание GeoEco Monitor">
          <h2>Что показывает панель</h2>
          <p>
            GeoEco Monitor рассчитывает NDVI, NDWI и NDBI по Sentinel-2 L2A, показывает качество
            данных, карту анализа, сравнение 2020 ↔ 2025 и PDF-отчет по дипломной методике.
          </p>
        </section>

        <section className="quick-start" aria-label="Быстрый старт">
          <h2>
            <Route size={17} /> Демо-сценарий
          </h2>
          <p>Ростов-на-Дону · сравнение 2020 ↔ 2025 · два live-расчета.</p>
          <button className="button secondary" onClick={prepareDemoScenario} type="button">
            <GitCompare size={17} />
            Подготовить демо-сценарий
          </button>
          {demoPrepared ? (
            <div className="demo-note">
              Параметры подготовлены. Нажмите “Запустить сравнение”, чтобы явно начать live-расчет.
            </div>
          ) : null}
        </section>

        <div className="field">
          <div className="field-label">Режим анализа</div>
          <div className="segmented" aria-label="Режим анализа">
            <button
              className={`mini-tab ${mode === "single" ? "active" : ""}`}
              onClick={() => setMode("single")}
              type="button"
            >
              Один год
            </button>
            <button
              className={`mini-tab ${mode === "comparison" ? "active" : ""}`}
              onClick={() => setMode("comparison")}
              type="button"
            >
              2020 ↔ 2025
            </button>
          </div>
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

        <div className="field" style={{ display: mode === "single" ? undefined : "none" }}>
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

        {mode === "comparison" ? (
          <div className="field">
            <label htmlFor="comparison-year">Год слоя на карте</label>
            <select
              className="select"
              id="comparison-year"
              value={comparisonYear}
              onChange={(event) => setComparisonYear(Number(event.target.value) as 2020 | 2025)}
            >
              <option value={2020}>2020</option>
              <option value={2025}>2025</option>
            </select>
            <div className="microcopy">
              Сравнение запускает два независимых дочерних расчета: 2020 и 2025.
            </div>
          </div>
        ) : null}

        <button
          className="button primary"
          type="button"
          disabled={
            !selectedZone ||
            createMutation.isPending ||
            createComparisonMutation.isPending ||
            job?.status === "running" ||
            comparison?.status === "running"
          }
          onClick={() => {
            if (mode === "comparison") {
              createComparisonMutation.mutate();
            } else {
              createMutation.mutate();
            }
          }}
        >
          {mode === "comparison" ? <GitCompare size={17} /> : <Play size={17} />}
          {mode === "comparison" ? "Запустить сравнение" : "Запустить расчет"}
        </button>

        {createMutation.error ? (
          <div className="error" style={{ marginTop: 14 }}>
            {createMutation.error.message}
          </div>
        ) : null}
        {createComparisonMutation.error ? (
          <div className="error" style={{ marginTop: 14 }}>
            {createComparisonMutation.error.message}
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
        statusText={mapStatusText}
        zone={selectedZone}
      />

      <aside className="right-panel" aria-label="Аналитическая панель">
        <section className="status-stack">
          <h2>
            <Activity size={18} /> {mode === "comparison" ? "Статус сравнения" : "Статус расчета"}
          </h2>
          {mode === "comparison" ? (
            <>
              <div className="metric">
                <span>Сравнение</span>
                <strong>{comparison ? statusLabels[comparison.status] : "не запускалось"}</strong>
                <div className="meta">
                  {comparison?.progress ?? 0}% · {comparison?.stage ?? "ожидание действия"}
                </div>
              </div>
              {([2020, 2025] as const).map((childYear) => {
                const child = comparison?.children[String(childYear)];
                return (
                  <div className="metric compact" key={childYear}>
                    <span>Дочерний расчет {childYear}</span>
                    <strong style={{ fontSize: 17 }}>
                      {child ? statusLabels[child.status] : "не создан"}
                    </strong>
                    <div className="meta">
                      {child?.progress ?? 0}% · {child?.stage ?? "ожидание запуска"}
                    </div>
                    {child?.errorMessage ? <div className="error">{child.errorMessage}</div> : null}
                  </div>
                );
              })}
              {(comparison?.logs ?? ["ожидание запуска"]).slice(-5).map((log) => (
                <div className="status-row" key={log}>
                  <span className={`dot ${log === comparison?.stage ? "active" : ""}`} />
                  <span>{log}</span>
                </div>
              ))}
              {comparison?.errorMessage ? (
                <div className="error">
                  <AlertTriangle size={16} /> {comparison.errorMessage}
                </div>
              ) : null}
            </>
          ) : (
            <>
              <div className="metric">
                <span>Состояние</span>
                <strong>{job ? statusLabels[job.status] : "не запускался"}</strong>
                <div className="meta">
                  {job?.progress ?? 0}% · {job?.stage ?? "ожидание действия"}
                </div>
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
            </>
          )}
        </section>

        {canCreateAnalysisReport ? (
          <ReportPanel
            buttonLabel="Сформировать PDF"
            error={analysisReportMutation.error?.message}
            isPending={analysisReportMutation.isPending}
            onGenerate={() => analysisReportMutation.mutate()}
            report={analysisReportMutation.data}
            readyLabel="Отчет готов"
          />
        ) : null}

        {canCreateComparisonReport ? (
          <ReportPanel
            buttonLabel="Сформировать PDF сравнения"
            error={comparisonReportMutation.error?.message}
            isPending={comparisonReportMutation.isPending}
            onGenerate={() => comparisonReportMutation.mutate()}
            report={comparisonReportMutation.data}
            readyLabel="Отчет сравнения готов"
          />
        ) : null}

        {mode === "comparison" ? (
          <section className="cards comparison-summary" style={{ marginTop: 18 }}>
            <h2>
              <BarChart3 size={18} /> Кратко по сравнению
            </h2>
            <div className="metric compact">
              <span>Выбранный год на карте</span>
              <strong style={{ fontSize: 18 }}>{comparisonYear}</strong>
              <div className="meta">Слой: {layerLabels[selectedLayer]}</div>
            </div>
            {comparisonHighlights.length > 0 ? (
              comparisonHighlights.map((highlight) => (
                <div className="summary-chip" key={highlight}>
                  {highlight}
                </div>
              ))
            ) : (
              <div className="meta">
                Краткий итог появится после завершения сравнения. Выводы остаются
                предварительными и дистанционными.
              </div>
            )}
          </section>
        ) : null}

        <section className="status-stack" style={{ marginTop: 18 }}>
          <h2>
            <Satellite size={18} /> Сцена Sentinel-2
          </h2>
          <div className="meta">ID: {result?.scene?.stacItemId ?? "—"}</div>
          <div className="meta">Дата: {result?.scene?.datetime ?? "—"}</div>
          <div className="meta">Облачность: {formatNumber(result?.scene?.cloudCover, 1)}%</div>
          <div className="meta">Тайл: {result?.scene?.tileId ?? "—"}</div>
          <div className="meta">Reference дата: {result?.scene?.referenceDate ?? "—"}</div>
          <div className="meta">Reference тайл: {result?.scene?.referenceTile ?? "—"}</div>
          <div className="meta">Кандидатов STAC: {result?.scene?.candidateCount ?? "—"}</div>
          {result?.scene?.sceneSelectionReason ? (
            <div className="meta">{result.scene.sceneSelectionReason}</div>
          ) : null}
          {result?.scene?.referenceNote &&
          result.scene.referenceNote !== result.scene.sceneSelectionReason ? (
            <div
              className={
                result.scene.referenceMatchStatus === "exact_id" ||
                result.scene.referenceMatchStatus === "same_date_tile"
                  ? "meta"
                  : "error"
              }
            >
              {result.scene.referenceNote}
            </div>
          ) : null}
        </section>

        <section className="cards" style={{ marginTop: 18 }}>
          <h2>
            <Gauge size={18} /> Качество данных
          </h2>
          <div className="metric">
            <span>Покрытие зоны сценой</span>
            <strong>{formatPercent(coverage?.rasterCoverageRatio)}</strong>
            <div className="meta">Площадь зоны: {formatNumber(coverage?.zoneAreaSqKm, 1)} км²</div>
          </div>
          <div className="metric">
            <span>Валидные пиксели</span>
            <strong>{formatPercent(coverage?.validPixelRatio)}</strong>
            <div className="meta">Маскированные пиксели: {formatPercent(coverage?.maskedPixelRatio)}</div>
          </div>
          <div className="metric">
            <span>Облака и тени по SCL</span>
            <strong>{formatPercent(coverage?.cloudMaskedPixelRatio)}</strong>
            <div className="meta">Nodata: {formatPercent(coverage?.nodataPixelRatio)}</div>
          </div>
          <div className="meta">Облачность сцены: {formatNumber(result?.scene?.cloudCover, 1)}%</div>
          {coverage?.coverageWarning ? (
            <div className="error">
              <AlertTriangle size={16} /> Данные требуют осторожной интерпретации:{" "}
              {coverage.coverageWarning}.
            </div>
          ) : (
            <div className="meta">Критичных предупреждений по покрытию не выявлено.</div>
          )}
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
              "После live-расчета здесь появится интерпретация по правилам методики без утверждений о доказанном загрязнении."}
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
          {comparisonResultQuery.error ? (
            <div className="error">{comparisonResultQuery.error.message}</div>
          ) : null}
        </section>
      </aside>

      <section className="bottom-panel">
        <div className="bottom-grid">
          <SummaryItem icon={<MapPinned size={17} />} label="Граница" value="bbox методики WGS84" />
          <SummaryItem label="Исходный балл" value={formatNumber(stats?.rawScore, 4)} />
          <SummaryItem
            label="Валидные пиксели"
            value={formatPercent(coverage?.validPixelRatio ?? stats?.validPixelRatio)}
          />
          <SummaryItem label="Источник" value="Earth Search STAC / Sentinel-2 L2A" />
        </div>
        {mode === "comparison" && comparisonResult ? (
          <div className="comparison-panel">
            <div>
              <h2>
                <BarChart3 size={18} /> Сравнение 2020 ↔ 2025
              </h2>
              <p className="meta">{comparisonResult.interpretation}</p>
              {comparisonResult.warnings.map((warning) => (
                <div className="error" key={warning}>
                  <AlertTriangle size={16} /> {warning}
                </div>
              ))}
            </div>
            <ComparisonBars rows={comparisonResult.comparisonTable} />
            <ComparisonTable rows={comparisonResult.comparisonTable} />
            {comparisonResult.referenceComparison ? (
              <div className="limitations">
                <strong>{comparisonResult.referenceComparison.title}</strong>
                <div>{comparisonResult.referenceComparison.note}</div>
              </div>
            ) : null}
          </div>
        ) : null}
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

function ReportPanel({
  buttonLabel,
  error,
  isPending,
  onGenerate,
  readyLabel,
  report
}: {
  buttonLabel: string;
  error?: string;
  isPending: boolean;
  onGenerate: () => void;
  readyLabel: string;
  report?: ReportCreated;
}) {
  return (
    <section className="cards report-panel" style={{ marginTop: 18 }}>
      <h2>
        <FileText size={18} /> PDF-отчет
      </h2>
      <button className="button primary" disabled={isPending} onClick={onGenerate} type="button">
        <FileText size={17} />
        {isPending ? "Формируем PDF" : buttonLabel}
      </button>
      <div className="report-steps" aria-label="Статус подготовки PDF">
        <div className={`status-row ${isPending ? "active-report-step" : ""}`}>
          <span className={`dot ${isPending ? "active" : ""}`} />
          <span>{isPending ? "Готовим отчет" : "Ожидание команды"}</span>
        </div>
        <div className={`status-row ${isPending ? "active-report-step" : ""}`}>
          <span className={`dot ${isPending ? "active" : ""}`} />
          <span>Генерируем изображения слоев</span>
        </div>
        <div className={`status-row ${isPending ? "active-report-step" : ""}`}>
          <span className={`dot ${isPending ? "active" : ""}`} />
          <span>
            {isPending
              ? "Формируем PDF"
              : report?.status === "queued"
                ? "PDF поставлен в очередь"
                : report?.status === "generating"
                  ? "PDF формируется worker-ом"
                  : report?.status === "failed"
                    ? "PDF не сформирован"
                    : report?.status === "ready"
                      ? readyLabel
                      : "PDF еще не сформирован"}
          </span>
        </div>
      </div>
      {report?.status === "ready" && report.pdfUrl ? (
        <>
          <a className="download-link" href={absoluteApiUrl(report.pdfUrl)} rel="noreferrer" target="_blank">
            <Download size={17} /> Скачать PDF
          </a>
          {report.warnings.length > 0 ? (
            <div className="limitations">
              {report.warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      {report?.status === "failed" && report.errorMessage ? (
        <div className="error">{report.errorMessage}</div>
      ) : null}
      {error ? <div className="error">{error}</div> : null}
    </section>
  );
}

function ComparisonBars({ rows }: { rows: ComparisonResult["comparisonTable"] }) {
  const chartRows = rows.filter((row) =>
    ["meanNDVI", "meanNDWI", "meanNDBI", "normalizedScore"].includes(row.metric)
  );
  return (
    <div className="bar-chart" aria-label="Группированная диаграмма сравнения">
      {chartRows.map((row) => (
        <div className="bar-row" key={row.metric}>
          <div className="bar-label">{row.label}</div>
          <div className="bar-track">
            <span className="bar y2020" style={{ width: `${barWidth(row.metric, row.value2020)}%` }} />
            <span className="bar y2025" style={{ width: `${barWidth(row.metric, row.value2025)}%` }} />
          </div>
          <div className="bar-values">
            <span>2020: {formatCellValue(row.metric, row.value2020)}</span>
            <span>2025: {formatCellValue(row.metric, row.value2025)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ComparisonTable({ rows }: { rows: ComparisonResult["comparisonTable"] }) {
  return (
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead>
          <tr>
            <th>Показатель</th>
            <th>2020</th>
            <th>2025</th>
            <th>Δ</th>
            <th>%</th>
            <th>Тренд</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metric}>
              <td>{row.label}</td>
              <td>{formatCellValue(row.metric, row.value2020)}</td>
              <td>{formatCellValue(row.metric, row.value2025)}</td>
              <td>{formatNumber(row.delta)}</td>
              <td>{row.percentChange === null ? "—" : `${row.percentChange.toFixed(1)}%`}</td>
              <td>{trendLabel(row.trend)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCellValue(metric: string, value: number | string | null) {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (metric === "validPixelRatio" || metric === "rasterCoverageRatio") {
    return formatPercent(value);
  }
  return formatNumber(value);
}

function trendLabel(trend: string) {
  const labels: Record<string, string> = {
    up: "рост",
    down: "снижение",
    stable: "стабильно",
    changed: "изменился",
    unknown: "нет данных"
  };
  return labels[trend] ?? trend;
}

function buildComparisonHighlights(rows: ComparisonResult["comparisonTable"]) {
  const byMetric = Object.fromEntries(rows.map((row) => [row.metric, row]));
  const highlights: string[] = [];
  const ndvi = byMetric.meanNDVI;
  const ndbi = byMetric.meanNDBI;
  const classRow = byMetric.classLabel;

  if (typeof ndvi?.delta === "number") {
    highlights.push(`NDVI ${ndvi.delta < 0 ? "снизился" : "вырос"} на ${Math.abs(ndvi.delta).toFixed(3)}`);
  }
  if (typeof ndbi?.delta === "number") {
    highlights.push(`NDBI ${ndbi.delta < 0 ? "снизился" : "вырос"} на ${Math.abs(ndbi.delta).toFixed(3)}`);
  }
  if (
    typeof classRow?.value2020 === "string" &&
    typeof classRow?.value2025 === "string" &&
    classRow.value2020 !== classRow.value2025
  ) {
    highlights.push(`Класс изменился: ${classRow.value2020} -> ${classRow.value2025}`);
  }
  return highlights;
}

function barWidth(metric: string, value: number | string | null) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  if (metric === "normalizedScore") {
    return Math.max(0, Math.min(100, value * 100));
  }
  return Math.max(0, Math.min(100, ((value + 1) / 2) * 100));
}
