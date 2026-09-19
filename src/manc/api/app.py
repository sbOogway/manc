"""App factory: the store and config are injected, so tests run it against FakeStore."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from manc.api.routes import router
from manc.config import Config
from manc.store.interface import Store


def create_app(config: Config, store: Store) -> FastAPI:
    app = FastAPI(title="manc", version="1")
    app.state.config = config
    app.state.store = store
    # read-only public data: any origin may read it, the GitHub Pages site included
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
    app.include_router(router)
    return app
