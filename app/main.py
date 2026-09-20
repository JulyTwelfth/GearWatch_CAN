from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.health import router as health_router
from app.api.routes.products import router as products_router
from app.core.config import get_settings
from app.web.pages import router as pages_router

STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Build the FastAPI application without creating external connections."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    application.include_router(health_router)
    application.include_router(products_router)
    application.include_router(pages_router)
    return application


app = create_app()
