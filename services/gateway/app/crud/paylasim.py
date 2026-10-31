"""Rota paylasim kodu kayitlari."""

import json
import secrets

import asyncpg

from app.db import havuz

# Karisan karakterler (0/O, 1/I/L) yok; 8 karakter ~ 10^12 olasilik
ALFABE = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
KOD_UZUNLUGU = 8


def kod_uret() -> str:
    """Rastgele paylasim kodu."""
    return "".join(secrets.choice(ALFABE) for _ in range(KOD_UZUNLUGU))


async def olustur(proje_id: int, veri: dict, sure_saat: int) -> dict:
    """Paylasim kaydi olusturur (cakismada yeni kod denenir); suresi gecmis kayitlar ara ara temizlenir."""
    async with havuz().acquire() as baglanti:
        await baglanti.execute("DELETE FROM rota_paylasim WHERE bitis < now() - interval '7 days'")
        for _ in range(5):
            try:
                s = await baglanti.fetchrow(
                    """INSERT INTO rota_paylasim (kod, proje_id, veri, bitis) VALUES ($1, $2, $3::jsonb, now() + make_interval(hours => $4))
                       RETURNING kod, bitis""", kod_uret(), proje_id, json.dumps(veri, ensure_ascii=False), sure_saat)
                return {"kod": s["kod"], "bitis": s["bitis"].isoformat()}
            except asyncpg.UniqueViolationError:
                continue
    raise RuntimeError("Paylasim kodu uretilemedi.")


async def getir(kod: str) -> dict | None:
    """Gecerli (suresi dolmamis) paylasimi getirir ve acilma sayisini artirir."""
    async with havuz().acquire() as baglanti:
        s = await baglanti.fetchrow(
            """UPDATE rota_paylasim SET acilma_sayisi = acilma_sayisi + 1 WHERE kod = $1 AND bitis > now()
               RETURNING veri, bitis, acilma_sayisi""", kod.upper())
    if s is None:
        return None
    return {**json.loads(s["veri"]), "kod": kod.upper(), "bitis": s["bitis"].isoformat(), "acilma_sayisi": s["acilma_sayisi"]}


async def sil(proje_id: int, kod: str) -> bool:
    """Projenin kendi paylasimini iptal eder."""
    async with havuz().acquire() as baglanti:
        sonuc = await baglanti.execute("DELETE FROM rota_paylasim WHERE kod = $1 AND proje_id = $2", kod.upper(), proje_id)
    return not sonuc.endswith(" 0")
