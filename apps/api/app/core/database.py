from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.effective_database_url,
    connect_args={
        "check_same_thread": False
    }
    if settings.effective_database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app.models.analysis import (  # noqa: F401, I001
        AnalysisJob,
        AnalysisResult,
        ComparisonJob,
        CoverageMetrics,
        RasterAsset,
        ReportJob,
        SceneMetadata,
    )

    Base.metadata.create_all(bind=engine)
    _ensure_scene_metadata_columns()


def _ensure_scene_metadata_columns() -> None:
    if not settings.effective_database_url.startswith("sqlite"):
        return

    columns = {
        "thesis_reference_id": "VARCHAR(260)",
        "reference_date": "VARCHAR(20)",
        "reference_tile": "VARCHAR(80)",
        "reference_match_status": "VARCHAR(40)",
        "scene_selection_reason": "TEXT",
        "candidate_count": "INTEGER",
        "top_candidates_json": "TEXT",
    }
    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(scene_metadata)")).fetchall()
        }
        for column, ddl_type in columns.items():
            if column not in existing:
                connection.execute(
                    text(f"ALTER TABLE scene_metadata ADD COLUMN {column} {ddl_type}")
                )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
