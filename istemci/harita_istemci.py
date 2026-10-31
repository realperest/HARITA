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
                        limit: int = 10, yaricap_m: int | None = None) -> list[dict]:
        """Kapi numarasi, sokak, bina, yer, yerlesim aramasi. tur: kapi | sokak | bina | yer | yerlesim.
        yakin verilirse esit eslesmelerde yakin olan one gelir; yaricap_m (yakin gerekir) bu yaricap disini eler."""
        n = _nokta(yakin) if yakin else {}
        return await self._istek("GET", "/v1/adres/ara", {"q": metin, "tur": tur, "ust_id": ust_id, "lat": n.get("lat"),
                                                          "lon": n.get("lon"), "limit": limit, "yaricap_m": yaricap_m})

    async def adres_ayristir(self, metin: str | list[str], baglam: Nokta | None = None, ilce_id: int | None = None) -> dict | list[dict]:
        """Serbest yazilmis adresi ayristirir ve dogrular: parcalar (il, ilce, mahalle, sokak, kapi, bina, blok, kat, daire,
        posta kodu, tarif), duzgun adres, konum (kesinlik: kapi | bina | sokak | mahalle_koy | ilce | il), 0-100 puan, oneriler.
        Puan 85 ve ustu otomatik kabul edilebilir; altinda kullaniciya onaylatin. Liste verilirse (en fazla 100) liste doner.
        baglam: isletme / kullanici konumu (metinde ilce yoksa o cevrede aranir)."""
        govde: dict[str, Any] = {"metinler": metin} if isinstance(metin, list) else {"metin": metin}
        if baglam:
            govde.update(_nokta(baglam))
        if ilce_id:
            govde["ilce_id"] = ilce_id
        return await self._istek("POST", "/v1/adres/ayristir", govde=govde)

    async def toplu(self, ogeler: Iterable[tuple[str, int]]) -> list[dict]:
        """(tur, id) ogeleri tek istekte: ad, adres, zincir kimlikleri (ust) ve kaynak anahtari. En fazla 500.
        tur: sokak, kapi, yer, bina ya da il, ilce, mahalle_koy ... Bulunamayan oge donmez."""
        return await self._istek("POST", "/v1/adres/toplu", govde={"ogeler": [{"tur": t, "id": i} for t, i in ogeler]})

    async def kaynaktan(self, anahtarlar: Iterable[str]) -> list[dict]:
        """OSM kaynak anahtarindan (osm:node:.. / osm:way:.. / osm:relation:..) HARITA kayitlari. En fazla 500."""
        return await self._istek("POST", "/v1/adres/kaynak", govde={"anahtarlar": list(anahtarlar)})

    async def en_yakin_kapi(self, sokak_id: int, enlem: float, boylam: float, yaricap_m: int = 100) -> dict | None:
        """Secilen sokaktaki en yakin kapi numarasi (pin icin oneri); yaricapta yoksa None."""
        try:
            return await self._istek("GET", f"/v1/adres/sokak/{sokak_id}/en-yakin-kapi", {"lat": enlem, "lon": boylam, "yaricap_m": yaricap_m})
        except HaritaHatasi as hata:
            if hata.durum == 404:
                return None
            raise

    async def ilce_sokaklari(self, ilce_id: int, limit: int = 200, atla: int = 0) -> list[dict]:
        """Hicbir mahalle / koy sinirina dusmeyip dogrudan ilceye bagli yollar."""
        return await self.adres_alt(f"ilce:{ilce_id}", cocuk="sokak", limit=limit, atla=atla)

    # ---------- Yol bilgisi ve baglantilar ----------

    async def yol_bilgisi(self, enlem: float, boylam: float, profil: Profil = "auto", yon: int | None = None) -> dict:
        """Konumdaki yolun ozellikleri (sinif, hiz siniri, trafik isigi, dur levhasi, tunel, kopru, gise) ve il / ilce."""
        return await self._istek("GET", "/v1/yol/nokta", {"lat": enlem, "lon": boylam, "profil": profil, "yon": yon})

    async def baglanti_coz(self, adres: str) -> list[dict]:
        """Google / Yandex / Apple / Waze / OSM harita baglantisindaki noktalar [{lat, lon}] (kisa baglantilar dahil)."""
        return (await self._istek("GET", "/v1/baglanti/coz", {"adres": adres}))["noktalar"]

    @staticmethod
    def navigasyon_baglantisi(duraklar: Iterable[Nokta], adlar: Iterable[str] | None = None, profil: str = "araba",
                              sayfa: str | None = None) -> str:
        """HARITA navigasyon ekranini duraklarla acan baglanti (kurye / surucu icin Yandex / Google yerine).
        profil: araba | motosiklet | yaya. sayfa: HARITA_NAVIGASYON_ADRESI ortam degiskeni ya da deneme sayfasi."""
        from urllib.parse import urlencode
        taban = sayfa or os.environ.get("HARITA_NAVIGASYON_ADRESI", "https://harita-deneme.89.45.45.152.sslip.io/navigasyon.html")
        noktalar = ";".join(f"{n['lat']:.6f},{n['lon']:.6f}" for n in map(_nokta, duraklar))
        parametre = {"duraklar": noktalar, "profil": profil}
        if adlar:
            parametre["adlar"] = "|".join(a.replace("|", " ") for a in adlar)
        return f"{taban}?{urlencode(parametre)}"

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

    # ---------- Yol uyarilari, hava, trafik ----------

    @staticmethod
    def _cizgi(cizgi: str | list[list[float]]) -> dict[str, Any]:
        """Cizgi govdesi: Valhalla polyline6 metni ya da [[lat, lon], ...]."""
        return {"polyline": cizgi} if isinstance(cizgi, str) else {"noktalar": cizgi}

    async def yol_uyarilari(self, cizgi: str | list[list[float]], tampon_m: float = 25, turler: list[str] | None = None) -> list[dict]:
        """Rota boyunca hiz kamerasi / hiz kesici. rota_m: rota basindan uzaklik (sirali)."""
        govde = {**self._cizgi(cizgi), "tampon_m": tampon_m, "turler": turler}
        return (await self._istek("POST", "/v1/yol/uyarilar", govde=govde))["uyarilar"]

    async def rota_havasi(self, cizgi: str | list[list[float]], sure_sn: float | None = None, kalkis: str | None = None) -> dict:
        """Rota boyunca varis saatindeki hava ve surus uyarilari (firtina, kar, buzlanma, kuvvetli_yagis, kuvvetli_ruzgar, sis)."""
        return await self._istek("POST", "/v1/yol/hava", govde={**self._cizgi(cizgi), "sure_sn": sure_sn, "kalkis": kalkis})

    async def trafik_izi(self, noktalar: list[dict], profil: Profil = "motosiklet") -> dict:
        """Bir surusun GPS izini (lat, lon, zaman Unix sn; artan sirada, en az 5) ortak trafik profiline katar. Kimlik saklanmaz."""
        return await self._istek("POST", "/v1/trafik/iz", govde={"profil": profil, "noktalar": noktalar})

    async def trafik_suresi(self, cizgi: str | list[list[float]], profil: Profil = "motosiklet", zaman: str | None = None) -> dict:
        """Ogrenilmis yol hizlariyla rota suresi: valhalla_sure_sn, tahmini_sure_sn, kapsama."""
        return await self._istek("POST", "/v1/trafik/sure", govde={**self._cizgi(cizgi), "profil": profil, "zaman": zaman})

    # ---------- Planlama ----------

    async def planla(self, araclar: list[dict], gorevler: list[dict] | None = None, gonderiler: list[dict] | None = None,
                     profil: Profil = "motosiklet", geometri: bool = False) -> dict:
        """Cok kuryeli planlama (VROOM): hangi kurye hangi isi hangi sirayla. Arac: {id, baslangic, bitis?, kapasite?, beceriler?,
        calisma?, maks_gorev?}; gorev: {id, konum, sure_sn?, miktar?, zaman_araliklari?, oncelik?}; gonderi: {id, alim, teslim, miktar?}."""
        return await self._istek("POST", "/v1/planla", govde={"profil": profil, "araclar": araclar, "gorevler": gorevler or [],
                                                              "gonderiler": gonderiler or [], "geometri": geometri})

    async def en_yakin(self, hedef: Nokta, adaylar: list[dict], profil: Profil = "motosiklet", adet: int = 5) -> list[dict]:
        """Adaylari ({id, konum}) hedefe gercek yol suresine gore siralar: [{id, sure_sn, mesafe_m}]."""
        govde = {"hedef": _nokta(hedef), "adaylar": adaylar, "profil": profil, "adet": adet}
        return (await self._istek("POST", "/v1/en-yakin", govde=govde))["adaylar"]

    # ---------- Kapi havuzu ----------

    async def kapi_ogren(self, sokak_id: int, kapi_no: str, enlem: float, boylam: float, dogruluk_m: float | None = None) -> dict:
        """Teslimat konumundan kapi numarasi ogretir (ortak havuz). OSM'de varsa durum "osm_var"."""
        govde = {"sokak_id": sokak_id, "kapi_no": kapi_no, "lat": enlem, "lon": boylam, "dogruluk_m": dogruluk_m}
        return await self._istek("POST", "/v1/adres/kapi-ogren", govde=govde)

    async def kapi_ogren_geri_al(self, kapi_id: int) -> dict:
        """Bu projenin kapi gozlemlerini geri alir (yanlis bildirim)."""
        return await self._istek("DELETE", f"/v1/adres/kapi-ogren/{kapi_id}")

    async def ogrenilen_kapilar(self, sokak_id: int) -> list[dict]:
        """Sokakta havuzdan ogrenilmis kapilar."""
        return await self._istek("GET", f"/v1/adres/sokak/{sokak_id}/ogrenilen-kapilar")

    # ---------- Paylasim ve GPX ----------

    async def paylasim_olustur(self, duraklar: list[dict], profil: str = "araba", ad: str | None = None, sure_saat: int = 72) -> dict:
        """Duraklari kisa kodla paylasir: {kod, bitis}. Navigasyon baglantisi: <navigasyon sayfasi>?kod=<kod>."""
        return await self._istek("POST", "/v1/paylasim", govde={"duraklar": duraklar, "profil": profil, "ad": ad, "sure_saat": sure_saat})

    async def paylasim_getir(self, kod: str) -> dict:
        """Paylasilan rota: {ad, profil, duraklar, bitis}."""
        return await self._istek("GET", f"/v1/paylasim/{kod}")

    async def paylasim_sil(self, kod: str) -> dict:
        """Projenin kendi paylasimini iptal eder."""
        return await self._istek("DELETE", f"/v1/paylasim/{kod}")

    async def _ham(self, yol: str, **secenek: Any) -> httpx.Response:
        """JSON olmayan govde / yanit icin istek; hata kodlarini HaritaHatasi'na cevirir."""
        try:
            yanit = await self._http.post(yol, **secenek)
        except httpx.HTTPError as hata:
            log.error("HARITA istegi basarisiz POST %s: %s", yol, type(hata).__name__)
            raise HaritaHatasi(0, "Harita servisine ulasilamadi.") from hata
        if yanit.status_code >= 400:
            log.warning("HARITA hata kodu %s POST %s: %s", yanit.status_code, yol, yanit.text[:300])
            raise HaritaHatasi(yanit.status_code, HATA_METNI.get(yanit.status_code, "Harita servisi hatasi."))
        return yanit

    async def gpx_olustur(self, duraklar: list[dict], cizgi: str | list[list[float]] | None = None, ad: str | None = None) -> str:
        """Duraklar ve (varsa) rota cizgisinden GPX 1.1 metni."""
        govde: dict[str, Any] = {"duraklar": duraklar, "ad": ad, **(self._cizgi(cizgi) if cizgi else {})}
        return (await self._ham("/v1/gpx/olustur", json=govde)).text

    async def gpx_oku(self, metin: str | bytes, iz_takip: bool = False) -> dict:
        """GPX dosyasini okur: duraklar (iz_takip ile izden ara noktalar), yol_noktalari, rotalar, izler."""
        govde = metin.encode("utf-8") if isinstance(metin, str) else metin
        return (await self._ham("/v1/gpx/oku", params={"iz_takip": str(iz_takip).lower()}, content=govde)).json()

    # ---------- Canli konum ve cevrimdisi ----------

    async def canli_konum(self, kanal: str, cihaz_id: str, enlem: float, boylam: float, **ek: Any) -> list[dict]:
        """Sunucudan konum yayini (hiz, yon, dogruluk, veri istege bagli). Donus: olaylar (bolge giris / cikis dahil)."""
        govde = {"id": cihaz_id, "lat": enlem, "lon": boylam, **ek}
        return (await self._istek("POST", f"/v1/canli/{kanal}/konum", govde=govde))["olaylar"]

    async def canli_konumlar(self, kanal: str) -> list[dict]:
        """Kanaldaki son konumlar (son 1 saat)."""
        return await self._istek("GET", f"/v1/canli/{kanal}/konumlar")

    async def canli_bolgeler(self, kanal: str, bolgeler: list[dict] | None = None) -> Any:
        """bolgeler verilirse kanalin bolgelerini degistirir ({id, ad, merkez + yaricap_m | poligon}); verilmezse listeler."""
        if bolgeler is None:
            return await self._istek("GET", f"/v1/canli/{kanal}/bolgeler")
        return await self._istek("PUT", f"/v1/canli/{kanal}/bolgeler", govde=bolgeler)

    async def cevrimdisi_paketler(self) -> dict:
        """Indirilebilir il paketleri (PMTiles) ve yazi tipi / simge arsivi."""
        return await self._istek("GET", "/v1/cevrimdisi/paketler")
