"""Yerlesim (il, ilce, mahalle / koy, sehir-kasaba-koy-mezra-semt merkezleri) sorgulari."""

import json

import asyncpg

from app.db import havuz
from app.metin import ad_katla

_SECIM = """
SELECT y.id, y.ad, t.kod AS tur, ST_Y(y.merkez::geometry) AS lat, ST_X(y.merkez::geometry) AS lon, y.nufus,
       y.ust_id, u.ad AS ust_ad, ut.kod AS ust_tur, y.kaynak_anahtari
  FROM yerlesim y
  JOIN tnm_yerlesim_turu t ON t.id = y.tur_id
  LEFT JOIN yerlesim u ON u.id = y.ust_id
  LEFT JOIN tnm_yerlesim_turu ut ON ut.id = u.tur_id
 WHERE y.aktif_mi
"""


def _satir(s: asyncpg.Record) -> dict:
    """Veritabani satirini API sozlugune cevirir."""
    return {
        "id": s["id"], "ad": s["ad"], "tur": s["tur"], "merkez": {"lat": s["lat"], "lon": s["lon"]}, "nufus": s["nufus"],
        "ust": {"id": s["ust_id"], "ad": s["ust_ad"], "tur": s["ust_tur"]} if s["ust_id"] else None,
        "kaynak": s["kaynak_anahtari"],
    }


async def toplu(idler: list[int]) -> list[dict]:
    """Verilen yerlesimler tek sorguda (toplu ad / zincir dogrulama icin)."""
    if not idler:
        return []
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(_SECIM + " AND y.id = ANY($1::bigint[])", idler)
    return [_satir(s) for s in satirlar]


async def kaynaktan(anahtarlar: list[str]) -> list[dict]:
    """OSM kaynak anahtariyla (osm:relation:.. / osm:node:..) yerlesimler."""
    if not anahtarlar:
        return []
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(_SECIM + " AND y.kaynak_anahtari = ANY($1::text[])", anahtarlar)
    return [_satir(s) for s in satirlar]


def _like_kacis(metin: str) -> str:
    """LIKE desenindeki ozel karakterleri kacirir."""
    return metin.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def ara(q: str, tur: str | None, ust_id: int | None, limit: int) -> list[dict]:
    """Ada gore arama: once tam eslesme, sonra on ek, sonra benzerlik; tur sirasi ve nufus ile siralanir."""
    katlanmis = ad_katla(q)
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            _SECIM + """
               AND (y.ad_arama LIKE $2 || '%' OR y.ad_arama % $1)
               AND ($3::text IS NULL OR t.kod = $3)
               AND ($4::bigint IS NULL OR y.ust_id = $4)
             ORDER BY (y.ad_arama = $1) DESC, (y.ad_arama LIKE $2 || '%') DESC, similarity(y.ad_arama, $1) DESC,
                      t.sira, y.nufus DESC NULLS LAST
             LIMIT $5""",
            katlanmis, _like_kacis(katlanmis), tur, ust_id, limit,
        )
    return [_satir(s) for s in satirlar]


async def getir(yerlesim_id: int, sinir: bool) -> dict | None:
    """Tek yerlesim; ust zinciri (il > ilce > mahalle) ve istenirse GeoJSON siniri ile."""
    async with havuz().acquire() as baglanti:
        satir = await baglanti.fetchrow(_SECIM + " AND y.id = $1", yerlesim_id)
        if satir is None:
            return None
        zincir = await baglanti.fetch(
            """WITH RECURSIVE z AS (
                   SELECT id, ust_id, ad, tur_id, 1 AS derinlik FROM yerlesim WHERE id = (SELECT ust_id FROM yerlesim WHERE id = $1)
                   UNION ALL
                   SELECT p.id, p.ust_id, p.ad, p.tur_id, z.derinlik + 1 FROM yerlesim p JOIN z ON p.id = z.ust_id)
               SELECT z.id, z.ad, t.kod AS tur FROM z JOIN tnm_yerlesim_turu t ON t.id = z.tur_id ORDER BY z.derinlik DESC""",
            yerlesim_id,
        )
        sinir_json = None
        if sinir:
            ham = await baglanti.fetchval("SELECT ST_AsGeoJSON(sinir::geometry, 5) FROM yerlesim WHERE id = $1", yerlesim_id)
            sinir_json = json.loads(ham) if ham else None
    veri = _satir(satir)
    veri["zincir"] = [{"id": z["id"], "ad": z["ad"], "tur": z["tur"]} for z in zincir]
    if sinir:
        veri["sinir"] = sinir_json
    return veri


async def alt_ogeler(yerlesim_id: int, tur: str | None, limit: int, atla: int) -> list[dict]:
    """Bir yerlesimin dogrudan altindakiler (or. ilin ilceleri, ilcenin mahalle / koyleri)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            _SECIM + " AND y.ust_id = $1 AND ($2::text IS NULL OR t.kod = $2) ORDER BY t.sira, y.ad_arama LIMIT $3 OFFSET $4",
            yerlesim_id, tur, limit, atla,
        )
    return [_satir(s) for s in satirlar]


async def noktada(lat: float, lon: float) -> dict:
    """Noktayi iceren il / ilce / mahalle-koy sinirlari ve en yakin merkez (sehir, kasaba, koy, mezra, semt)."""
    async with havuz().acquire() as baglanti:
        icerenler = await baglanti.fetch(
            _SECIM + """
               AND t.id IN (1, 2, 3)
               AND ST_Covers(y.sinir, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography)
             ORDER BY t.sira""",
            lat, lon,
        )
        yakin = await baglanti.fetchrow(
            _SECIM.replace("SELECT y.id,", "SELECT ST_Distance(y.merkez, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS mesafe, y.id,")
            + " AND t.id >= 4 ORDER BY y.merkez <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography LIMIT 1",
            lat, lon,
        )
    yanit = {"icinde": [_satir(s) for s in icerenler], "en_yakin_merkez": None}
    if yakin is not None:
        yanit["en_yakin_merkez"] = {**_satir(yakin), "mesafe_m": round(yakin["mesafe"])}
    return yanit


async def yakin(lat: float, lon: float, yaricap_m: int, tur: str | None, limit: int) -> list[dict]:
    """Noktaya yaricap icindeki merkezler, yakindan uzaga."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            _SECIM.replace("SELECT y.id,", "SELECT ST_Distance(y.merkez, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS mesafe, y.id,")
            + """ AND ST_DWithin(y.merkez, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3)
                  AND ($4::text IS NULL OR t.kod = $4)
                ORDER BY y.merkez <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography LIMIT $5""",
            lat, lon, yaricap_m, tur, limit,
        )
    return [{**_satir(s), "mesafe_m": round(s["mesafe"])} for s in satirlar]
