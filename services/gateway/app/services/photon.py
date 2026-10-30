"""Photon istemcisi: adres / yer arama ve ters arama (GeoJSON yanit)."""

import logging

import httpx

from app.config import ayarlar
from app.services.http import AltServisHatasi, istemci

log = logging.getLogger(__name__)


async def _al(yol: str, parametreler: dict) -> dict:
    """Photon'a GET atar; hatayi AltServisHatasi'na cevirir."""
    try:
        yanit = await istemci().get(f"{ayarlar.ARAMA_ADRESI}{yol}", params=parametreler)
    except httpx.HTTPError as hata:
        log.error("Photon ulasilamadi: %s", type(hata).__name__)
        raise AltServisHatasi("arama servisi ulasilamadi") from hata
    if yanit.status_code != 200:
        log.error("Photon beklenmeyen yanit %s: %s", yanit.status_code, yanit.text[:200])
        raise AltServisHatasi("arama servisi hata verdi")
    return yanit.json()


async def ara(q: str, limit: int, dil: str, lat: float | None, lon: float | None) -> dict:
    """Metinle arama; lat/lon verilirse o civardaki sonuclar one cikar."""
    parametreler: dict = {"q": q, "limit": limit, "lang": dil}
    if lat is not None and lon is not None:
        parametreler.update({"lat": lat, "lon": lon})
    return await _al("/api", parametreler)


async def ters_ara(lat: float, lon: float, dil: str, limit: int) -> dict:
    """Koordinattan en yakin adres / yer."""
    return await _al("/reverse", {"lat": lat, "lon": lon, "lang": dil, "limit": limit})


async def hazir_mi() -> bool:
    """Photon durum ucu yanit veriyor mu."""
    try:
        yanit = await istemci().get(f"{ayarlar.ARAMA_ADRESI}/status", timeout=3.0)
    except httpx.HTTPError:
        return False
    return yanit.status_code == 200
