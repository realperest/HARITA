"""Adres / yer arama ve ters arama uclari (Photon GeoJSON)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.security import yetki
from app.services import photon
from app.services.http import AltServisHatasi

router = APIRouter(prefix="/v1", tags=["arama"])


@router.get("/arama")
async def arama(q: str = Query(min_length=2, max_length=200), limit: int = Query(default=7, ge=1, le=20),
                dil: str = Query(default="tr", pattern="^[a-z]{2}$"), lat: float | None = Query(default=None, ge=-90, le=90),
                lon: float | None = Query(default=None, ge=-180, le=180), _proje: dict = Depends(yetki("arama"))) -> dict:
    """Metinle adres / yer arama. lat ve lon verilirse o civar one cikar."""
    try:
        return await photon.ara(q, limit, dil, lat, lon)
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Arama servisi su an yanit vermiyor.") from hata


@router.get("/ters-arama")
async def ters_arama(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                     dil: str = Query(default="tr", pattern="^[a-z]{2}$"), limit: int = Query(default=1, ge=1, le=5),
                     _proje: dict = Depends(yetki("arama"))) -> dict:
    """Koordinattan en yakin adres / yer."""
    try:
        return await photon.ters_ara(lat, lon, dil, limit)
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Arama servisi su an yanit vermiyor.") from hata
