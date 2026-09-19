"""What a route needs from the app: the config and the store it was created with."""

from fastapi import Request

from manc.config import Config
from manc.store.interface import Store


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> Store:
    return request.app.state.store
