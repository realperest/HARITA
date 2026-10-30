"""Redis istemcisi. Anahtar bicimi: <varlik>:<id>:<oznitelik>."""

import redis.asyncio as redis

from app.config import ayarlar

_istemci: redis.Redis | None = None


async def baslat() -> None:
    """Redis baglantisini kurar."""
    global _istemci
    _istemci = redis.from_url(ayarlar.REDIS_URL, decode_responses=True)
    await _istemci.ping()


async def kapat() -> None:
    """Redis baglantisini kapatir."""
    global _istemci
    if _istemci is not None:
        await _istemci.aclose()
        _istemci = None


def istemci() -> redis.Redis:
    """Acik Redis istemcisini dondurur."""
    if _istemci is None:
        raise RuntimeError("Redis baglantisi acik degil.")
    return _istemci
