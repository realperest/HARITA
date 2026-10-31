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
            await _yeni_servisleri_ac(baglanti)
        finally:
            await baglanti.execute("SELECT pg_advisory_unlock(727001)")
    log.info("Veritabani hazir, sema uygulandi.")


async def _yeni_servisleri_ac(baglanti: asyncpg.Connection) -> None:
    """Sema betikleriyle eklenen her yeni servisi, mevcut tum projelere bir kez 'gorebilir' olarak acar.

    Ilk calismada var olan servisler yalniz isaretlenir (bilincli kisitlamalar bozulmaz). Sonrasinda gelen
    servisler tum projelere acilir; yonetici sonradan bir izni kaldirirsa geri eklenmez (sema_gocu kaydi)."""
    async with baglanti.transaction():
        await baglanti.execute(
            "CREATE TABLE IF NOT EXISTS sema_gocu (ad TEXT PRIMARY KEY, zaman TIMESTAMPTZ NOT NULL DEFAULT now())")
        ilk = await baglanti.fetchval("SELECT 1 FROM sema_gocu WHERE ad = 'servis_otomatik_baslangic'") is None
        yeniler = await baglanti.fetch(
            """SELECT s.id, s.kod FROM tnm_servis s
                WHERE NOT EXISTS (SELECT 1 FROM sema_gocu g WHERE g.ad = 'servis_otomatik_' || s.kod)
                ORDER BY s.id""")
        for servis in yeniler:
            if not ilk:
                await baglanti.execute(
                    """INSERT INTO proje_servis_izni (proje_id, servis_id, izin_seviyesi_id)
                       SELECT p.id, $1, (SELECT id FROM tnm_izin_seviyesi WHERE kod = 'gorebilir') FROM proje p
                       ON CONFLICT (proje_id, servis_id) DO NOTHING""", servis["id"])
                log.info("Yeni servis tum projelere acildi: %s", servis["kod"])
            await baglanti.execute("INSERT INTO sema_gocu (ad) VALUES ($1) ON CONFLICT DO NOTHING",
                                   "servis_otomatik_" + servis["kod"])
        if ilk:
            await baglanti.execute("INSERT INTO sema_gocu (ad) VALUES ('servis_otomatik_baslangic') ON CONFLICT DO NOTHING")


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
