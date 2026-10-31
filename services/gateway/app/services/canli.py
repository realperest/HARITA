"""Canli konum yayini ve bolge (geofence) olaylari.

Kanal proje basinadir: Redis yayin kanali canli:<proje>:<kanal>; son konumlar canli:<proje>:<kanal>:konumlar (hash, 1 saat),
cihazin icinde oldugu bolgeler canli:<proje>:<kanal>:bolge_durum (hash). Birden cok gateway kopyasi Redis uzerinden ayni olaylari gorur.
Bolge kontrolu bellekte yapilir (daire: haversine, poligon: isin kesme); bolgeler veritabanindan okunur ve 30 sn onbellekte tutulur.
"""

import json
import math
import time

from app import cache
from app.db import havuz

KONUM_SURESI_SN = 3600
BOLGE_ONBELLEK_SN = 30
_bolge_onbellek: dict[tuple[int, str], tuple[float, list[dict]]] = {}


def kanal_adi(proje_id: int, kanal: str) -> str:
    """Redis yayin kanali."""
    return f"canli:{proje_id}:{kanal}"


def _mesafe_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Iki nokta arasi metre (haversine)."""
    r = 6371008.8
    f1, f2 = math.radians(a_lat), math.radians(b_lat)
    h = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def icinde_mi(tanim: dict, lat: float, lon: float) -> bool:
    """Nokta bolgenin icinde mi: daire (merkez + yaricap_m) ya da poligon ([[lat, lon], ...], isin kesme)."""
    if "merkez" in tanim:
        return _mesafe_m(lat, lon, tanim["merkez"]["lat"], tanim["merkez"]["lon"]) <= tanim["yaricap_m"]
    nokta = tanim["poligon"]
    icerde = False
    j = len(nokta) - 1
    for i in range(len(nokta)):
        (yi, xi), (yj, xj) = nokta[i], nokta[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            icerde = not icerde
        j = i
    return icerde


async def bolgeler(proje_id: int, kanal: str, tazele: bool = False) -> list[dict]:
    """Kanalin bolgeleri (kisa sureli bellek onbellegi)."""
    anahtar = (proje_id, kanal)
    kayit = _bolge_onbellek.get(anahtar)
    if kayit and not tazele and time.monotonic() - kayit[0] < BOLGE_ONBELLEK_SN:
        return kayit[1]
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch("SELECT bolge_id, ad, tanim FROM canli_bolge WHERE proje_id = $1 AND kanal = $2 ORDER BY bolge_id",
                                        proje_id, kanal)
    liste = [{"id": s["bolge_id"], "ad": s["ad"], **json.loads(s["tanim"])} for s in satirlar]
    _bolge_onbellek[anahtar] = (time.monotonic(), liste)
    return liste


async def bolgeleri_yaz(proje_id: int, kanal: str, liste: list[dict]) -> int:
    """Kanalin bolgelerini verilen listeyle degistirir; eski bolge durumlari sifirlanir."""
    async with havuz().acquire() as baglanti, baglanti.transaction():
        await baglanti.execute("DELETE FROM canli_bolge WHERE proje_id = $1 AND kanal = $2", proje_id, kanal)
        await baglanti.executemany(
            "INSERT INTO canli_bolge (proje_id, kanal, bolge_id, ad, tanim) VALUES ($1, $2, $3, $4, $5::jsonb)",
            [(proje_id, kanal, b["id"], b.get("ad"), json.dumps({k: v for k, v in b.items() if k in ("merkez", "yaricap_m", "poligon")}))
             for b in liste])
    await cache.istemci().delete(f"{kanal_adi(proje_id, kanal)}:bolge_durum")
    _bolge_onbellek.pop((proje_id, kanal), None)
    return len(liste)


async def konum_isle(proje_id: int, kanal: str, konum: dict) -> list[dict]:
    """Konumu kaydeder, bolge giris / cikislarini bulur ve hepsini kanala yayinlar. Donus: yayinlanan mesajlar."""
    r = cache.istemci()
    ad = kanal_adi(proje_id, kanal)
    cihaz = str(konum["id"])
    mesaj = {"tip": "konum", **konum, "zaman": konum.get("zaman") or time.time()}
    mesajlar = [mesaj]
    liste = await bolgeler(proje_id, kanal)
    if liste:
        simdi = {b["id"] for b in liste if icinde_mi(b, konum["lat"], konum["lon"])}
        eski_ham = await r.hget(f"{ad}:bolge_durum", cihaz)
        eski = set(eski_ham.split("\x1f")) if eski_ham else set()
        adlar = {b["id"]: b.get("ad") for b in liste}
        for bolge in sorted(simdi - eski):
            mesajlar.append({"tip": "bolge", "olay": "giris", "id": cihaz, "bolge": bolge, "bolge_ad": adlar.get(bolge), "zaman": mesaj["zaman"]})
        for bolge in sorted(eski - simdi):
            mesajlar.append({"tip": "bolge", "olay": "cikis", "id": cihaz, "bolge": bolge, "bolge_ad": adlar.get(bolge), "zaman": mesaj["zaman"]})
        if simdi != eski:
            if simdi:
                await r.hset(f"{ad}:bolge_durum", cihaz, "\x1f".join(sorted(simdi)))
            else:
                await r.hdel(f"{ad}:bolge_durum", cihaz)
        mesaj["bolgeler"] = sorted(simdi)
    boru = r.pipeline()
    boru.hset(f"{ad}:konumlar", cihaz, json.dumps(mesaj, ensure_ascii=False))
    boru.expire(f"{ad}:konumlar", KONUM_SURESI_SN)
    boru.expire(f"{ad}:bolge_durum", KONUM_SURESI_SN)
    for m in mesajlar:
        boru.publish(ad, json.dumps(m, ensure_ascii=False))
    await boru.execute()
    return mesajlar


async def son_konumlar(proje_id: int, kanal: str) -> list[dict]:
    """Kanaldaki cihazlarin son konumlari (son 1 saat)."""
    degerler = await cache.istemci().hvals(f"{kanal_adi(proje_id, kanal)}:konumlar")
    simdi = time.time()
    return sorted((m for m in map(json.loads, degerler) if simdi - m["zaman"] < KONUM_SURESI_SN), key=lambda m: str(m["id"]))
