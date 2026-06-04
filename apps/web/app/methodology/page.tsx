import Link from "next/link";

const indexCards = [
  {
    title: "NDVI",
    text: "Показывает спектральный сигнал растительности и помогает увидеть изменение зеленой массы."
  },
  {
    title: "NDWI",
    text: "Отражает воду и увлажнение поверхности, чувствителен к водным объектам и влажным зонам."
  },
  {
    title: "NDBI",
    text: "Используется как индикатор застроенных, минеральных и нарушенных поверхностей."
  }
];

export default function MethodologyPage() {
  return (
    <main className="info-page">
      <section className="info-hero">
        <Link href="/" className="back-link">
          Вернуться к панели мониторинга
        </Link>
        <h1>Методика предварительной дистанционной оценки</h1>
        <p>
          GeoEco Monitor использует сцены Sentinel-2 L2A, стандартные bbox-зоны дипломной методики
          и три спектральных индекса: NDVI, NDWI и NDBI. Итоговый класс является сравнительной
          предварительной оценкой, а не официальным экологическим заключением.
        </p>
      </section>

      <section className="info-grid">
        {indexCards.map((card) => (
          <article className="info-card" key={card.title}>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </article>
        ))}
      </section>

      <section className="info-section">
        <h2>Как формируется оценка</h2>
        <ol>
          <li>Для выбранной зоны выполняется STAC-поиск сцен Sentinel-2 L2A.</li>
          <li>Сцена ранжируется по покрытию зоны, облачности и совпадению с reference-сценой.</li>
          <li>Каналы Red, Green, Blue, NIR, SWIR и SCL приводятся к единой сетке.</li>
          <li>Облака, тени и невалидные пиксели исключаются через SCL mask.</li>
          <li>Рассчитываются NDVI, NDWI, NDBI, статистика и интегральный балл.</li>
          <li>Итоговый класс выбирается из четырех допустимых классов методики.</li>
        </ol>
      </section>

      <section className="info-section">
        <h2>Классы предварительной оценки</h2>
        <div className="class-list">
          <span>благоприятное</span>
          <span>удовлетворительное</span>
          <span>напряженное</span>
          <span>проблемное</span>
        </div>
      </section>

      <section className="info-disclaimer">
        Результат является предварительной дистанционной оценкой по спутниковым данным Sentinel-2 и
        не заменяет лабораторные измерения, санитарно-гигиеническую экспертизу и натурное
        обследование.
      </section>
    </main>
  );
}
