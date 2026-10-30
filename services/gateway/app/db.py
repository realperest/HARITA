"""PostgreSQL baglanti havuzu ve sema kurulumu."""

import logging
from pathlib import Path

import asyncpg

from app.config import ayarlar

log = logging.getLogger(__name__)

SEMA_DIZINI = Path(__file__).resolve().parent.parent / "sql"

_havuz: asyncpg.Pool | None = None


async def baslat() -> None:
    """Havuzu acar ve sql/ altindaki sema betiklerini sirayla calistirir (betikler tekrar calistirilabilir)."""
    global _havuz
    _havuz = await asyncpg.create_pool(ayarlar.DATABASE_URL, min_size=1, max_size=10)
    async with _havuz.acquire() as baglanti:
        # Es zamanli acilan kopyalar sirayla kurulsun diye danisma kilidi
        await baglanti.execute("SELECT pg_advisory_lock(727001)")
        try:
            for dosya in sorted(SEMA_DIZINI.glob("*.sql")):
                await baglanti.execute(dosya.read_text(encoding="utf-8"))
        finally:
            await baglanti.execute("SELECT pg_advisory_unlock(727001)")
    log.info("Veritabani hazir, sema uygulandi.")


async def kapat() -> None:
    """Havuzu kapatir."""
    global _havuz
    if _havuz is not None:
        await _havuz.close()
        _havuz = None


def havuz() -> asyncpg.Pool:
    """Acik havuzu dondurur; acilmadiysa hata verir."""
    if _havuz is None:
        raise RuntimeError("Veritabani havuzu acik degil.")
    return _havuz
