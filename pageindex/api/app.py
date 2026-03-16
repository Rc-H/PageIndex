from __future__ import annotations

from fastapi import FastAPI

from pageindex.api.routes import router as api_router
from pageindex.infrastructure.settings import ServiceSettings, load_settings
from pageindex.core.services.task_service import IndexTaskService


def create_app(
    settings: ServiceSettings | None = None,
    task_service: IndexTaskService | None = None,
) -> FastAPI:
    service_settings = settings or load_settings().service
    index_task_service = task_service or IndexTaskService(service_settings)

    app = FastAPI(title="PageIndex Service", version="1.0.0")
    app.state.task_service = index_task_service
    app.include_router(api_router)
    return app
