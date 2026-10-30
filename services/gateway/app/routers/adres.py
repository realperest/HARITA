"""Adres uclari: birlesik arama, ters arama, sokak, kapi numarasi ve onemli yerler (tum Turkiye, OSM)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.crud import adres as adres_crud
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
