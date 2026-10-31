"""Test ortami: gercek PostgreSQL ve Redis (ortam degiskenleri), alt servisler respx ile taklit edilir."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:test@localhost:55432/harita")
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/0")
os.environ.setdefault("YONETIM_ANAHTARI", "test-yonetim")
os.environ.setdefault("KARO_ADRESI", "https://karo.test")
os.environ.setdefault("ROTA_ADRESI", "http://rota.test:8002")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def istemci():
    """Uygulamayi yasam dongusuyle birlikte calistiran test istemcisi."""
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
