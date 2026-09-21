"""App factory: the store and config are injected, so tests run it against FakeStore."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from manc.api.routes import router
from manc.config import Config
from manc.store.interface import Store

ALLOWED_ORIGINS = [
    "https://mattiapapaccioli.com",  # GitHub Pages, on its custom domain
    "https://www.mattiapapaccioli.com",
    "https://sboogway.github.io",  # the same site before the redirect
    "http://localhost:8050",  # manc ui
    "http://127.0.0.1:8050",
    "http://localhost:5173",  # npm run dev
    "http://127.0.0.1:5173",
]


def create_app(config: Config, store: Store) -> FastAPI:
    app = FastAPI(title="manc", version="1")
    app.state.config = config
    app.state.store = store
    # only the dashboard's own origins read the API from a browser, with the cookie of a login
    # in front of the tunnel (Cloudflare Access) when there is one
    app.add_middleware(
        CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET"], allow_credentials=True
    )
    app.include_router(router)
    return app
