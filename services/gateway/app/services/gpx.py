"""GPX 1.1 olusturma ve okuma (dis kutuphane gerektirmez).

Okumada DOCTYPE / ENTITY iceren dosyalar reddedilir (XML varlik genisletme saldirilarina karsi).
"""

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
