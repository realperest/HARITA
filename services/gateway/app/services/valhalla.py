"""Valhalla istemcisi: rota (OSRM bicimli yanit) ve sure / mesafe matrisi."""

import logging

import httpx

from app.config import ayarlar
from app.schemas.harita import Nokta
from app.services.http import AltServisHatasi, AltServisYok, istemci

log = logging.getLogger(__name__)

# Hem kendi profil adlarimiz hem OSRM profil adlari Valhalla maliyet modeline eslenir
COSTING = {
    "auto": "auto", "driving": "auto", "car": "auto",
    "motosiklet": "motorcycle", "motorcycle": "motorcycle",
    "bisiklet": "bicycle", "bicycle": "bicycle", "bike": "bicycle", "cycling": "bicycle",
    "yaya": "pedestrian", "foot": "pedestrian", "walking": "pedestrian",
}


def maliyet_modeli(profil: str) -> str | None:
    """Profil adindan Valhalla maliyet modeli; bilinmiyorsa None."""
    return COSTING.get(profil.lower())


def polyline_coz(metin: str, hassasiyet: int) -> list[list[float]]:
    """Kodlanmis polyline'i [boylam, enlem] listesine cevirir (hassasiyet 5 veya 6)."""
    carpan = 10 ** hassasiyet
    indeks, enlem, boylam, sonuc = 0, 0, 0, []
    while indeks < len(metin):
        for hedef in ("enlem", "boylam"):
            kaydirma, deger = 0, 0
            while True:
                bayt = ord(metin[indeks]) - 63
                indeks += 1
                deger |= (bayt & 0x1F) << kaydirma
                kaydirma += 5
                if bayt < 0x20:
                    break
            fark = ~(deger >> 1) if deger & 1 else deger >> 1
            if hedef == "enlem":
                enlem += fark
            else:
                boylam += fark
        sonuc.append([boylam / carpan, enlem / carpan])
    return sonuc


async def _istek(yol: str, govde: dict) -> dict:
    """Valhalla'ya POST atar; hata durumunu AltServisHatasi / AltServisYok'a cevirir."""
    try:
        yanit = await istemci().post(f"{ayarlar.ROTA_ADRESI}{yol}", json=govde)
    except httpx.HTTPError as hata:
        log.error("Valhalla ulasilamadi: %s", type(hata).__name__)
        raise AltServisHatasi("rota servisi ulasilamadi") from hata
    if yanit.status_code == 400:
        # 442/443/171: yol bulunamadi / nokta yola oturtulamadi
        log.info("Valhalla rota bulamadi: %s", yanit.text[:200])
        raise AltServisYok("rota bulunamadi")
    if yanit.status_code != 200:
        log.error("Valhalla beklenmeyen yanit %s: %s", yanit.status_code, yanit.text[:200])
        raise AltServisHatasi("rota servisi hata verdi")
    return yanit.json()


async def rota(noktalar: list[Nokta], maliyet: str, geometri: str = "geojson") -> dict:
    """Rota ister; OSRM bicimli yanit sozlugunu dondurur. geometri: geojson | polyline | polyline6 | yok."""
    govde = {
        "locations": [{"lat": n.lat, "lon": n.lon} for n in noktalar],
        "costing": maliyet,
        "format": "osrm",
        "banner_instructions": False,
        "voice_instructions": False,
        "directions_options": {"units": "kilometers"},
    }
    govde["shape_format"] = {"geojson": "geojson", "polyline": "polyline5", "polyline6": "polyline6"}.get(geometri, "geojson")
    veri = await _istek("/route", govde)
    if not veri.get("routes"):
        raise AltServisYok("rota bulunamadi")
    return veri


def geojson_geometri(rota_sozlugu: dict) -> dict | None:
    """OSRM bicimli rotadan GeoJSON LineString uretir (geometri polyline ise cozer)."""
    geometri = rota_sozlugu.get("geometry")
    if isinstance(geometri, dict):
        return geometri
    if isinstance(geometri, str) and geometri:
        return {"type": "LineString", "coordinates": polyline_coz(geometri, 6)}
    return None


async def hazir_mi() -> bool:
    """Valhalla durum ucu yanit veriyor mu."""
    try:
        yanit = await istemci().get(f"{ayarlar.ROTA_ADRESI}/status", timeout=3.0)
    except httpx.HTTPError:
        return False
    return yanit.status_code == 200


async def matris(kaynaklar: list[Nokta], hedefler: list[Nokta], maliyet: str) -> dict:
    """Sure (sn) ve mesafe (m) matrisi; ulasilamayan hucre None."""
    veri = await _istek("/sources_to_targets", {
        "sources": [{"lat": n.lat, "lon": n.lon} for n in kaynaklar],
        "targets": [{"lat": n.lat, "lon": n.lon} for n in hedefler],
        "costing": maliyet,
    })
    satirlar = veri.get("sources_to_targets") or []
    sure = [[h.get("time") for h in satir] for satir in satirlar]
    mesafe = [[(h["distance"] * 1000 if h.get("distance") is not None else None) for h in satir] for satir in satirlar]
    return {"sure_sn": sure, "mesafe_m": mesafe}
