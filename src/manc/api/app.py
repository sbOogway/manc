"""App factory: the store and config are injected, so tests run it against FakeStore."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from manc.api.routes import router
from manc.config import Config
from manc.store.interface import Store


def create_app(config: Config, store: Store, site_dir: Path | None = None) -> FastAPI:
    """The routes and, when `site_dir` holds a built dashboard, that site at `/`: one origin,
    so the browser needs no cross-origin grant and a login in front covers both."""
    app = FastAPI(title="manc", version="1")
    app.state.config = config
    app.state.store = store
    app.include_router(router)
    if site_dir is not None and (site_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=site_dir, html=True), name="site")
    return app
