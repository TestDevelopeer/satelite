from redis import Redis
from rq import Queue, Worker

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is required for the RQ worker.")
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.queue_name, connection=connection)
    worker = Worker([queue], connection=connection)
    print(
        f"GeoEco RQ worker listening on queue '{settings.queue_name}' "
        f"with timeout {settings.rq_default_timeout}s",
        flush=True,
    )
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
