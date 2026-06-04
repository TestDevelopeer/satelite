import json

from app.core.database import SessionLocal
from app.models.analysis import ReportJob
from app.services.analysis_runner import run_analysis_job
from app.services.comparison import run_comparison_job
from app.services.reports import ReportError, ensure_analysis_report, ensure_comparison_report


def run_analysis_job_task(analysis_id: str, cloud_cover_max: float) -> None:
    run_analysis_job(analysis_id, cloud_cover_max)


def run_comparison_job_task(comparison_id: str, cloud_cover_max: float) -> None:
    run_comparison_job(comparison_id, cloud_cover_max)


def generate_analysis_report_task(report_job_id: str, analysis_id: str) -> None:
    db = SessionLocal()
    try:
        report = _mark_report(db, report_job_id, status="generating", error_message=None)
        artifact = ensure_analysis_report(db, analysis_id)
        report.status = "ready"
        report.pdf_path = str(artifact.pdf_path)
        report.html_path = str(artifact.html_path)
        report.warnings_json = json.dumps(artifact.warnings, ensure_ascii=False)
        db.add(report)
        db.commit()
    except ReportError as exc:
        _fail_report(db, report_job_id, exc.detail)
    except Exception as exc:  # noqa: BLE001
        _fail_report(db, report_job_id, str(exc))
    finally:
        db.close()


def generate_comparison_report_task(report_job_id: str, comparison_id: str) -> None:
    db = SessionLocal()
    try:
        report = _mark_report(db, report_job_id, status="generating", error_message=None)
        artifact = ensure_comparison_report(db, comparison_id)
        report.status = "ready"
        report.pdf_path = str(artifact.pdf_path)
        report.html_path = str(artifact.html_path)
        report.warnings_json = json.dumps(artifact.warnings, ensure_ascii=False)
        db.add(report)
        db.commit()
    except ReportError as exc:
        _fail_report(db, report_job_id, exc.detail)
    except Exception as exc:  # noqa: BLE001
        _fail_report(db, report_job_id, str(exc))
    finally:
        db.close()


def _mark_report(
    db,
    report_job_id: str,
    *,
    status: str,
    error_message: str | None,
) -> ReportJob:
    report = db.get(ReportJob, report_job_id)
    if report is None:
        raise RuntimeError(f"Report job not found: {report_job_id}")
    report.status = status
    report.error_message = error_message
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _fail_report(db, report_job_id: str, error_message: str) -> None:
    report = db.get(ReportJob, report_job_id)
    if report is None:
        return
    report.status = "failed"
    report.error_message = error_message
    db.add(report)
    db.commit()
