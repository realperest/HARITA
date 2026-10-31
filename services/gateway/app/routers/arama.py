"""Adres / yer arama ve ters arama uclari (Photon GeoJSON biciminde, kendi adres indeksimizden)."""

from fastapi import APIRouter, Depends, Query

from app.crud import adres as adres_crud
from app.routers.uyumlu import _photon
from app.security import yetki

router = APIRouter(prefix="/v1", tags=["arama"])


@router.get("/arama")
async def arama(q: str = Query(min_length=2, max_length=200), limit: int = Query(default=7, ge=1, le=20),
                lat: float | None = Query(default=None, ge=-90, le=90), lon: float | None = Query(default=None, ge=-180, le=180),
                _proje: dict = Depends(yetki("arama"))) -> dict:
    """Metinle adres / yer arama (GeoJSON). lat ve lon verilirse o civar one cikar."""
    return {"type": "FeatureCollection", "features": [_photon(r) for r in await adres_crud.ara(q, None, None, lat, lon, limit)]}


@router.get("/ters-arama")
async def ters_arama(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                     _proje: dict = Depends(yetki("arama"))) -> dict:
    """Konumdan en yakin kapi, sokak veya yer (GeoJSON)."""
    v = await adres_crud.nokta(lat, lon, 150, 1)
    ilk = (v["kapilar"] or v["sokaklar"] or v["yerler"] or [None])[0]
    return {"type": "FeatureCollection", "features": [_photon(ilk)] if ilk else []}
