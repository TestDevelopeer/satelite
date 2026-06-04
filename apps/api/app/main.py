import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import init_db


async def init_db_with_retry(max_attempts: int = 6, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            init_db()
            return
        except SQLAlchemyError:
            if attempt == max_attempts:
                raise
            await asyncio.sleep(delay_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db_with_retry()
    yield


app = FastAPI(
    title="GeoEco Monitor API",
    description=(
        "API публичной панели мониторинга для предварительной дистанционной оценки "
        "по Sentinel-2."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "geoeco-api"}


app.include_router(router, prefix="/api")
