"""Yerlesim uclari: il, ilce, mahalle / koy ve sehir-kasaba-koy-mezra-semt merkezleri (tum Turkiye)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.crud import yerlesim as yerlesim_crud
from app.security import yetki

router = APIRouter(prefix="/v1/yerlesim", tags=["yerlesim"])

Tur = Literal["il", "ilce", "mahalle_koy", "sehir", "kasaba", "koy", "mezra", "semt"]


@router.get("/ara")
async def ara(q: str = Query(min_length=2, max_length=100), tur: Tur | None = None, ust_id: int | None = None,
              limit: int = Query(default=10, ge=1, le=50), _proje: dict = Depends(yetki("yerlesim"))) -> list[dict]:
    """Ada gore yerlesim arama (Turkce karakter duyarsiz). tur ve ust_id ile daraltilir."""
    return await yerlesim_crud.ara(q, tur, ust_id, limit)


@router.get("/nokta")
async def nokta(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                _proje: dict = Depends(yetki("yerlesim"))) -> dict:
    """Noktanin hangi il / ilce / mahalle-koy icinde oldugu ve en yakin merkez."""
    return await yerlesim_crud.noktada(lat, lon)


@router.get("/yakin")
async def yakin(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                yaricap_m: int = Query(default=5000, ge=100, le=50000), tur: Tur | None = None,
                limit: int = Query(default=20, ge=1, le=100), _proje: dict = Depends(yetki("yerlesim"))) -> list[dict]:
    """Noktaya yaricap icindeki merkezler, yakindan uzaga."""
    return await yerlesim_crud.yakin(lat, lon, yaricap_m, tur, limit)


@router.get("/{yerlesim_id}")
async def getir(yerlesim_id: int, sinir: bool = False, _proje: dict = Depends(yetki("yerlesim"))) -> dict:
    """Tek yerlesim ve ust zinciri; sinir=true ile GeoJSON siniri."""
    veri = await yerlesim_crud.getir(yerlesim_id, sinir)
    if veri is None:
        raise HTTPException(status_code=404, detail="Yerlesim bulunamadi.")
    return veri


@router.get("/{yerlesim_id}/alt")
async def alt(yerlesim_id: int, tur: Tur | None = None, limit: int = Query(default=100, ge=1, le=500),
              atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("yerlesim"))) -> list[dict]:
    """Dogrudan alt ogeler (ilin ilceleri, ilcenin mahalle / koyleri)."""
    return await yerlesim_crud.alt_ogeler(yerlesim_id, tur, limit, atla)
