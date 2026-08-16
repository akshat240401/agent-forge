from __future__ import annotations

from fastapi import FastAPI, HTTPException

from src.replay import ReplayResult

from .catalog import CapabilityCatalog
from .models import (
    CapabilityCatalogResponse,
    CapabilityInvocationRequest,
    CapabilitySummary,
)
from .service import CapabilityInvoker, DeterministicCapabilityInvoker


def create_app(
    *,
    artifact_dir: str = "artifacts",
    evidence_root: str = "evidence",
    invoker: CapabilityInvoker | None = None,
) -> FastAPI:
    catalog = CapabilityCatalog(artifact_dir)
    capability_invoker = invoker or DeterministicCapabilityInvoker(
        evidence_root=evidence_root,
        headless=True,
    )

    app = FastAPI(
        title="AgentForge Capability API",
        version="1.0.0",
        description=(
            "Agent-facing catalog and deterministic invocation surface "
            "for saved AgentForge capabilities."
        ),
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/v1/capabilities",
        response_model=CapabilityCatalogResponse,
    )
    async def list_capabilities() -> CapabilityCatalogResponse:
        return CapabilityCatalogResponse(
            capabilities=catalog.list_summaries()
        )

    @app.get(
        "/v1/capabilities/{capability_id}",
        response_model=CapabilitySummary,
    )
    async def get_capability(
        capability_id: str,
    ) -> CapabilitySummary:
        try:
            artifact = catalog.get(capability_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        return catalog.summary(artifact)

    @app.post(
        "/v1/capabilities/{capability_id}/invoke",
        response_model=ReplayResult,
    )
    async def invoke_capability(
        capability_id: str,
        request: CapabilityInvocationRequest,
    ) -> ReplayResult:
        try:
            artifact = catalog.get(capability_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        return await capability_invoker.invoke(
            artifact=artifact,
            arguments=request.arguments,
        )

    return app


app = create_app()
