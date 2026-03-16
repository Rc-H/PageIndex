from __future__ import annotations

from typing import Any, Protocol

from pageindex.core.indexers.pipeline.context import PipelineContext


class DocumentAdapter(Protocol):
    async def build(self, context: PipelineContext) -> dict[str, Any]:
        ...
