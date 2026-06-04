import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.core.database import Base, get_db
from app.main import app
from app.models.analysis import AnalysisJob, ReportJob
from app.services import job_queue
from app.worker_tasks import run_analysis_job_task


def _testing_session() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _geometry() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [39.58, 47.11],
                [39.82, 47.11],
                [39.82, 47.36],
                [39.58, 47.36],
                [39.58, 47.11],
            ]
        ],
    }


def test_dispatch_analysis_uses_rq_mode(monkeypatch) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class Settings:
        job_execution_mode = "rq"
        rq_analysis_timeout = 3600
        rq_default_timeout = 3600

    def fake_enqueue(function_path: str, *args: object, **kwargs: object) -> None:
        calls.append((function_path, args, kwargs))

    monkeypatch.setattr(job_queue, "get_settings", lambda: Settings())
    monkeypatch.setattr(job_queue, "enqueue_rq_job", fake_enqueue)

    job_queue.dispatch_analysis("analysis-id", 20)

    assert calls[0][0] == "app.worker_tasks.run_analysis_job_task"
    assert calls[0][1] == ("analysis-id", 20)
    assert calls[0][2]["job_kind"] == "analysis"


def test_queue_overload_returns_clear_error(monkeypatch) -> None:
    class Settings:
        queue_max_jobs = 1
        rq_default_timeout = 3600

    class FakeQueue:
        count = 1

        def enqueue(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise AssertionError("enqueue should not be called when queue is full")

    monkeypatch.setattr(job_queue, "get_settings", lambda: Settings())
    monkeypatch.setattr(job_queue, "get_queue", lambda: FakeQueue())

    try:
        job_queue.enqueue_rq_job(
            "app.worker_tasks.run_analysis_job_task",
            "analysis-id",
            job_kind="analysis",
        )
    except job_queue.QueueOverloadedError as exc:
        assert "Очередь перегружена" in str(exc)
    else:
        raise AssertionError("QueueOverloadedError was not raised")


def test_create_analysis_endpoint_enqueues_without_running(monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    dispatch_calls: list[tuple[str, float]] = []

    def fake_dispatch(analysis_id: str, cloud_cover_max: float) -> None:
        dispatch_calls.append((analysis_id, cloud_cover_max))

    monkeypatch.setattr(routes, "dispatch_analysis", fake_dispatch)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.post(
            "/api/analyses",
            json={
                "zoneSlug": "rostov_on_don",
                "zoneName": "Ростов-на-Дону",
                "geometry": _geometry(),
                "year": 2020,
                "mode": "single",
                "cloudCoverMax": 20,
                "isCustomZone": False,
            },
        )
        assert response.status_code == 200, response.text
        analysis_id = response.json()["analysisId"]
        assert dispatch_calls == [(analysis_id, 20)]

        db = TestingSessionLocal()
        try:
            job = db.get(AnalysisJob, analysis_id)
            assert job is not None
            assert job.status == "queued"
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_worker_task_calls_analysis_runner(monkeypatch) -> None:
    calls: list[tuple[str, float]] = []

    def fake_runner(analysis_id: str, cloud_cover_max: float) -> None:
        calls.append((analysis_id, cloud_cover_max))

    monkeypatch.setattr("app.worker_tasks.run_analysis_job", fake_runner)

    run_analysis_job_task("analysis-id", 15)

    assert calls == [("analysis-id", 15)]


def test_report_status_endpoint_returns_pending_before_generation() -> None:
    TestingSessionLocal = _testing_session()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.get("/api/reports/analysis/missing/status")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
    finally:
        app.dependency_overrides.clear()


def test_report_job_response_uses_ready_pdf_url(tmp_path: Path) -> None:
    report = ReportJob(
        id="analysis:analysis-id",
        report_type="analysis",
        subject_id="analysis-id",
        status="ready",
        pdf_path=str(tmp_path / "analysis-id.pdf"),
        html_path=str(tmp_path / "analysis-id.html"),
        warnings_json=json.dumps(["warning"], ensure_ascii=False),
    )

    response = routes._report_to_response(report)

    assert response["status"] == "ready"
    assert response["pdfUrl"] == "/api/reports/analysis/analysis-id.pdf"
    assert response["warnings"] == ["warning"]
