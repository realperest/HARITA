"""Trafik profili: projelerin anonim GPS izlerinden yol parcasi hizlarini ogrenir ve rota surelerini buna gore duzeltir.

Ogrenme: iz Valhalla trace_attributes ile yola eslenir (use_timestamps); her tam gecilen kenarin suresi uc dugumlerinin gecen
sure farkidir, hiz = uzunluk / sure. Ilk ve son kenar (kismi gecis) ile 40 m'den kisa kenarlar atilir.
Saklama: PostgreSQL'de OSM yol kimligi + haftanin saati basina ortalama (kalici), Redis'te son 20 dakikanin hareketli ortalamasi
(canli; anahtar trafik:<yol>:canli). Cihaz, kisi ya da iz saklanmaz.
Kullanim: rota cizgisi yola eslenir; her kenar icin canli hiz (yakin zaman ise) > haftanin o saatinin ortalamasi (en az
EN_AZ_ORNEK ornek) > Valhalla'nin varsayilan hizi kullanilir.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app import cache
from app.config import ayarlar
from app.db import havuz
from app.services.http import AltServisHatasi, AltServisYok, istemci

log = logging.getLogger(__name__)

TR = ZoneInfo("Europe/Istanbul")
EN_KISA_KENAR_KM = 0.04
EN_AZ_ORNEK = 3
ORNEK_TAVANI = 500           # ortalama yeni olcumlere uyum saglasin diye agirlik bu sayida sinirlanir
CANLI_SN = 1200
CANLI_AGIRLIK = 0.3
ALANLAR = ["edge.way_id", "edge.length", "edge.speed", "node.elapsed_time"]


def haftanin_saati(zaman: datetime) -> int:
    """Turkiye saatine gore haftanin saati: Pazartesi 00:00-01:00 = 0, Pazar 23:00 = 167."""
    yerel = zaman.astimezone(TR)
    return yerel.weekday() * 24 + yerel.hour


async def _esle(shape: list[dict], maliyet: str, zamanli: bool) -> list[dict]:
    """Noktalari yola esler; kenar listesi (way_id, length km, speed, end_node.elapsed_time)."""
    govde = {"shape": shape, "costing": maliyet, "shape_match": "map_snap",
             "trace_options": {"search_radius": 50, "gps_accuracy": 15}, "filters": {"attributes": ALANLAR, "action": "include"}}
    if zamanli:
        govde["use_timestamps"] = True
    try:
        yanit = await istemci().post(f"{ayarlar.ROTA_ADRESI}/trace_attributes", json=govde, timeout=30.0)
    except httpx.HTTPError as hata:
        log.error("Valhalla trace_attributes ulasilamadi: %s", type(hata).__name__)
        raise AltServisHatasi("rota servisi ulasilamadi") from hata
    if yanit.status_code == 400:
        log.info("Iz yola eslenemedi: %s", yanit.text[:200])
        raise AltServisYok("iz eslenemedi")
    if yanit.status_code != 200:
        log.error("Valhalla trace_attributes %s: %s", yanit.status_code, yanit.text[:200])
        raise AltServisHatasi("rota servisi hata verdi")
    return yanit.json().get("edges") or []


def kenar_hizlari(kenarlar: list[dict]) -> list[tuple[int, float]]:
    """Tam gecilen kenarlarin olculen hizi: [(way_id, km/sa)]; ilk / son kenar ve kisa kenarlar atilir."""
    sonuc = []
    onceki = 0.0
    for i, k in enumerate(kenarlar):
        bitis = (k.get("end_node") or {}).get("elapsed_time")
        if bitis is None:
            onceki = None
            continue
        if 0 < i < len(kenarlar) - 1 and onceki is not None and k.get("way_id") and (k.get("length") or 0) >= EN_KISA_KENAR_KM:
            sure = bitis - onceki
            if sure > 0:
                hiz = k["length"] / (sure / 3600)
                if 2 <= hiz <= 180:
                    sonuc.append((int(k["way_id"]), hiz))
        onceki = bitis
    return sonuc


async def iz_ogren(noktalar: list[dict], maliyet: str) -> dict:
    """GPS izinden hiz ornekleri cikarir ve kaydeder. noktalar: [{lat, lon, zaman (Unix sn)}], zamana gore sirali."""
    shape = [{"lat": n["lat"], "lon": n["lon"], "time": int(n["zaman"])} for n in noktalar]
    kenarlar = await _esle(shape, maliyet, zamanli=True)
    hizlar = kenar_hizlari(kenarlar)
    if not hizlar:
        return {"eslenen_kenar": len(kenarlar), "kaydedilen": 0}
    # Ayni yolda birden cok kenar: yol basina ortalama
    yol: dict[int, list[float]] = {}
    for w, h in hizlar:
        yol.setdefault(w, []).append(h)
    ortalama = {w: sum(v) / len(v) for w, v in yol.items()}
    orta_zaman = datetime.fromtimestamp((noktalar[0]["zaman"] + noktalar[-1]["zaman"]) / 2, tz=timezone.utc)
    saat = haftanin_saati(orta_zaman)
    async with havuz().acquire() as baglanti:
        await baglanti.executemany(
            """INSERT INTO trafik_hiz (osm_yol_id, saat, ornek, ortalama) VALUES ($1, $2, 1, $3)
               ON CONFLICT (osm_yol_id, saat) DO UPDATE SET
                   ortalama = (trafik_hiz.ortalama * LEAST(trafik_hiz.ornek, $4) + EXCLUDED.ortalama) / (LEAST(trafik_hiz.ornek, $4) + 1),
                   ornek = trafik_hiz.ornek + 1, guncelleme = now()""",
            [(w, saat, h, ORNEK_TAVANI) for w, h in ortalama.items()])
    if datetime.now(timezone.utc) - datetime.fromtimestamp(noktalar[-1]["zaman"], tz=timezone.utc) < timedelta(seconds=CANLI_SN):
        r = cache.istemci()
        eski = await r.mget([f"trafik:{w}:canli" for w in ortalama])
        boru = r.pipeline()
        for (w, h), e in zip(ortalama.items(), eski):
            yeni = h if e is None else float(e) * (1 - CANLI_AGIRLIK) + h * CANLI_AGIRLIK
            boru.set(f"trafik:{w}:canli", f"{yeni:.2f}", ex=CANLI_SN)
        await boru.execute()
    return {"eslenen_kenar": len(kenarlar), "kaydedilen": len(ortalama), "haftanin_saati": saat}


async def sure_tahmini(cizgi: list[list[float]], maliyet: str, zaman: datetime | None) -> dict:
    """Rota cizgisi ([boylam, enlem]) icin ogrenilmis hizlarla sure. Donus: valhalla_sure_sn, tahmini_sure_sn, kapsama (0-1)."""
    zaman = (zaman or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # Cok uzun cizgide esleme yukunu sinirlamak icin seyreltilir
    adim = max(1, len(cizgi) // 4000)
    shape = [{"lat": y, "lon": x} for x, y in cizgi[::adim]]
    if shape[-1] != {"lat": cizgi[-1][1], "lon": cizgi[-1][0]}:
        shape.append({"lat": cizgi[-1][1], "lon": cizgi[-1][0]})
    kenarlar = [k for k in await _esle(shape, maliyet, zamanli=False) if k.get("length")]
    yollar = sorted({int(k["way_id"]) for k in kenarlar if k.get("way_id")})
    saat = haftanin_saati(zaman)
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            "SELECT osm_yol_id, ortalama FROM trafik_hiz WHERE osm_yol_id = ANY($1::bigint[]) AND saat = $2 AND ornek >= $3",
            yollar, saat, EN_AZ_ORNEK)
    gecmis = {s["osm_yol_id"]: s["ortalama"] for s in satirlar}
    canli: dict[int, float] = {}
    if yollar and abs((zaman - datetime.now(timezone.utc)).total_seconds()) < 1800:
        degerler = await cache.istemci().mget([f"trafik:{w}:canli" for w in yollar])
        canli = {w: float(d) for w, d in zip(yollar, degerler) if d is not None}
    varsayilan = tahmini = kapsanan = toplam_km = 0.0
    for k in kenarlar:
        km = k["length"]
        v_hiz = k.get("speed") or 30
        w = int(k["way_id"]) if k.get("way_id") else None
        hiz = canli.get(w) or gecmis.get(w)
        varsayilan += km / v_hiz * 3600
        tahmini += km / (hiz or v_hiz) * 3600
        toplam_km += km
        if hiz:
            kapsanan += km
    return {"valhalla_sure_sn": round(varsayilan), "tahmini_sure_sn": round(tahmini), "mesafe_m": round(toplam_km * 1000),
            "kapsama": round(kapsanan / toplam_km, 3) if toplam_km else 0.0, "canli_yol": len(canli), "gecmis_yol": len(gecmis),
            "haftanin_saati": saat}
