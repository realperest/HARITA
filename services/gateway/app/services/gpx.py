"""GPX 1.1 olusturma ve okuma (dis kutuphane gerektirmez).

Okumada DOCTYPE / ENTITY iceren dosyalar reddedilir (XML varlik genisletme saldirilarina karsi).
"""

import bisect
import math
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

MAKS_NOKTA = 200_000


class GpxHatasi(ValueError):
    """GPX dosyasi okunamadi."""


def olustur(ad: str, cizgi: list[list[float]], duraklar: list[dict]) -> str:
    """Rota cizgisi ([boylam, enlem]) iz (trk), duraklar yol noktasi (wpt) ve rota noktasi (rte) olarak GPX metni."""
    ad_x = escape(ad or "Rota")
    satirlar = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<gpx version="1.1" creator="HARITA" xmlns="http://www.topografix.com/GPX/1/1">',
                f"  <metadata><name>{ad_x}</name></metadata>"]
    for i, d in enumerate(duraklar, 1):
        satirlar.append(f'  <wpt lat="{d["lat"]:.6f}" lon="{d["lon"]:.6f}"><name>{escape(d.get("ad") or f"Durak {i}")}</name></wpt>')
    if duraklar:
        satirlar.append(f"  <rte><name>{ad_x}</name>")
        for i, d in enumerate(duraklar, 1):
            satirlar.append(f'    <rtept lat="{d["lat"]:.6f}" lon="{d["lon"]:.6f}"><name>{escape(d.get("ad") or f"Durak {i}")}</name></rtept>')
        satirlar.append("  </rte>")
    if cizgi:
        satirlar.append(f"  <trk><name>{ad_x}</name><trkseg>")
        satirlar.extend(f'    <trkpt lat="{y:.6f}" lon="{x:.6f}"/>' for x, y in cizgi)
        satirlar.append("  </trkseg></trk>")
    satirlar.append("</gpx>")
    return "\n".join(satirlar) + "\n"


def _yerel(etiket: str) -> str:
    """Ad alani onekini atar: {http://...}trkpt -> trkpt."""
    return etiket.rsplit("}", 1)[-1]


def _nokta(e: ET.Element) -> dict:
    """lat / lon ozniteliklerini ve name / ele cocuklarini okur."""
    try:
        lat, lon = float(e.attrib["lat"]), float(e.attrib["lon"])
    except (KeyError, ValueError) as hata:
        raise GpxHatasi("Noktada lat / lon eksik.") from hata
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise GpxHatasi("Koordinat gecersiz.")
    sonuc: dict = {"lat": lat, "lon": lon}
    for c in e:
        if _yerel(c.tag) == "name" and c.text:
            sonuc["ad"] = c.text.strip()[:200]
        elif _yerel(c.tag) == "ele" and c.text:
            try:
                sonuc["yukseklik_m"] = float(c.text)
            except ValueError:
                sonuc["yukseklik_m"] = None
    return sonuc


def oku(metin: str) -> dict:
    """GPX metnini okur: {ad, yol_noktalari (wpt), rotalar: [[nokta]], izler: [[nokta]]}. Hata olursa GpxHatasi."""
    bas = metin[:4096].upper()
    if "<!DOCTYPE" in bas or "<!ENTITY" in metin.upper():
        raise GpxHatasi("DOCTYPE / ENTITY iceren GPX kabul edilmez.")
    try:
        kok = ET.fromstring(metin)
    except ET.ParseError as hata:
        raise GpxHatasi("GPX dosyasi okunamadi.") from hata
    if _yerel(kok.tag) != "gpx":
        raise GpxHatasi("Dosya GPX degil.")
    ad, wpt, rotalar, izler, sayac = None, [], [], [], 0
    for e in kok:
        etiket = _yerel(e.tag)
        if etiket == "metadata":
            ad = next((c.text.strip() for c in e if _yerel(c.tag) == "name" and c.text), ad)
        elif etiket == "wpt":
            wpt.append(_nokta(e))
        elif etiket == "rte":
            rotalar.append([_nokta(c) for c in e if _yerel(c.tag) == "rtept"])
            ad = ad or next((c.text.strip() for c in e if _yerel(c.tag) == "name" and c.text), None)
        elif etiket == "trk":
            ad = ad or next((c.text.strip() for c in e if _yerel(c.tag) == "name" and c.text), None)
            for parca in (c for c in e if _yerel(c.tag) == "trkseg"):
                izler.append([_nokta(n) for n in parca if _yerel(n.tag) == "trkpt"])
        sayac = len(wpt) + sum(map(len, rotalar)) + sum(map(len, izler))
        if sayac > MAKS_NOKTA:
            raise GpxHatasi(f"GPX en fazla {MAKS_NOKTA} nokta icerebilir.")
    if not sayac:
        raise GpxHatasi("GPX dosyasinda nokta yok.")
    return {"ad": ad[:200] if ad else None, "yol_noktalari": wpt, "rotalar": [r for r in rotalar if r], "izler": [i for i in izler if i]}


def _metre(a: dict, b: dict) -> float:
    """Iki nokta arasi metre (haversine)."""
    f1, f2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def iz_takip(duraklar: list[dict], iz: list[dict], maks_ara: int, aralik_m: float = 2000) -> list[dict]:
    """Duraklara izden ara (gecis) noktalari ekler: rota hesaplanirken bu noktalardan gecilir, boylece navigasyon izin yollarini izler.
    Her ara nokta izde kendisinden sonra gelen durağin "ara" listesine konur. Ilk durak baslangic sayilir (ara almaz).
    Ara nokta sayisi en fazla maks_ara; aralik izin uzunluguna gore buyur."""
    if len(iz) < 3 or len(duraklar) < 2 or maks_ara <= 0:
        return duraklar
    # Uzun izde hesap yukunu sinirlamak icin seyreltilir (en fazla ~5.000 nokta)
    adim_n = max(1, len(iz) // 5000)
    iz = iz[::adim_n] + ([iz[-1]] if (len(iz) - 1) % adim_n else [])
    kum = [0.0]
    for i in range(1, len(iz)):
        kum.append(kum[-1] + _metre(iz[i - 1], iz[i]))
    # Duraklarin izdeki sirasi (geri gitmeyen en yakin nokta)
    indeksler, bas = [], 0
    for d in duraklar:
        en = min(range(bas, len(iz)), key=lambda i: _metre(d, iz[i]), default=bas)
        indeksler.append(en)
        bas = en
    toplam = kum[-1]
    adet = min(maks_ara, int(toplam // aralik_m))
    if adet <= 0:
        return duraklar
    adim = toplam / (adet + 1)
    durak_m = [kum[i] for i in indeksler]
    sonuc = [{**d, "ara": []} for d in duraklar]
    for k in range(1, adet + 1):
        hedef = k * adim
        i = min(bisect.bisect_left(kum, hedef), len(iz) - 1)
        # Duraga cok yakin ara nokta gereksizdir
        if any(abs(kum[i] - m) < 200 for m in durak_m):
            continue
        sira = next((j for j, di in enumerate(indeksler) if j > 0 and di >= i), None)
        if sira is not None:
            sonuc[sira]["ara"].append({"lat": iz[i]["lat"], "lon": iz[i]["lon"]})
    return sonuc
