"""Adres uclari: birlesik arama, ters arama, sokak, kapi numarasi ve onemli yerler (tum Turkiye, OSM)."""

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.crud import adres as adres_crud
from app.crud import yerlesim as yerlesim_crud
from app.security import yetki

router = APIRouter(prefix="/v1/adres", tags=["adres"])


@router.get("/ara")
async def ara(q: str = Query(min_length=2, max_length=200), tur: Literal["kapi", "sokak", "bina", "yer", "yerlesim"] | None = None,
              ust_id: int | None = None, lat: float | None = Query(default=None, ge=-90, le=90),
              lon: float | None = Query(default=None, ge=-180, le=180), limit: int = Query(default=10, ge=1, le=50),
              _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Birlesik adres arama. 'Namik Kemal Bulvari 12' gibi metinler kapi numarasina kadar eslesir. lat/lon verilirse yakinlik sirayi etkiler."""
    return await adres_crud.ara(q, tur, ust_id, lat, lon, limit)


@router.get("/nokta")
async def nokta(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), yaricap_m: int = Query(default=150, ge=10, le=2000),
                limit: int = Query(default=5, ge=1, le=20), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Ters arama: noktadan adres metni, il / ilce / mahalle, en yakin sokaklar, kapi numaralari ve yerler."""
    return await adres_crud.nokta(lat, lon, yaricap_m, limit)


@router.get("/yerler")
async def yerler(bati: float = Query(ge=-180, le=180), guney: float = Query(ge=-90, le=90), dogu: float = Query(ge=-180, le=180),
                 kuzey: float = Query(ge=-90, le=90), tur: str | None = Query(default=None, max_length=30),
                 limit: int = Query(default=1000, ge=1, le=5000), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Harita katmani: kutu icindeki onemli yerler GeoJSON olarak (eczane, okul, market, restoran vb.)."""
    return await adres_crud.yerler_kutuda(bati, guney, dogu, kuzey, tur, limit)


@router.get("/mahalle/{mahalle_id}/sokaklar")
async def mahalle_sokaklari(mahalle_id: int, q: str | None = Query(default=None, max_length=100), limit: int = Query(default=200, ge=1, le=1000),
                            atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir mahalle / koyun sokaklari (acilir liste icin)."""
    return await adres_crud.sokaklar(mahalle_id, q, limit, atla)


@router.get("/sokak/{sokak_id}")
async def sokak(sokak_id: int, cizgi: bool = False, _proje: dict = Depends(yetki("adres"))) -> dict:
    """Tek sokak; cizgi=true ile GeoJSON cizgisi."""
    veri = await adres_crud.sokak_getir(sokak_id, cizgi)
    if veri is None:
        raise HTTPException(status_code=404, detail="Sokak bulunamadi.")
    return veri


@router.get("/sokak/{sokak_id}/kapilar")
async def sokak_kapilari(sokak_id: int, limit: int = Query(default=200, ge=1, le=1000), atla: int = Query(default=0, ge=0),
                         _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir sokaktaki kapi numaralari."""
    return await adres_crud.kapilar(sokak_id, limit, atla)


@router.get("/sokak/{sokak_id}/binalar")
async def sokak_binalari(sokak_id: int, limit: int = Query(default=200, ge=1, le=1000), atla: int = Query(default=0, ge=0),
                         _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir sokaga bagli adli site ve binalar (Site / Bina acilir listesi)."""
    return await adres_crud.sokak_binalari(sokak_id, limit, atla)


@router.get("/mahalle/{mahalle_id}/binalar")
async def mahalle_binalari(mahalle_id: int, q: str | None = Query(default=None, max_length=100), limit: int = Query(default=200, ge=1, le=1000),
                           atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir mahalle / koydeki adli site ve binalar."""
    return await adres_crud.mahalle_binalari(mahalle_id, q, limit, atla)


@router.get("/bina/{bina_id}")
async def bina(bina_id: int, sinir: bool = False, _proje: dict = Depends(yetki("adres"))) -> dict:
    """Tek site / bina; sinir=true ile GeoJSON poligonu."""
    veri = await adres_crud.bina_getir(bina_id, sinir)
    if veri is None:
        raise HTTPException(status_code=404, detail="Bina bulunamadi.")
    return veri


def _karo_kutusu(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Web Mercator karo (x, y, z) -> (bati, guney, dogu, kuzey)."""
    n = 2 ** z
    bati, dogu = x / n * 360 - 180, (x + 1) / n * 360 - 180
    kuzey = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    guney = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return bati, guney, dogu, kuzey


@router.get("/yerler/karo")
async def yerler_karo(x: int = Query(ge=0), y: int = Query(ge=0), z: int = Query(default=15, ge=10, le=20), tur: str | None = Query(default=None, max_length=30),
                      limit: int = Query(default=2000, ge=1, le=5000), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Karo (x, y, z=15 varsayilan) icindeki onemli yerler GeoJSON olarak (karo bazli onbellekleme icin)."""
    bati, guney, dogu, kuzey = _karo_kutusu(x, y, z)
    return await adres_crud.yerler_kutuda(bati, guney, dogu, kuzey, tur, limit)


@router.get("/yakin")
async def yakin_yerler(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), yaricap_m: int = Query(default=5000, ge=50, le=100000),
                       tur: str | None = Query(default=None, max_length=30), limit: int = Query(default=20, ge=1, le=100),
                       _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Noktaya yakin onemli yerler (or. tur=akaryakit: en yakin benzin istasyonlari), yakindan uzaga."""
    return await adres_crud.yakin_yerler(lat, lon, yaricap_m, tur, limit)


class RotaBoyunca(BaseModel):
    """Rota cizgisi boyunca yer aramasi istegi (GeoJSON LineString koordinatlari: [boylam, enlem])."""

    koordinatlar: list[list[float]] = Field(min_length=2, max_length=5000)
    tur: str | None = Field(default=None, max_length=30)
    tampon_m: int = Field(default=500, ge=10, le=5000)
    limit: int = Field(default=100, ge=1, le=500)


@router.post("/rota-boyunca")
async def rota_boyunca(istek: RotaBoyunca, _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Rota boyunca yerler (benzin, mola, otel vb.), rota uzerindeki siraya gore."""
    return await adres_crud.rota_boyunca(istek.koordinatlar, istek.tur, istek.tampon_m, istek.limit)


@router.get("/alt")
async def alt_ogeler(ust: str = Query(pattern=r"^(il|ilce|mahalle_koy|semt|sokak):\d+$", description="tur:id, or. ilce:123"),
                     cocuk: Literal["sokak", "bina", "kapi"] | None = None, limit: int = Query(default=200, ge=1, le=1000),
                     atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Adres agacinda bir alt seviye: il > ilce > mahalle/koy > sokak > site-bina / kapi. Acilir listeler tek uctan beslenir."""
    tur, kimlik = ust.split(":")
    kimlik = int(kimlik)
    if tur in ("il", "ilce"):
        # il > ilce, ilce > mahalle / koy (sehir, kasaba, semt merkezi noktalari acilir listeye girmez)
        return await yerlesim_crud.alt_ogeler(kimlik, "ilce" if tur == "il" else "mahalle_koy", limit, atla)
    if tur in ("mahalle_koy", "semt"):
        return await (adres_crud.mahalle_binalari(kimlik, None, limit, atla) if cocuk == "bina" else adres_crud.sokaklar(kimlik, None, limit, atla))
    return await (adres_crud.kapilar(kimlik, limit, atla) if cocuk == "kapi" else adres_crud.sokak_binalari(kimlik, limit, atla))


@router.get("/sekil")
async def sekil(tur: Literal["il", "ilce", "mahalle_koy", "sehir", "kasaba", "koy", "mezra", "semt", "sokak", "bina"], id: int,
                _proje: dict = Depends(yetki("adres"))) -> dict:
    """Herhangi bir adres ogesinin GeoJSON sekli (sinir, sokak cizgisi veya bina poligonu)."""
    veri = await adres_crud.sekil(tur, id)
    if veri is None:
        raise HTTPException(status_code=404, detail="Oge bulunamadi.")
    return veri
