import os
from pathlib import Path

import neatlogs
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import create_router
from .storage import DocumentStore


def _configure_neatlogs() -> None:
    """Enable external tracing only when deployment credentials are configured."""
    api_key = os.getenv("NEATLOGS_API_KEY")
    if not api_key:
        return
    neatlogs.init(
        api_key=api_key,
        endpoint=os.getenv("NEATLOGS_ENDPOINT", "K9wVuaPutltz-DGc3T6xrdM_1pCRQO5J"),
        workflow_name="finance-reconciliation-investigation",
        instrumentations=["openai"],
    )


_configure_neatlogs()

API_TITLE = "Finance Reconciliation API"
API_VERSION = "0.1.0"


def create_app(
    storage_path: str | None = None,
    *,
    ml_model_directory: str | Path | None = None,
) -> FastAPI:
    """Create the API with an optional, locally trusted Phase 5 artifact."""
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    database_url = storage_path
    if storage_path and "://" not in storage_path:
        database_url = f"sqlite:///{storage_path}"
    store = DocumentStore(database_url)
    app.state.document_store = store
    configured_model_directory = ml_model_directory or os.getenv("ML_MODEL_DIRECTORY")
    app.state.ml_model_directory = (
        Path(configured_model_directory) if configured_model_directory else None
    )
    app.router.routes.extend(create_router(store, app.state.ml_model_directory).routes)
    return app
