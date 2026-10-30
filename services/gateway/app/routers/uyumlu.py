"""Standart uyumlu uclar: Nominatim ve Photon bicimi. Bu servislerle yazilmis istemciler yalniz adresi degistirerek baglanir."""

from fastapi import APIRouter, Depends, Query

from app.crud import adres as adres_crud
from app.security import yetki

router = APIRouter(tags=["uyumlu"])

# Kendi tur adlarimizdan Nominatim class / type
NOMINATIM_SINIF = {"sokak": ("highway", "road"), "kapi": ("place", "house"), "yer": ("amenity", "yer")}


def _nominatim(r: dict) -> dict:
    """Kendi sonucumuzu Nominatim ogesine cevirir."""
    sinif, tur = NOMINATIM_SINIF.get(r["tur"], ("boundary", "administrative" if r["tur"] in ("il", "ilce", "mahalle_koy") else "place"))
    adres = {"country": "Türkiye", "country_code": "tr"}
    if r.get("il"):
        adres["state"] = r["il"]
    if r.get("ilce"):
        adres["town"] = r["ilce"]
    if r.get("mahalle"):
        adres["suburb"] = r["mahalle"]
    if r["tur"] == "kapi":
        adres["road"], adres["house_number"] = r["ek"].get("sokak"), r["ek"].get("kapi_no")
    elif r["tur"] == "sokak":
        adres["road"] = r["ad"]
    elif r["tur"] == "yer":
        adres["amenity"] = r["ad"]
    return {"place_id": r["id"], "lat": str(r["merkez"]["lat"]), "lon": str(r["merkez"]["lon"]), "display_name": r["adres"] or r["ad"],
            "class": sinif, "type": tur, "importance": r["skor"] or 0.5, "address": adres, "name": r["ad"]}


def _photon(r: dict) -> dict:
    """Kendi sonucumuzu Photon GeoJSON ogesine cevirir."""
    p = {"osm_id": r["id"], "name": r["ad"], "country": "Türkiye", "countrycode": "TR", "type": r["tur"]}
    if r.get("il"):
        p["state"] = r["il"]
    if r.get("ilce"):
        p["city"] = r["ilce"]
    if r.get("mahalle"):
        p["district"] = r["mahalle"]
    if r["tur"] == "kapi":
        p["street"], p["housenumber"] = r["ek"].get("sokak"), r["ek"].get("kapi_no")
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["merkez"]["lon"], r["merkez"]["lat"]]}, "properties": p}


@router.get("/nominatim/search")
async def nominatim_arama(q: str = Query(min_length=2, max_length=200), limit: int = Query(default=10, ge=1, le=50),
                          _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Nominatim /search uyumlu (format=jsonv2 benzeri) yanit."""
    return [_nominatim(r) for r in await adres_crud.ara(q, None, None, None, None, limit)]


@router.get("/nominatim/reverse")
async def nominatim_ters(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                         _proje: dict = Depends(yetki("adres"))) -> dict:
    """Nominatim /reverse uyumlu yanit."""
    v = await adres_crud.nokta(lat, lon, 150, 1)
    ilk = (v["kapilar"] or v["sokaklar"] or v["yerler"] or [None])[0]
    adres = {"country": "Türkiye", "country_code": "tr", "state": v["il"], "town": v["ilce"], "suburb": v["mahalle"]}
    if ilk and ilk["tur"] == "sokak":
        adres["road"] = ilk["ad"]
    if ilk and ilk["tur"] == "kapi":
        adres["road"], adres["house_number"] = ilk["ek"].get("sokak"), ilk["ek"].get("kapi_no")
    return {"lat": str(lat), "lon": str(lon), "display_name": v["adres"], "address": {k: x for k, x in adres.items() if x}}


@router.get("/photon/api")
async def photon_arama(q: str = Query(min_length=2, max_length=200), limit: int = Query(default=10, ge=1, le=50),
                       lat: float | None = Query(default=None, ge=-90, le=90), lon: float | None = Query(default=None, ge=-180, le=180),
                       _proje: dict = Depends(yetki("adres"))) -> dict:
    """Photon /api uyumlu GeoJSON yanit (kendi indeksimizden)."""
    return {"type": "FeatureCollection", "features": [_photon(r) for r in await adres_crud.ara(q, None, None, lat, lon, limit)]}


@router.get("/photon/reverse")
async def photon_ters(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Photon /reverse uyumlu GeoJSON yanit."""
    v = await adres_crud.nokta(lat, lon, 150, 1)
    ilk = (v["kapilar"] or v["sokaklar"] or v["yerler"] or [None])[0]
    return {"type": "FeatureCollection", "features": [_photon(ilk)] if ilk else []}
