from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from redis import Redis
from rq import Queue

from app.core.config import get_settings
from app.services.analysis_runner import run_analysis_job
from app.services.comparison import run_comparison_job

JobKind = Literal["analysis", "comparison", "analysis_report", "comparison_report"]


class QueueUnavailableError(RuntimeError):
    pass


class QueueOverloadedError(RuntimeError):
    pass


_executor = ThreadPoolExecutor(max_workers=get_settings().max_concurrent_jobs)


def execution_mode() -> str:
    settings = get_settings()
    if settings.job_execution_mode == "rq":
        return "rq"
    return "in_process"


def dispatch_analysis(analysis_id: str, cloud_cover_max: float) -> None:
    if execution_mode() == "rq":
        enqueue_rq_job(
            "app.worker_tasks.run_analysis_job_task",
            analysis_id,
            cloud_cover_max,
            job_kind="analysis",
            timeout=get_settings().rq_analysis_timeout,
        )
        return
    _executor.submit(run_analysis_job, analysis_id, cloud_cover_max)


def dispatch_comparison(comparison_id: str, cloud_cover_max: float) -> None:
    if execution_mode() == "rq":
        enqueue_rq_job(
            "app.worker_tasks.run_comparison_job_task",
            comparison_id,
            cloud_cover_max,
            job_kind="comparison",
            timeout=get_settings().rq_comparison_timeout,
        )
        return
    _executor.submit(run_comparison_job, comparison_id, cloud_cover_max)


def dispatch_analysis_report(report_job_id: str, analysis_id: str) -> None:
    if execution_mode() == "rq":
        enqueue_rq_job(
            "app.worker_tasks.generate_analysis_report_task",
            report_job_id,
            analysis_id,
            job_kind="analysis_report",
            timeout=get_settings().rq_report_timeout,
        )
        return
    from app.worker_tasks import generate_analysis_report_task

    generate_analysis_report_task(report_job_id, analysis_id)


def dispatch_comparison_report(report_job_id: str, comparison_id: str) -> None:
    if execution_mode() == "rq":
        enqueue_rq_job(
            "app.worker_tasks.generate_comparison_report_task",
            report_job_id,
            comparison_id,
            job_kind="comparison_report",
            timeout=get_settings().rq_report_timeout,
        )
        return
    from app.worker_tasks import generate_comparison_report_task

    generate_comparison_report_task(report_job_id, comparison_id)


def enqueue_rq_job(
    function_path: str,
    *args: object,
    job_kind: JobKind,
    timeout: int | None = None,
) -> None:
    queue = get_queue()
    settings = get_settings()
    if queue.count >= settings.queue_max_jobs:
        raise QueueOverloadedError(
            f"Очередь перегружена: {queue.count}/{settings.queue_max_jobs} задач."
        )
    queue.enqueue(
        function_path,
        *args,
        job_timeout=timeout or settings.rq_default_timeout,
        result_ttl=3600,
        failure_ttl=86400,
        description=f"geoeco:{job_kind}",
    )


def get_queue() -> Queue:
    settings = get_settings()
    if not settings.redis_url:
        raise QueueUnavailableError("REDIS_URL не задан, RQ-очередь недоступна.")
    try:
        connection = Redis.from_url(settings.redis_url)
        connection.ping()
    except Exception as exc:  # noqa: BLE001
        raise QueueUnavailableError(f"Redis недоступен: {exc}") from exc
    return Queue(settings.queue_name, connection=connection)
