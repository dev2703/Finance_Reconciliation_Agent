from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import create_router
from .storage import DocumentStore

API_TITLE = "Finance Reconciliation API"
API_VERSION = "0.1.0"


def create_app(storage_path: str | None = None) -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    database_url = storage_path
    if storage_path and "://" not in storage_path:
        database_url = f"sqlite:///{storage_path}"
    store = DocumentStore(database_url)
    app.state.document_store = store
    app.router.routes.extend(create_router(store).routes)
    return app