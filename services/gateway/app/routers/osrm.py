"""OSRM uyumlu rota ucu: OSRM kullanan projeler yalniz adresi (ve anahtari) degistirerek baglanir.

Iki bicim: anahtar basliktan (X-Harita-Anahtar) ya da basligi ayarlayamayan istemciler icin yoldan (/k/<anahtar>/osrm/...).
Desteklenen: GET .../route/v1/{profil}/{boylam,enlem;boylam,enlem;...}?overview=false|simplified|full&geometries=geojson|polyline|polyline6
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.config import ayarlar
from app.schemas.harita import Nokta
from app.security import yetki
from app.services import valhalla
from app.services.http import AltServisHatasi, AltServisYok

router = APIRouter(tags=["osrm"])


def _hata(kod: int, osrm_kodu: str, mesaj: str) -> JSONResponse:
    """OSRM bicimli hata yaniti."""
    return JSONResponse(status_code=kod, content={"code": osrm_kodu, "message": mesaj})


def _koordinatlar(metin: str) -> list[Nokta] | None:
    """'boylam,enlem;boylam,enlem' metnini noktalara cevirir; gecersizse None."""
    try:
        noktalar = [Nokta(lon=float(c.split(",")[0]), lat=float(c.split(",")[1])) for c in metin.split(";")]
    except (ValueError, IndexError):
        return None
    return noktalar if 2 <= len(noktalar) <= ayarlar.ROTA_MAKS_NOKTA else None


async def _rota(profil: str, koordinatlar: str, overview: str, geometries: str) -> JSONResponse:
    """Ortak OSRM rota islemi."""
    maliyet = valhalla.maliyet_modeli(profil)
    noktalar = _koordinatlar(koordinatlar)
    if maliyet is None or noktalar is None:
        return _hata(400, "InvalidQuery", "Profil veya koordinatlar gecersiz.")
    try:
        veri = await valhalla.rota(noktalar, maliyet, geometries if geometries in ("geojson", "polyline", "polyline6") else "geojson")
    except AltServisYok:
        return _hata(400, "NoRoute", "Rota bulunamadi.")
    except AltServisHatasi:
        return _hata(502, "ServiceUnavailable", "Rota servisi su an yanit vermiyor.")
    if overview == "false":
        for r in veri["routes"]:
            r.pop("geometry", None)
    return JSONResponse(content=veri)


@router.get("/osrm/route/v1/{profil}/{koordinatlar}")
async def osrm_rota_baslik(profil: str, koordinatlar: str, overview: str = Query(default="simplified"),
                           geometries: str = Query(default="polyline"), _proje: dict = Depends(yetki("rota"))) -> JSONResponse:
    """OSRM uyumlu rota (anahtar basliktan)."""
    return await _rota(profil, koordinatlar, overview, geometries)


@router.get("/k/{anahtar}/osrm/route/v1/{profil}/{koordinatlar}")
async def osrm_rota_yol(anahtar: str, profil: str, koordinatlar: str, overview: str = Query(default="simplified"),
                        geometries: str = Query(default="polyline"), _proje: dict = Depends(yetki("rota"))) -> JSONResponse:
    """OSRM uyumlu rota (anahtar yoldan; yalniz ic ag / sunucu cagrilari icin onerilir)."""
    return await _rota(profil, koordinatlar, overview, geometries)
