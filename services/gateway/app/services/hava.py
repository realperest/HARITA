"""Rota boyunca hava durumu: Open-Meteo saatlik tahmini, her ornek noktaya tahmini varis saatinde.

Tahminler ~11 km'lik izgara hucresine (0,1 derece) gore Redis'te 5 dakika tutulur (anahtar hava:<enlem>,<boylam>:saatlik).
Open-Meteo ucretsiz sunucusu ticari olmayan kullanim icindir; ticari kullanimda HAVA_ANAHTARI ile ucretli adres kullanilir.
"""

import json
import logging
import math
from datetime import datetime, timedelta, timezone

import httpx

from app import cache
from app.config import ayarlar
from app.services.http import AltServisHatasi, istemci

log = logging.getLogger(__name__)

ONBELLEK_SN = 300
MAKS_ORNEK = 25
ALANLAR = "temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m,visibility"

# WMO hava kodlari (Open-Meteo)
DURUM_METNI = {
    0: "Açık", 1: "Az bulutlu", 2: "Parçalı bulutlu", 3: "Kapalı", 45: "Sis", 48: "Kırağılı sis",
    51: "Hafif çisenti", 53: "Çisenti", 55: "Yoğun çisenti", 56: "Donan çisenti", 57: "Yoğun donan çisenti",
    61: "Hafif yağmur", 63: "Yağmur", 65: "Kuvvetli yağmur", 66: "Donan yağmur", 67: "Kuvvetli donan yağmur",
    71: "Hafif kar", 73: "Kar", 75: "Yoğun kar", 77: "Kar taneleri", 80: "Hafif sağanak", 81: "Sağanak", 82: "Şiddetli sağanak",
    85: "Kar sağanağı", 86: "Yoğun kar sağanağı", 95: "Gök gürültülü fırtına", 96: "Dolulu fırtına", 99: "Şiddetli dolulu fırtına",
}


def _mesafe(a: list[float], b: list[float]) -> float:
    """Iki [boylam, enlem] arasi metre (yaklasik, haversine)."""
    r = 6371008.8
    f1, f2 = math.radians(a[1]), math.radians(b[1])
    df, dl = f2 - f1, math.radians(b[0] - a[0])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def ornekle(cizgi: list[list[float]], aralik_m: float | None = None) -> list[tuple[list[float], float]]:
    """Cizgi boyunca esit aralikli ornekler: [(nokta, rota_m)]; baslangic ve bitis dahil, en fazla MAKS_ORNEK."""
    kum = [0.0]
    for i in range(1, len(cizgi)):
        kum.append(kum[-1] + _mesafe(cizgi[i - 1], cizgi[i]))
    toplam = kum[-1]
    aralik = max(aralik_m or 0, 10_000, toplam / (MAKS_ORNEK - 1))
    hedefler = [i * aralik for i in range(int(toplam // aralik) + 1)]
    if not hedefler or toplam - hedefler[-1] > aralik * 0.3:
        hedefler.append(toplam)
    else:
        hedefler[-1] = toplam
    sonuc, j = [], 0
    for h in hedefler:
        while j < len(kum) - 2 and kum[j + 1] < h:
            j += 1
        parca = kum[j + 1] - kum[j] if len(kum) > 1 else 0
        t = (h - kum[j]) / parca if parca else 0
        a, b = cizgi[j], cizgi[min(j + 1, len(cizgi) - 1)]
        sonuc.append(([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], h))
    return sonuc


def _hucre(nokta: list[float]) -> tuple[float, float]:
    """0,1 derecelik izgara hucresi (enlem, boylam)."""
    return round(nokta[1], 1), round(nokta[0], 1)


async def _tahminler(hucreler: list[tuple[float, float]]) -> dict[tuple[float, float], dict]:
    """Hucrelerin saatlik tahmini: once Redis, eksikler tek Open-Meteo isteginde."""
    r = cache.istemci()
    anahtarlar = [f"hava:{a:.1f},{b:.1f}:saatlik" for a, b in hucreler]
    onbellek = await r.mget(anahtarlar) if anahtarlar else []
    sonuc = {h: json.loads(v) for h, v in zip(hucreler, onbellek) if v}
    eksik = [h for h in hucreler if h not in sonuc]
    if eksik:
        parametre = {"latitude": ",".join(f"{a:.1f}" for a, _ in eksik), "longitude": ",".join(f"{b:.1f}" for _, b in eksik),
                     "hourly": ALANLAR, "timezone": "UTC", "forecast_days": 4, "wind_speed_unit": "kmh"}
        if ayarlar.HAVA_ANAHTARI:
            parametre["apikey"] = ayarlar.HAVA_ANAHTARI
        try:
            yanit = await istemci().get(f"{ayarlar.HAVA_ADRESI}/v1/forecast", params=parametre, timeout=10.0)
        except httpx.HTTPError as hata:
            log.error("Hava servisine ulasilamadi: %s", type(hata).__name__)
            raise AltServisHatasi("hava") from hata
        if yanit.status_code != 200:
            log.error("Hava servisi %s: %s", yanit.status_code, yanit.text[:200])
            raise AltServisHatasi("hava")
        veri = yanit.json()
        liste = veri if isinstance(veri, list) else [veri]
        if len(liste) != len(eksik):
            log.error("Hava servisi %s konum yerine %s sonuc dondu", len(eksik), len(liste))
            raise AltServisHatasi("hava")
        boru = r.pipeline()
        for h, v in zip(eksik, liste):
            saatlik = v.get("hourly") or {}
            sonuc[h] = saatlik
            boru.set(f"hava:{h[0]:.1f},{h[1]:.1f}:saatlik", json.dumps(saatlik), ex=ONBELLEK_SN)
        await boru.execute()
    return sonuc


def _uyarilar(s: dict) -> list[str]:
    """Surus icin onemli kosullar."""
    u = []
    kod = s.get("kod")
    if kod in (95, 96, 99):
        u.append("firtina")
    if kod in (71, 73, 75, 77, 85, 86):
        u.append("kar")
    if kod in (56, 57, 66, 67) or (s.get("sicaklik_c") is not None and s["sicaklik_c"] <= 1 and (s.get("yagis_mm") or 0) > 0):
        u.append("buzlanma")
    if (s.get("yagis_mm") or 0) >= 4:
        u.append("kuvvetli_yagis")
    if (s.get("ruzgar_hamle_kmh") or 0) >= 50:
        u.append("kuvvetli_ruzgar")
    if s.get("gorus_m") is not None and s["gorus_m"] < 1000:
        u.append("sis")
    return u


async def rota_boyunca(cizgi: list[list[float]], sure_sn: float | None, kalkis: datetime | None, aralik_m: float | None) -> dict:
    """Ornek noktalarda varis saatindeki hava. sure_sn verilmezse 60 km/sa ortalama hiz varsayilir."""
    ornekler = ornekle(cizgi, aralik_m)
    toplam = ornekler[-1][1] or 1
    sure = sure_sn if sure_sn else toplam / (60 / 3.6)
    bas = (kalkis or datetime.now(timezone.utc)).astimezone(timezone.utc)
    hucreler = list(dict.fromkeys(_hucre(n) for n, _ in ornekler))
    tahmin = await _tahminler(hucreler)
    noktalar, tum = [], set()
    for n, m in ornekler:
        varis = bas + timedelta(seconds=sure * m / toplam)
        saatlik = tahmin.get(_hucre(n)) or {}
        zamanlar = saatlik.get("time") or []
        hedef = varis.replace(minute=0, second=0, microsecond=0) + (timedelta(hours=1) if varis.minute >= 30 else timedelta())
        try:
            i = zamanlar.index(hedef.strftime("%Y-%m-%dT%H:%M"))
        except ValueError:
            i = None

        def al(ad: str, i: int | None = i, saatlik: dict = saatlik):
            dizi = saatlik.get(ad) or []
            return dizi[i] if i is not None and i < len(dizi) else None

        kod = al("weather_code")
        s = {"lat": round(n[1], 5), "lon": round(n[0], 5), "rota_m": round(m), "varis": varis.isoformat(timespec="minutes"),
             "sicaklik_c": al("temperature_2m"), "yagis_mm": al("precipitation"), "yagis_olasiligi": al("precipitation_probability"),
             "kod": kod, "durum": DURUM_METNI.get(kod) if kod is not None else None, "ruzgar_kmh": al("wind_speed_10m"),
             "ruzgar_hamle_kmh": al("wind_gusts_10m"), "gorus_m": al("visibility"), "tahmin_var": i is not None}
        s["uyarilar"] = _uyarilar(s)
        tum.update(s["uyarilar"])
        noktalar.append(s)
    return {"noktalar": noktalar, "uyarilar": sorted(tum), "kaynak": "Open-Meteo.com (CC BY 4.0)"}
