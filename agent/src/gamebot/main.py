from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI

from .emulators import AdbGenericDriver, LDPlayerDriver, Registry


def default_registry() -> Registry:
    return Registry([LDPlayerDriver(), AdbGenericDriver()])


def create_app(registry: Registry | None = None) -> FastAPI:
    app = FastAPI(title="gamebot-agent")
    app.state.registry = registry or default_registry()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/instances")
    def instances() -> list[dict]:
        return [asdict(i) for i in app.state.registry.scan()]

    return app


app = create_app()
