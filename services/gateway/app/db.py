"""PostgreSQL baglanti havuzu ve sema kurulumu."""

import logging
from pathlib import Path

import asyncpg

from app.config import ayarlar

log = logging.getLogger(__name__)

SEMA_DOSYASI = Path(__file__).resolve().parent.parent / "sql" / "001_sema.sql"

_havuz: asyncpg.Pool | None = None


async def baslat() -> None:
    """Havuzu acar ve sema betigini calistirir (betik tekrar calistirilabilir)."""
    global _havuz
    _havuz = await asyncpg.create_pool(ayarlar.DATABASE_URL, min_size=1, max_size=10)
    async with _havuz.acquire() as baglanti:
        await baglanti.execute(SEMA_DOSYASI.read_text(encoding="utf-8"))
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
