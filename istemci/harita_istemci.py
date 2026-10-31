"""HARITA Python istemcisi: arka uclarin (FastAPI vb.) harita servisini tek dosyayla kullanmasini saglar.

Gereksinim: httpx==0.28.1 (SIPARIS'te zaten var; MotoConvoy'da requirements.txt'e eklenmeli).

Kullanim:
    from harita_istemci import HaritaIstemcisi

    harita = HaritaIstemcisi()                     # HARITA_API_ADRESI ve HARITA_SUNUCU_ANAHTARI ortam degiskenlerinden
    rota = await harita.rota([(40.99, 29.02), (40.98, 29.03)], profil="motosiklet")
    adres = await harita.adres_nokta(40.99, 29.02)
    await harita.kapat()                           # uygulama kapanirken (FastAPI lifespan)

Butun noktalar (enlem, boylam) ikilisi ya da {"lat": .., "lon": ..} sozlugu olarak verilebilir.
Hatalar HaritaHatasi olarak atilir: .durum HTTP kodu, .mesaj kullaniciya gosterilebilecek sade metin.
Anahtar yalniz sunucuda kalir; tarayiciya ayri web anahtari verilir (bkz. docs/ENTEGRASYON.md).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Literal

import httpx

log = logging.getLogger(__name__)

Profil = Literal["auto", "motosiklet", "bisiklet", "yaya"]
Nokta = tuple[float, float] | dict[str, float]

HATA_METNI = {
    400: "Istek gecersiz ya da bu noktalar arasinda rota yok.",
    401: "Harita anahtari gecersiz.",
    403: "Bu servis icin izin yok.",
    404: "Sonuc bulunamadi.",
    413: "Istek cok buyuk.",
    422: "Girilen deger gecersiz.",
    429: "Harita servisi istek siniri asildi.",
    502: "Rota servisi su an yanit vermiyor.",
    503: "Harita servisi hazir degil.",
}


class HaritaHatasi(Exception):
    """Harita servisi hatasi. durum: HTTP kodu (ag hatasinda 0), mesaj: sade aciklama."""

    def __init__(self, durum: int, mesaj: str):
        super().__init__(f"HARITA {durum}: {mesaj}")
        self.durum = durum
        self.mesaj = mesaj


def _nokta(n: Nokta) -> dict[str, float]:
    """(enlem, boylam) ya da {"lat","lon"} -> {"lat","lon"}."""
    if isinstance(n, dict):
        return {"lat": float(n["lat"]), "lon": float(n["lon"])}
    return {"lat": float(n[0]), "lon": float(n[1])}


class HaritaIstemcisi:
    """HARITA API'sinin tum uclarini saran asenkron istemci. Tek ornek uygulama boyunca paylasilmalidir."""

    def __init__(self, api_adresi: str | None = None, anahtar: str | None = None, zaman_asimi: float = 10.0):
        self.api_adresi = (api_adresi or os.environ.get("HARITA_API_ADRESI", "")).rstrip("/")
        self.anahtar = anahtar or os.environ.get("HARITA_SUNUCU_ANAHTARI", "")
        if not self.api_adresi or not self.anahtar:
            raise ValueError("HARITA_API_ADRESI ve HARITA_SUNUCU_ANAHTARI gerekli.")
        self._http = httpx.AsyncClient(base_url=self.api_adresi, timeout=zaman_asimi,
                                       headers={"X-Harita-Anahtar": self.anahtar, "User-Agent": "harita-istemci-py/1.0"})

    async def kapat(self) -> None:
        """HTTP baglantilarini kapatir."""
        await self._http.aclose()

    async def _istek(self, yontem: str, yol: str, params: dict | None = None, govde: Any = None) -> Any:
        """Ortak istek; hata kodlarini HaritaHatasi'na cevirir, teknik ayrintiyi loga yazar."""
        temiz = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            yanit = await self._http.request(yontem, yol, params=temiz, json=govde)
        except httpx.HTTPError as hata:
            log.error("HARITA istegi basarisiz %s %s: %s", yontem, yol, type(hata).__name__)
            raise HaritaHatasi(0, "Harita servisine ulasilamadi.") from hata
        if yanit.status_code >= 400:
            log.warning("HARITA hata kodu %s %s %s: %s", yanit.status_code, yontem, yol, yanit.text[:300])
            raise HaritaHatasi(yanit.status_code, HATA_METNI.get(yanit.status_code, "Harita servisi hatasi."))
        return yanit.json()

    # ---------- Yapilandirma ----------

    async def yapilandirma(self) -> dict:
        """Karo, yazi tipi ve simge adresleri (tarayiciya harita kurdurmak icin)."""
        return await self._istek("GET", "/v1/yapilandirma")

    # ---------- Rota ----------

    async def rota(self, noktalar: Iterable[Nokta], profil: Profil = "auto", geometri: bool = True) -> dict:
        """Noktalar arasi rota: {sure_sn, mesafe_m, geometri (GeoJSON LineString)}. En fazla 20 nokta."""
        return await self._istek("POST", "/v1/rota", govde={"noktalar": [_nokta(n) for n in noktalar], "profil": profil, "geometri": geometri})

    async def matris(self, kaynaklar: Iterable[Nokta], hedefler: Iterable[Nokta], profil: Profil = "auto") -> dict:
        """Sure / mesafe matrisi: {sure_sn: [[..]], mesafe_m: [[..]]}. En fazla 50 x 50."""
        return await self._istek("POST", "/v1/matris", govde={"kaynaklar": [_nokta(n) for n in kaynaklar],
                                                              "hedefler": [_nokta(n) for n in hedefler], "profil": profil})

    async def valhalla(self, uc: str, govde: dict) -> dict:
        """Valhalla'nin tam API'si: route, optimized_route, sources_to_targets, isochrone, trace_route,
        trace_attributes, locate, expansion, centroid, height. Govde Valhalla bicimindedir."""
        return await self._istek("POST", f"/valhalla/{uc}", govde=govde)

    async def adim_adim_rota(self, noktalar: Iterable[Nokta], costing: str = "auto", dil: str = "tr-TR") -> dict:
        """Turkce adim adim talimatli rota (navigasyon icin; Valhalla route yaniti)."""
        return await self.valhalla("route", {"locations": [_nokta(n) for n in noktalar], "costing": costing,
                                             "directions_options": {"language": dil, "units": "kilometers"}})

    def osrm_adresi(self) -> str:
        """OSRM bekleyen kod icin taban adres (OSRM_ADRESI). Anahtar yoldadir; yalniz sunucuda kullanin."""
        return f"{self.api_adresi}/k/{self.anahtar}/osrm"

    # ---------- Arama ve adres ----------

    async def ara(self, metin: str, yakin: Nokta | None = None, limit: int = 7) -> dict:
        """Genel arama (GeoJSON FeatureCollection, Photon bicimi). yakin verilirse o civar one cikar."""
        n = _nokta(yakin) if yakin else {}
        return await self._istek("GET", "/v1/arama", {"q": metin, "limit": limit, "lat": n.get("lat"), "lon": n.get("lon")})

    async def ters_ara(self, enlem: float, boylam: float) -> dict:
        """Koordinattan en yakin kapi, sokak ya da yer (GeoJSON)."""
        return await self._istek("GET", "/v1/ters-arama", {"lat": enlem, "lon": boylam})

    async def adres_ara(self, metin: str, tur: str | None = None, ust_id: int | None = None, yakin: Nokta | None = None,
                        limit: int = 10) -> list[dict]:
        """Kapi numarasi, sokak, bina, yer, yerlesim aramasi. tur: kapi | sokak | bina | yer | yerlesim."""
        n = _nokta(yakin) if yakin else {}
        return await self._istek("GET", "/v1/adres/ara", {"q": metin, "tur": tur, "ust_id": ust_id, "lat": n.get("lat"),
                                                          "lon": n.get("lon"), "limit": limit})

    async def adres_nokta(self, enlem: float, boylam: float, yaricap_m: int = 150) -> dict:
        """Pin -> adres: adres metni, il / ilce / mahalle, en yakin sokak, kapi ve yerler."""
        return await self._istek("GET", "/v1/adres/nokta", {"lat": enlem, "lon": boylam, "yaricap_m": yaricap_m})

    async def adres_alt(self, ust: str, cocuk: str | None = None, limit: int = 200, atla: int = 0) -> list[dict]:
        """Acilir liste agaci: ust 'il:34', 'ilce:123', 'mahalle_koy:456', 'sokak:789'; cocuk: sokak | bina | kapi."""
        return await self._istek("GET", "/v1/adres/alt", {"ust": ust, "cocuk": cocuk, "limit": limit, "atla": atla})

    async def mahalle_sokaklari(self, mahalle_id: int, q: str | None = None, limit: int = 200) -> list[dict]:
        """Mahalle / koydeki cadde ve sokaklar."""
        return await self._istek("GET", f"/v1/adres/mahalle/{mahalle_id}/sokaklar", {"q": q, "limit": limit})

    async def sokak_kapilari(self, sokak_id: int, limit: int = 200) -> list[dict]:
        """Sokaktaki kapi numaralari."""
        return await self._istek("GET", f"/v1/adres/sokak/{sokak_id}/kapilar", {"limit": limit})

    async def sekil(self, tur: str, kimlik: int) -> dict:
        """Ogenin sekli: {tur, id, ad, geometri (GeoJSON)}; il / ilce / mahalle siniri, sokak cizgisi, bina poligonu."""
        return await self._istek("GET", "/v1/adres/sekil", {"tur": tur, "id": kimlik})

    async def yakin_yerler(self, enlem: float, boylam: float, tur: str | None = None, yaricap_m: int = 5000, limit: int = 20) -> list[dict]:
        """En yakin yerler (or. tur='akaryakit', 'eczane', 'otel')."""
        return await self._istek("GET", "/v1/adres/yakin", {"lat": enlem, "lon": boylam, "tur": tur, "yaricap_m": yaricap_m, "limit": limit})

    async def rota_boyunca(self, koordinatlar: list[list[float]], tur: str | None = None, tampon_m: int = 500, limit: int = 100) -> list[dict]:
        """Rota cizgisi ([boylam, enlem] listesi) boyunca yerler, rota sirasina gore."""
        return await self._istek("POST", "/v1/adres/rota-boyunca", govde={"koordinatlar": koordinatlar, "tur": tur,
                                                                          "tampon_m": tampon_m, "limit": limit})

    # ---------- Yerlesim (il, ilce, mahalle / koy) ----------

    async def yerlesim_ara(self, metin: str, tur: str | None = None, ust_id: int | None = None, limit: int = 10) -> list[dict]:
        """Il, ilce, mahalle_koy, sehir, kasaba, koy, mezra, semt aramasi (Turkce karakter duyarsiz)."""
        return await self._istek("GET", "/v1/yerlesim/ara", {"q": metin, "tur": tur, "ust_id": ust_id, "limit": limit})

    async def yerlesim_nokta(self, enlem: float, boylam: float) -> dict:
        """Noktanin il / ilce / mahalle-koy bilgisi."""
        return await self._istek("GET", "/v1/yerlesim/nokta", {"lat": enlem, "lon": boylam})

    async def yerlesim_alt(self, yerlesim_id: int, tur: str | None = None, limit: int = 100, atla: int = 0) -> list[dict]:
        """Alt ogeler (ilin ilceleri, ilcenin mahalleleri ...)."""
        return await self._istek("GET", f"/v1/yerlesim/{yerlesim_id}/alt", {"tur": tur, "limit": limit, "atla": atla})
