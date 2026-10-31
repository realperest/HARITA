"""Yol bilgisi ve harita baglantisi cozme uclari.

/v1/yol/nokta: bir konumdaki yolun ozellikleri (sinif, hiz, trafik isigi, dur levhasi, tunel, kopru, gise ...) ve idari bolge;
    surus analizleri (or. ani durma: isikta mi, otoyolda mi) icin dis servis (Overpass) gerektirmez.
/v1/baglanti/coz: Google Haritalar / Yandex / Apple / Waze / OSM baglantisindan (kisa baglantilar dahil) koordinatlari cikarir.
"""

import logging
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import ayarlar
from app.crud import yerlesim as yerlesim_crud
from app.security import yetki
from app.services import valhalla
from app.services.http import istemci

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["yol"])

# Yalniz bu alan adlarinin baglantilari acilir (sunucu tarafi istek sahteciligine karsi izin listesi)
IZINLI_ALANLAR = ("google.com", "google.com.tr", "goo.gl", "app.goo.gl", "maps.app.goo.gl", "g.co", "yandex.com", "yandex.com.tr",
                  "yandex.ru", "ya.cc", "apple.com", "waze.com", "openstreetmap.org", "osm.org")
MAKS_YONLENDIRME = 5
SAYI = r"(-?\d{1,3}(?:\.\d+)?)"


def _izinli_mi(adres: str) -> bool:
    """https/http ve izinli alan adi mi."""
    p = urlparse(adres)
    host = (p.hostname or "").lower()
    return p.scheme in ("https", "http") and any(host == a or host.endswith("." + a) for a in IZINLI_ALANLAR)


def _gecerli(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def koordinatlari_cikar(adres: str) -> list[dict]:
    """Harita baglantisindaki noktalar (sirayla, tekrarsiz): [{lat, lon}]. Bulunamazsa bos liste."""
    metin = unquote(adres)
    p = urlparse(metin)
    sorgu = parse_qs(p.query)
    noktalar: list[tuple[float, float]] = []

    def ekle(lat: str, lon: str) -> None:
        a, b = float(lat), float(lon)
        if _gecerli(a, b) and (a, b) not in noktalar:
            noktalar.append((a, b))

    def cift(deger: str, ters: bool = False) -> None:
        m = re.fullmatch(rf"\s*{SAYI}\s*,\s*{SAYI}\s*", deger)
        if m:
            ekle(*(m.group(2), m.group(1)) if ters else (m.group(1), m.group(2)))

    # Yandex: rtext=lat,lon~lat,lon (bos parca = anlik konum), ll=lon,lat, pt=lon,lat
    for deger in sorgu.get("rtext", []):
        for parca in deger.split("~"):
            cift(parca)
    # Google: /dir/lat,lon/lat,lon, origin/destination/waypoints, q / query / daddr / ll (Apple: daddr, ll, q)
    for anahtar in ("origin", "waypoints", "destination", "daddr", "saddr", "q", "query", "ll", "center"):
        for deger in sorgu.get(anahtar, []):
            for parca in re.split(r"[|]|\+to:", deger):
                cift(parca, ters=anahtar == "ll" and "yandex" in (p.hostname or ""))
    for deger in sorgu.get("pt", []):
        cift(deger.split(",pm")[0], ters=True)
    if "/dir/" in p.path:
        for parca in p.path.split("/dir/", 1)[1].split("/"):
            cift(parca)
    # Google yer sayfasi: !3d<lat>!4d<lon> (asil nokta), @lat,lon (harita merkezi; yalniz baska nokta yoksa)
    for m in re.finditer(rf"!3d{SAYI}!4d{SAYI}", metin):
        ekle(m.group(1), m.group(2))
    if not noktalar:
        m = re.search(rf"@{SAYI},{SAYI}", metin)
        if m:
            ekle(m.group(1), m.group(2))
    # OSM: #map=z/lat/lon, mlat/mlon; Waze: ll=lat,lon (yukarida)
    if not noktalar:
        if sorgu.get("mlat") and sorgu.get("mlon"):
            ekle(sorgu["mlat"][0], sorgu["mlon"][0])
        m = re.search(rf"map=\d+/{SAYI}/{SAYI}", metin)
        if m:
            ekle(m.group(1), m.group(2))
    return [{"lat": a, "lon": b} for a, b in noktalar]


@router.get("/baglanti/coz")
async def baglanti_coz(adres: str = Query(min_length=8, max_length=2000), _proje: dict = Depends(yetki("rota"))) -> dict:
    """Paylasilan harita baglantisindaki noktalar. Kisa baglantilar (maps.app.goo.gl vb.) izinli alan adlari icinde takip edilir.
    Donus: {adres (son adres), noktalar: [{lat, lon}]}; nokta yoksa 422."""
    if not _izinli_mi(adres):
        raise HTTPException(status_code=422, detail="Desteklenmeyen baglanti (Google, Yandex, Apple, Waze, OpenStreetMap).")
    son = adres
    noktalar = koordinatlari_cikar(son)
    try:
        for _ in range(MAKS_YONLENDIRME):
            if noktalar:
                break
            yanit = await istemci().get(son, follow_redirects=False, timeout=8.0, headers={"User-Agent": "Mozilla/5.0 harita-gateway"})
            konum = yanit.headers.get("location")
            if yanit.status_code not in (301, 302, 303, 307, 308) or not konum:
                # Yonlendirme yoksa sayfa icindeki ilk Google koordinat izine bak (ornegin consent sayfasi degilse)
                noktalar = koordinatlari_cikar(yanit.text[:200000]) if yanit.status_code == 200 else []
                break
            son = urljoin(son, konum)
            if not _izinli_mi(son):
                raise HTTPException(status_code=422, detail="Baglanti izin verilmeyen bir adrese yonleniyor.")
            noktalar = koordinatlari_cikar(son)
    except httpx.HTTPError as hata:
        log.warning("Baglanti cozulemedi: %s", type(hata).__name__)
        raise HTTPException(status_code=502, detail="Baglanti acilamadi.") from hata
    if not noktalar:
        raise HTTPException(status_code=422, detail="Baglantida konum bulunamadi.")
    return {"adres": son, "noktalar": noktalar}


def _kenar_ozeti(kenar: dict) -> dict:
    """Valhalla locate kenarini sade yol bilgisine cevirir."""
    e = kenar.get("edge") or {}
    bilgi = kenar.get("edge_info") or {}
    sinif = e.get("classification") or {}
    uzunluk = (e.get("geo_attributes") or {}).get("length")
    oran = kenar.get("percent_along")
    sona = round(uzunluk * (1 - oran)) if uzunluk is not None and oran is not None else None
    hiz_siniri = bilgi.get("speed_limit") or None
    return {
        "adlar": bilgi.get("names") or [],
        "sinif": sinif.get("classification"),          # motorway, trunk, primary, secondary, tertiary, unclassified, residential, service_other
        "kullanim": sinif.get("use"),                  # road, ramp, turn_channel, track, driveway, alley, parking_aisle, footway ...
        "yuzey": sinif.get("surface"),
        "baglanti_yolu": bool(sinif.get("link")),
        "hiz_siniri_kmh": hiz_siniri if hiz_siniri and hiz_siniri < 200 else None,
        "tahmini_hiz_kmh": (e.get("speeds") or {}).get("default"),
        "serit": e.get("lane_count"),
        "tek_yon": not bool(e.get("forward")) if "forward" in e else None,
        "trafik_isigi": bool(e.get("traffic_signal")),   # kenarin sonunda (kavsakta) trafik isigi
        "dur_levhasi": bool(e.get("stop_sign")),
        "yol_ver_levhasi": bool(e.get("yield_sign")),
        "gobek": bool(e.get("round_about")),
        "tunel": bool(e.get("tunnel")),
        "kopru": bool(e.get("bridge")),
        "gise": bool(e.get("toll")),
        "cikmaz": bool(e.get("deadend")),
        "uzunluk_m": uzunluk,
        "kavsaga_kalan_m": sona,
        "uzaklik_m": round(kenar["distance"]) if kenar.get("distance") is not None else None,
        "osm_yol_id": bilgi.get("way_id"),
    }


@router.get("/yol/nokta")
async def yol_noktasi(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                      profil: str = Query(default="auto", max_length=20), yon: int | None = Query(default=None, ge=0, le=360),
                      _proje: dict = Depends(yetki("rota"))) -> dict:
    """Konumdaki yolun ozellikleri ve idari bolgesi. yon (derece) verilirse gidis yonundeki yol secilir.
    trafik_isigi / dur_levhasi kenarin sonundaki kavsagi anlatir; kavsaga_kalan_m ile birlikte yorumlanir."""
    maliyet = valhalla.maliyet_modeli(profil)
    if maliyet is None:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    nokta = {"lat": lat, "lon": lon}
    if yon is not None:
        nokta.update(heading=yon, heading_tolerance=60)
    try:
        yanit = await istemci().post(f"{ayarlar.ROTA_ADRESI}/locate", json={"locations": [nokta], "costing": maliyet, "verbose": True})
    except httpx.HTTPError as hata:
        log.error("Valhalla locate ulasilamadi: %s", type(hata).__name__)
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
    if yanit.status_code != 200:
        log.info("Valhalla locate %s: %s", yanit.status_code, yanit.text[:200])
        raise HTTPException(status_code=404, detail="Bu konumda yol bulunamadi.")
    kenarlar = (yanit.json() or [{}])[0].get("edges") or []
    if not kenarlar:
        raise HTTPException(status_code=404, detail="Bu konumda yol bulunamadi.")
    idari = await yerlesim_crud.noktada(lat, lon)
    icinde = {s["tur"]: s["ad"] for s in idari["icinde"]}
    return {
        "yol": _kenar_ozeti(kenarlar[0]),
        "diger_yonler": [_kenar_ozeti(k) for k in kenarlar[1:3]],
        "il": icinde.get("il"), "ilce": icinde.get("ilce"), "mahalle_koy": icinde.get("mahalle_koy"),
        "en_yakin_merkez": idari["en_yakin_merkez"],
    }
