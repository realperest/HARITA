"""Proje, anahtar, izin, kaynak ve kullanim sayaci islemleri."""

import json
import logging
from datetime import date

import asyncpg

from app.db import havuz

log = logging.getLogger(__name__)

_PROJE_SORGUSU = """
SELECT p.id, p.ad, p.aciklama, p.aktif, p.dakika_limiti, p.olusturma,
       COALESCE((SELECT array_agg(k.kaynak ORDER BY k.kaynak) FROM proje_kaynak k WHERE k.proje_id = p.id), '{}') AS kaynaklar,
       COALESCE((SELECT jsonb_object_agg(s.kod, i.izin_seviyesi_id)
                   FROM proje_servis_izni i JOIN tnm_servis s ON s.id = i.servis_id
                  WHERE i.proje_id = p.id), '{}'::jsonb) AS izinler,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('on_ek', a.on_ek, 'aktif', a.aktif, 'son_kullanim', a.son_kullanim)
                                  ORDER BY a.id)
                   FROM proje_anahtar a WHERE a.proje_id = p.id), '[]'::jsonb) AS anahtarlar
  FROM proje p
"""


def _proje_sozlugu(satir: asyncpg.Record) -> dict:
    """Veritabani satirini API sozlugune cevirir (jsonb alanlari acilir)."""
    veri = dict(satir)
    veri["kaynaklar"] = list(veri["kaynaklar"])
    veri["izinler"] = json.loads(veri["izinler"]) if isinstance(veri["izinler"], str) else veri["izinler"]
    veri["anahtarlar"] = json.loads(veri["anahtarlar"]) if isinstance(veri["anahtarlar"], str) else veri["anahtarlar"]
    return veri


async def anahtardan_coz(ozet: str) -> dict | None:
    """Anahtar ozetinden proje, izinler ve kaynaklari tek sorguda getirir; yoksa None."""
    async with havuz().acquire() as baglanti:
        satir = await baglanti.fetchrow(
            _PROJE_SORGUSU.replace("FROM proje p", "FROM proje p JOIN proje_anahtar pa ON pa.proje_id = p.id")
            + " WHERE pa.anahtar_ozeti = $1",
            ozet,
        )
        if satir is None:
            return None
        anahtar_aktif = await baglanti.fetchval("SELECT aktif FROM proje_anahtar WHERE anahtar_ozeti = $1", ozet)
    veri = _proje_sozlugu(satir)
    veri["anahtar_aktif"] = bool(anahtar_aktif)
    return veri


async def kullanimi_say(proje_id: int, servis_kod: str, ozet: str) -> None:
    """Gunluk kullanim sayacini artirir ve anahtarin son kullanim zamanini gunceller; hata istegi bozmaz."""
    try:
        async with havuz().acquire() as baglanti:
            async with baglanti.transaction():
                await baglanti.execute(
                    """INSERT INTO kullanim_gunluk (proje_id, servis_id, gun, adet)
                       SELECT $1, s.id, $3, 1 FROM tnm_servis s WHERE s.kod = $2
                       ON CONFLICT (proje_id, servis_id, gun) DO UPDATE SET adet = kullanim_gunluk.adet + 1""",
                    proje_id, servis_kod, date.today(),
                )
                await baglanti.execute("UPDATE proje_anahtar SET son_kullanim = now() WHERE anahtar_ozeti = $1", ozet)
    except Exception:
        log.exception("Kullanim sayaci yazilamadi (proje=%s, servis=%s)", proje_id, servis_kod)


async def _izinleri_yaz(baglanti: asyncpg.Connection, proje_id: int, servisler: list[str] | None) -> None:
    """Projenin servis izinlerini verilen listeyle degistirir (listedekiler 'gorebilir'). None = tum servisler."""
    await baglanti.execute("DELETE FROM proje_servis_izni WHERE proje_id = $1", proje_id)
    bulunan = await baglanti.fetchval(
        """INSERT INTO proje_servis_izni (proje_id, servis_id, izin_seviyesi_id)
           SELECT $1, s.id, (SELECT id FROM tnm_izin_seviyesi WHERE kod = 'gorebilir')
             FROM tnm_servis s WHERE $2::text[] IS NULL OR s.kod = ANY($2::text[])
           RETURNING 1""",
        proje_id, servisler,
    ) if servisler is None or servisler else None
    if (servisler is None or servisler) and bulunan is None:
        raise ValueError("Gecerli servis kodu bulunamadi.")


async def _kaynaklari_yaz(baglanti: asyncpg.Connection, proje_id: int, kaynaklar: list[str]) -> None:
    """Projenin izinli tarayici kaynaklarini verilen listeyle degistirir."""
    await baglanti.execute("DELETE FROM proje_kaynak WHERE proje_id = $1", proje_id)
    if kaynaklar:
        await baglanti.executemany(
            "INSERT INTO proje_kaynak (proje_id, kaynak) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            [(proje_id, k.rstrip("/")) for k in kaynaklar],
        )


async def olustur(ad: str, aciklama: str | None, dakika_limiti: int, servisler: list[str] | None, kaynaklar: list[str],
                  ozet: str, on_ek: str) -> int:
    """Proje, ilk anahtar, izinler ve kaynaklari tek islemde olusturur; proje id'sini dondurur."""
    async with havuz().acquire() as baglanti:
        async with baglanti.transaction():
            proje_id = await baglanti.fetchval(
                "INSERT INTO proje (ad, aciklama, dakika_limiti) VALUES ($1, $2, $3) RETURNING id",
                ad, aciklama, dakika_limiti,
            )
            await _izinleri_yaz(baglanti, proje_id, servisler)
            await _kaynaklari_yaz(baglanti, proje_id, kaynaklar)
            await baglanti.execute(
                "INSERT INTO proje_anahtar (proje_id, anahtar_ozeti, on_ek) VALUES ($1, $2, $3)", proje_id, ozet, on_ek,
            )
    return proje_id


async def getir(proje_id: int) -> dict | None:
    """Tek projeyi getirir."""
    async with havuz().acquire() as baglanti:
        satir = await baglanti.fetchrow(_PROJE_SORGUSU + " WHERE p.id = $1", proje_id)
    return _proje_sozlugu(satir) if satir else None


async def listele() -> list[dict]:
    """Tum projeleri tek sorguda listeler."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(_PROJE_SORGUSU + " ORDER BY p.id")
    return [_proje_sozlugu(s) for s in satirlar]


async def guncelle(proje_id: int, aktif: bool | None, dakika_limiti: int | None, servisler: list[str] | None,
                   kaynaklar: list[str] | None) -> bool:
    """Verilen alanlari gunceller; proje yoksa False."""
    async with havuz().acquire() as baglanti:
        async with baglanti.transaction():
            if await baglanti.fetchval("SELECT 1 FROM proje WHERE id = $1", proje_id) is None:
                return False
            if aktif is not None:
                await baglanti.execute("UPDATE proje SET aktif = $2 WHERE id = $1", proje_id, aktif)
            if dakika_limiti is not None:
                await baglanti.execute("UPDATE proje SET dakika_limiti = $2 WHERE id = $1", proje_id, dakika_limiti)
            if servisler is not None:
                await _izinleri_yaz(baglanti, proje_id, servisler)
            if kaynaklar is not None:
                await _kaynaklari_yaz(baglanti, proje_id, kaynaklar)
    return True


async def anahtar_ekle(proje_id: int, ozet: str, on_ek: str) -> bool:
    """Projeye yeni anahtar ekler; proje yoksa False."""
    async with havuz().acquire() as baglanti:
        if await baglanti.fetchval("SELECT 1 FROM proje WHERE id = $1", proje_id) is None:
            return False
        await baglanti.execute(
            "INSERT INTO proje_anahtar (proje_id, anahtar_ozeti, on_ek) VALUES ($1, $2, $3)", proje_id, ozet, on_ek,
        )
    return True


async def anahtar_iptal(proje_id: int, on_ek: str) -> list[str]:
    """On ek ile bulunan anahtari kapatir; etkilenen anahtar ozetlerini (onbellek temizligi icin) dondurur."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            "UPDATE proje_anahtar SET aktif = FALSE WHERE proje_id = $1 AND on_ek = $2 RETURNING anahtar_ozeti",
            proje_id, on_ek,
        )
    return [s["anahtar_ozeti"] for s in satirlar]


async def anahtar_ozetleri(proje_id: int) -> list[str]:
    """Projenin tum anahtar ozetleri (onbellek temizligi icin)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch("SELECT anahtar_ozeti FROM proje_anahtar WHERE proje_id = $1", proje_id)
    return [s["anahtar_ozeti"] for s in satirlar]


async def kullanim(proje_id: int, gun_sayisi: int) -> list[dict]:
    """Projenin son N gunluk servis bazli kullanimini dondurur."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            """SELECT k.gun, s.kod AS servis, k.adet
                 FROM kullanim_gunluk k JOIN tnm_servis s ON s.id = k.servis_id
                WHERE k.proje_id = $1 AND k.gun > current_date - $2::int
                ORDER BY k.gun DESC, s.kod""",
            proje_id, gun_sayisi,
        )
    return [{"gun": s["gun"].strftime("%d.%m.%Y"), "servis": s["servis"], "adet": s["adet"]} for s in satirlar]
