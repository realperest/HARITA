"""Yol uyarisi (hiz kamerasi, hiz kesici) sorgulari."""

import asyncpg

from app.db import havuz

_ALANLAR = """u.id, t.kod AS tur, ST_Y(u.konum::geometry) AS lat, ST_X(u.konum::geometry) AS lon, u.hiz_siniri, u.yon, u.kaynak_anahtari"""


def _satir(s: asyncpg.Record) -> dict:
    """Veritabani satirini API sozlugune cevirir."""
    sonuc = {"id": s["id"], "tur": s["tur"], "lat": s["lat"], "lon": s["lon"], "hiz_siniri_kmh": s["hiz_siniri"], "yon": s["yon"],
             "kaynak": s["kaynak_anahtari"]}
    if "rota_m" in s.keys():
        sonuc["rota_m"] = round(s["rota_m"])
        sonuc["uzaklik_m"] = round(s["uzaklik_m"], 1)
    return sonuc


async def rota_boyunca(noktalar: list[list[float]], tampon_m: float, turler: list[str] | None) -> list[dict]:
    """Rota cizgisine (noktalar: [boylam, enlem]) tampon_m icindeki uyarilar, rota baslangicindan uzakliga (rota_m) gore sirali."""
    wkt = "LINESTRING(" + ",".join(f"{x} {y}" for x, y in noktalar) + ")"
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""WITH r AS (SELECT ST_GeomFromText($1, 4326) AS g)
                SELECT {_ALANLAR}, ST_LineLocatePoint(r.g, u.konum::geometry) * ST_Length(r.g::geography) AS rota_m,
                       ST_Distance(u.konum, r.g::geography) AS uzaklik_m
                  FROM yol_uyari u JOIN tnm_yol_uyari_turu t ON t.id = u.tur_id, r
                 WHERE u.aktif_mi AND ST_DWithin(u.konum, r.g::geography, $2)
                   AND ($3::text[] IS NULL OR t.kod = ANY($3::text[]))
                 ORDER BY rota_m""",
            wkt, tampon_m, turler)
    return [_satir(s) for s in satirlar]


async def kutuda(bati: float, guney: float, dogu: float, kuzey: float, turler: list[str] | None, sinir: int) -> list[dict]:
    """Harita kutusundaki uyarilar (en fazla sinir adet)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT {_ALANLAR} FROM yol_uyari u JOIN tnm_yol_uyari_turu t ON t.id = u.tur_id
                 WHERE u.aktif_mi AND u.konum && ST_MakeEnvelope($1, $2, $3, $4, 4326)::geography
                   AND ($5::text[] IS NULL OR t.kod = ANY($5::text[]))
                 LIMIT $6""",
            bati, guney, dogu, kuzey, turler, sinir)
    return [_satir(s) for s in satirlar]
