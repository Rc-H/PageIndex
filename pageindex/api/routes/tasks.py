from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pageindex.api.parsers import parse_task_request
from pageindex.core.services.task_service import IndexTaskService

router = APIRouter()


def get_task_service(request: Request) -> IndexTaskService:
    return request.app.state.task_service


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/index-tasks", status_code=202)
async def create_task(
    request: Request,
    task_service: IndexTaskService = Depends(get_task_service),
) -> dict[str, str]:
    task_request = await parse_task_request(request)
    await task_service.submit(task_request)
    return {"task_id": task_request.task_id, "status": "accepted"}
