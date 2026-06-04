import Link from "next/link";

const stack = [
  "Next.js",
  "FastAPI",
  "Sentinel-2 L2A",
  "Earth Search STAC",
  "rasterio",
  "MapLibre",
  "PostgreSQL/PostGIS",
  "Redis/RQ",
  "Docker/Caddy",
  "Playwright PDF"
];

const features = [
  "live Sentinel-2 analysis для стандартных зон дипломной методики",
  "растровые слои RGB, NDVI, NDWI и NDBI на карте анализа",
  "сравнение 2020 ↔ 2025 с parent job и дочерними расчетами",
  "метрики качества данных: покрытие зоны, валидные пиксели, облачность и nodata",
  "реальные PDF-отчеты по single analysis и comparison",
  "production deployment layer с Caddy, PostGIS, Redis и RQ worker"
];

export default function AboutPage() {
  return (
    <main className="info-page">
      <section className="info-hero">
        <Link href="/" className="back-link">
          Вернуться к панели мониторинга
        </Link>
        <h1>GeoEco Monitor как дипломный и portfolio MVP</h1>
        <p>
          Проект демонстрирует полный путь от спутниковых данных Sentinel-2 до публичного
          аналитического интерфейса, карты, comparison mode, PDF-отчета и production-ready
          архитектуры для VPS.
        </p>
      </section>

      <section className="info-section">
        <h2>Что реализовано</h2>
        <ul>
          {features.map((feature) => (
            <li key={feature}>{feature}</li>
          ))}
        </ul>
      </section>

      <section className="info-section">
        <h2>Технологии</h2>
        <div className="tech-list">
          {stack.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>

      <section className="info-section">
        <h2>Ограничения</h2>
        <p>
          Приложение не доказывает загрязнение и не формирует официальный нормативный класс. Оно
          показывает предварительный дистанционный сигнал, качество входных данных и зоны внимания
          для дальнейшего натурного или лабораторного обследования.
        </p>
      </section>

      <section className="info-section">
        <h2>Следующие улучшения</h2>
        <ul>
          <li>публичный деплой на VPS и финальный QA по реальной ссылке;</li>
          <li>полноценные пользовательские зоны после стабилизации демо-сценария;</li>
          <li>миграции production DB и расширенная observability для worker-очереди.</li>
        </ul>
      </section>
    </main>
  );
}
