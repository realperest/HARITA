"""Anahtar uretimi, anahtar kapisi (izin, kaynak, kota) ve yonetim kapisi."""

import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import BackgroundTasks, Header, HTTPException, Request

from app import cache
from app.config import ayarlar
from app.crud import proje as proje_crud

log = logging.getLogger(__name__)

IZIN_GOREBILIR = 2


def ozet_al(anahtar: str) -> str:
    """Anahtarin SHA-256 ozeti; anahtarin kendisi hicbir yerde saklanmaz."""
    return hashlib.sha256(anahtar.encode("utf-8")).hexdigest()


def yeni_anahtar() -> tuple[str, str, str]:
    """(anahtar, ozet, on_ek) uretir. Anahtar yalniz olusturulurken bir kez gosterilir."""
    anahtar = "hk_" + secrets.token_urlsafe(32)
    return anahtar, ozet_al(anahtar), anahtar[:10]


async def onbellegi_temizle(ozetler: list[str]) -> None:
    """Verilen anahtar ozetlerinin proje onbellegini siler."""
    if ozetler:
        await cache.istemci().delete(*[f"anahtar:{o}:proje" for o in ozetler])


async def _projeyi_coz(ozet: str) -> dict | None:
    """Proje bilgisini once Redis'ten, yoksa veritabanindan okur."""
    anahtar = f"anahtar:{ozet}:proje"
    onbellek = await cache.istemci().get(anahtar)
    if onbellek:
        return json.loads(onbellek)
    proje = await proje_crud.anahtardan_coz(ozet)
    if proje is not None:
        await cache.istemci().set(anahtar, json.dumps(proje, default=str), ex=ayarlar.ANAHTAR_ONBELLEK_SN)
    return proje


async def _kota_kontrol(proje: dict) -> None:
    """Dakika basina istek siniri; asilirsa 429."""
    pencere = int(time.time() // 60)
    anahtar = f"limit:{proje['id']}:{pencere}"
    sayi = await cache.istemci().incr(anahtar)
    if sayi == 1:
        await cache.istemci().expire(anahtar, 70)
    if sayi > proje["dakika_limiti"]:
        raise HTTPException(status_code=429, detail="Istek siniri asildi, biraz sonra tekrar deneyin.",
                            headers={"Retry-After": "30"})


def yetki(servis_kod: str):
    """Servis icin anahtar kapisi dependency'si uretir. Basarili ise proje sozlugunu dondurur."""

    async def _kapi(
        request: Request,
        arka_plan: BackgroundTasks,
        x_harita_anahtar: str | None = Header(default=None),
    ) -> dict:
        ham = x_harita_anahtar or request.path_params.get("anahtar")
        if not ham:
            raise HTTPException(status_code=401, detail="Harita anahtari gerekli.")
        ozet = ozet_al(ham)
        proje = await _projeyi_coz(ozet)
        if proje is None or not proje["aktif"] or not proje["anahtar_aktif"]:
            raise HTTPException(status_code=401, detail="Harita anahtari gecersiz.")
        if proje["izinler"].get(servis_kod, 1) < IZIN_GOREBILIR:
            raise HTTPException(status_code=403, detail="Bu servis icin izniniz yok.")
        kaynak = request.headers.get("origin")
        if kaynak and proje["kaynaklar"] and kaynak.rstrip("/") not in proje["kaynaklar"]:
            raise HTTPException(status_code=403, detail="Bu kaynaktan erisim izni yok.")
        await _kota_kontrol(proje)
        arka_plan.add_task(proje_crud.kullanimi_say, proje["id"], servis_kod, ozet)
        return proje

    return _kapi


async def yonetim_kapisi(x_yonetim_anahtari: str | None = Header(default=None)) -> None:
    """Yonetim uclari icin ortak yonetim anahtarini sabit sure karsilastirmasiyla dogrular."""
    beklenen = ayarlar.YONETIM_ANAHTARI.encode("utf-8")
    verilen = (x_yonetim_anahtari or "").encode("utf-8")
    if not hmac.compare_digest(beklenen, verilen):
        raise HTTPException(status_code=401, detail="Yonetim anahtari gecersiz.")
