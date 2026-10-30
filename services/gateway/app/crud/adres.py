"""Adres sorgulari: sokak, kapi numarasi, onemli yerler (yer isareti), birlesik arama ve ters arama."""

import json
import re

import asyncpg

from app.crud import yerlesim as yerlesim_crud
from app.db import havuz
from app.metin import ad_katla

KAPI_DESENI = re.compile(r"^(?P<sokak>.+?)\s+(?:no\s*[:.]?\s*)?(?P<no>\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?)$", re.IGNORECASE)

# Mahalle > ilce > il adlari (derlenmis sirayla); ust zinciri yerlesim tablosundan
ZINCIR_JOIN = """
  LEFT JOIN yerlesim m ON m.id = x.mahalle_id
  LEFT JOIN yerlesim i ON i.id = m.ust_id
  LEFT JOIN yerlesim l ON l.id = i.ust_id
"""
ZINCIR_ALAN = "m.id AS mahalle_id, m.ad AS mahalle, i.ad AS ilce, l.ad AS il"
UST_FILTRE = "($3::bigint IS NULL OR m.id = $3 OR i.id = $3 OR l.id = $3)"


def _konum(s: asyncpg.Record) -> dict:
    return {"lat": s["lat"], "lon": s["lon"]}


def adres_metni(parcalar: list[str | None], mahalle: str | None, ilce: str | None, il: str | None) -> str:
    """'Sokak No:5, Mahalle, Ilce / Il' bicimli okunabilir adres."""
    yerel = ", ".join(p for p in (*parcalar, mahalle) if p)
    ust = " / ".join(p for p in (ilce, il) if p)
    return ", ".join(p for p in (yerel, ust) if p)


def _kayit(tur: str, s: asyncpg.Record, ad: str, parcalar: list[str | None], skor: float | None = None, ek: dict | None = None) -> dict:
    return {
        "tur": tur, "id": s["id"], "ad": ad, "merkez": _konum(s), "mahalle": s["mahalle"], "ilce": s["ilce"], "il": s["il"],
        "adres": adres_metni(parcalar, s["mahalle"], s["ilce"], s["il"]), "skor": round(float(skor), 3) if skor is not None else None,
        "mesafe_m": round(s["mesafe"]) if "mesafe" in s.keys() and s["mesafe"] is not None else None, "ek": ek or {},
    }


def _like(metin: str) -> str:
    return metin.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _sokak_ara(baglanti, katli: str, ust_id: int | None, lat: float | None, lon: float | None, limit: int) -> list[dict]:
    satirlar = await baglanti.fetch(
        f"""SELECT x.id, x.ad, similarity(x.ad_arama, $1) AS skor, c.kod AS sinif,
                   ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon, {ZINCIR_ALAN},
                   CASE WHEN $4::float8 IS NULL THEN NULL ELSE ST_Distance(x.merkez, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography) END AS mesafe
              FROM sokak x JOIN tnm_yol_sinifi c ON c.id = x.sinif_id {ZINCIR_JOIN}
             WHERE x.aktif_mi AND (x.ad_arama LIKE $2 || '%' OR x.ad_arama % $1) AND {UST_FILTRE}
             ORDER BY (x.ad_arama = $1) DESC, (x.ad_arama LIKE $2 || '%') DESC, skor DESC, mesafe ASC NULLS LAST, c.sira
             LIMIT $6""",
        katli, _like(katli), ust_id, lat, lon, limit)
    return [_kayit("sokak", s, s["ad"], [s["ad"]], s["skor"], {"sinif": s["sinif"]}) for s in satirlar]


async def _yer_ara(baglanti, katli: str, ust_id: int | None, lat: float | None, lon: float | None, limit: int) -> list[dict]:
    satirlar = await baglanti.fetch(
        f"""SELECT x.id, x.ad, similarity(x.ad_arama, $1) AS skor, t.kod AS yer_turu,
                   ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon, {ZINCIR_ALAN},
                   CASE WHEN $4::float8 IS NULL THEN NULL ELSE ST_Distance(x.konum, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography) END AS mesafe
              FROM yer_isareti x JOIN tnm_yer_turu t ON t.id = x.tur_id {ZINCIR_JOIN}
             WHERE x.aktif_mi AND (x.ad_arama LIKE $2 || '%' OR x.ad_arama % $1) AND {UST_FILTRE}
             ORDER BY (x.ad_arama = $1) DESC, skor DESC, mesafe ASC NULLS LAST
             LIMIT $6""",
        katli, _like(katli), ust_id, lat, lon, limit)
    return [_kayit("yer", s, s["ad"], [s["ad"]], s["skor"], {"yer_turu": s["yer_turu"]}) for s in satirlar]


async def _bina_ara(baglanti, katli: str, ust_id: int | None, lat: float | None, lon: float | None, limit: int) -> list[dict]:
    satirlar = await baglanti.fetch(
        f"""SELECT x.id, x.ad, similarity(x.ad_arama, $1) AS skor, t.kod AS bina_turu, k.kod AS kullanim,
                   ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon, {ZINCIR_ALAN},
                   CASE WHEN $4::float8 IS NULL THEN NULL ELSE ST_Distance(x.merkez, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography) END AS mesafe
              FROM bina x JOIN tnm_bina_turu t ON t.id = x.tur_id LEFT JOIN tnm_bina_kullanimi k ON k.id = x.kullanim_id {ZINCIR_JOIN}
             WHERE x.aktif_mi AND (x.ad_arama LIKE $2 || '%' OR x.ad_arama % $1) AND {UST_FILTRE}
             ORDER BY (x.ad_arama = $1) DESC, skor DESC, mesafe ASC NULLS LAST
             LIMIT $6""",
        katli, _like(katli), ust_id, lat, lon, limit)
    return [_kayit("bina", s, s["ad"], [s["ad"]], s["skor"], {"bina_turu": s["bina_turu"], "kullanim": s["kullanim"]}) for s in satirlar]


async def _kapi_ara(baglanti, sokak_katli: str, no: str, ust_id: int | None, limit: int) -> list[dict]:
    satirlar = await baglanti.fetch(
        f"""SELECT x.id, x.kapi_no, s.ad AS sokak, similarity(s.ad_arama, $1) AS skor,
                   ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon, {ZINCIR_ALAN}
              FROM kapi_numarasi x JOIN sokak s ON s.id = x.sokak_id {ZINCIR_JOIN}
             WHERE x.aktif_mi AND x.kapi_no_arama = $2 AND (s.ad_arama LIKE $4 || '%' OR s.ad_arama % $1) AND {UST_FILTRE}
             ORDER BY skor DESC LIMIT $5""",
        sokak_katli, no.lower().replace(" ", ""), ust_id, _like(sokak_katli), limit)
    return [_kayit("kapi", s, f"{s['sokak']} No:{s['kapi_no']}", [f"{s['sokak']} No:{s['kapi_no']}"], s["skor"],
                   {"sokak": s["sokak"], "kapi_no": s["kapi_no"]}) for s in satirlar]


async def ara(q: str, tur: str | None, ust_id: int | None, lat: float | None, lon: float | None, limit: int) -> list[dict]:
    """Birlesik arama: kapi numarasi (metin sonunda numara varsa), sokak, yer, yerlesim. tur: kapi|sokak|yer|yerlesim|None."""
    sonuc: list[dict] = []
    eslesme = KAPI_DESENI.match(q.strip())
    async with havuz().acquire() as baglanti:
        if eslesme and tur in (None, "kapi"):
            sonuc += await _kapi_ara(baglanti, ad_katla(eslesme["sokak"]), eslesme["no"], ust_id, limit)
        katli = ad_katla(q)
        if tur in (None, "sokak"):
            sonuc += await _sokak_ara(baglanti, ad_katla(eslesme["sokak"]) if eslesme and sonuc else katli, ust_id, lat, lon, limit)
        if tur in (None, "yer"):
            sonuc += await _yer_ara(baglanti, katli, ust_id, lat, lon, limit)
        if tur in (None, "bina"):
            sonuc += await _bina_ara(baglanti, katli, ust_id, lat, lon, limit)
    if tur in (None, "yerlesim"):
        for y in await yerlesim_crud.ara(q, None, ust_id, limit):
            ust = y["ust"] or {}
            sonuc.append({"tur": y["tur"], "id": y["id"], "ad": y["ad"], "merkez": y["merkez"], "mahalle": None, "ilce": None, "il": None,
                          "adres": ", ".join(p for p in (y["ad"], ust.get("ad")) if p), "skor": None, "mesafe_m": None,
                          "ek": {"nufus": y["nufus"], "ust": y["ust"]}})
    oncelik = {"kapi": 0, "sokak": 1, "bina": 2, "yer": 3}
    sonuc.sort(key=lambda r: (oncelik.get(r["tur"], 3), -(r["skor"] or 0)))
    return sonuc[:limit]


async def nokta(lat: float, lon: float, yaricap_m: int, limit: int) -> dict:
    """Ters arama: noktanin idari zinciri, en yakin sokaklar, kapi numaralari ve yerler; birlesik 'adres' metni."""
    idari = await yerlesim_crud.noktada(lat, lon)
    p = "ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography"
    async with havuz().acquire() as baglanti:
        sokaklar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, c.kod AS sinif, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon, ST_Distance(x.cizgi, {p}) AS mesafe,
                       {ZINCIR_ALAN} FROM sokak x JOIN tnm_yol_sinifi c ON c.id = x.sinif_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_DWithin(x.cizgi, {p}, $3) ORDER BY x.cizgi <-> {p} LIMIT $4""", lat, lon, yaricap_m, limit)
        kapilar = await baglanti.fetch(
            f"""SELECT x.id, x.kapi_no, s.ad AS sokak, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon, ST_Distance(x.konum, {p}) AS mesafe,
                       {ZINCIR_ALAN} FROM kapi_numarasi x LEFT JOIN sokak s ON s.id = x.sokak_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_DWithin(x.konum, {p}, $3) ORDER BY x.konum <-> {p} LIMIT $4""", lat, lon, min(yaricap_m, 100), limit)
        yerler = await baglanti.fetch(
            f"""SELECT x.id, x.ad, t.kod AS yer_turu, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon, ST_Distance(x.konum, {p}) AS mesafe,
                       {ZINCIR_ALAN} FROM yer_isareti x JOIN tnm_yer_turu t ON t.id = x.tur_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_DWithin(x.konum, {p}, $3) ORDER BY x.konum <-> {p} LIMIT $4""", lat, lon, min(yaricap_m, 300), limit)
        binalar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, t.kod AS bina_turu, k.kod AS kullanim, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon,
                       0::float8 AS mesafe, {ZINCIR_ALAN}
                  FROM bina x JOIN tnm_bina_turu t ON t.id = x.tur_id LEFT JOIN tnm_bina_kullanimi k ON k.id = x.kullanim_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_Covers(x.sinir, {p}) ORDER BY x.tur_id DESC, ST_Area(x.sinir) LIMIT $3""", lat, lon, limit)
    icinde = {s["tur"]: s["ad"] for s in idari["icinde"]}
    mahalle, ilce, il = icinde.get("mahalle_koy"), icinde.get("ilce"), icinde.get("il")
    en_iyi_kapi = next((k for k in kapilar if k["mesafe"] <= 40 and k["sokak"]), None)
    en_iyi_sokak = sokaklar[0] if sokaklar else None
    bina_adi = binalar[0]["ad"] if binalar else None
    if en_iyi_kapi:
        adres = adres_metni([bina_adi, f"{en_iyi_kapi['sokak']} No:{en_iyi_kapi['kapi_no']}"], mahalle, ilce, il)
    elif en_iyi_sokak:
        adres = adres_metni([bina_adi, en_iyi_sokak["ad"]], mahalle, ilce, il)
    else:
        adres = adres_metni([bina_adi], mahalle, ilce, il)
    return {
        "adres": adres, "mahalle": mahalle, "ilce": ilce, "il": il, "idari": idari,
        "sokaklar": [_kayit("sokak", s, s["ad"], [s["ad"]], None, {"sinif": s["sinif"]}) for s in sokaklar],
        "kapilar": [_kayit("kapi", s, f"{s['sokak'] or ''} No:{s['kapi_no']}".strip(), [f"{s['sokak'] or ''} No:{s['kapi_no']}".strip()], None,
                           {"sokak": s["sokak"], "kapi_no": s["kapi_no"]}) for s in kapilar],
        "yerler": [_kayit("yer", s, s["ad"], [s["ad"]], None, {"yer_turu": s["yer_turu"]}) for s in yerler],
        "binalar": [_kayit("bina", s, s["ad"], [s["ad"]], None, {"bina_turu": s["bina_turu"], "kullanim": s["kullanim"]}) for s in binalar],
    }


async def yerler_kutuda(bati: float, guney: float, dogu: float, kuzey: float, tur: str | None, limit: int) -> dict:
    """Harita katmani icin: kutu icindeki yer isaretleri (GeoJSON FeatureCollection)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            """SELECT x.id, x.ad, t.kod AS yer_turu, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon
                 FROM yer_isareti x JOIN tnm_yer_turu t ON t.id = x.tur_id
                WHERE x.aktif_mi AND x.konum && ST_MakeEnvelope($1, $2, $3, $4, 4326)::geography AND ($5::text IS NULL OR t.kod = $5)
                LIMIT $6""", bati, guney, dogu, kuzey, tur, limit)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
         "properties": {"id": s["id"], "ad": s["ad"], "tur": s["yer_turu"]}} for s in satirlar]}


async def sokaklar(mahalle_id: int, q: str | None, limit: int, atla: int) -> list[dict]:
    """Bir mahalle / koyun sokaklari (acilir liste icin), ada gore siralanir."""
    katli = ad_katla(q) if q else None
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, c.kod AS sinif, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon, {ZINCIR_ALAN}
                  FROM sokak x JOIN tnm_yol_sinifi c ON c.id = x.sinif_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND x.mahalle_id = $1 AND ($2::text IS NULL OR x.ad_arama LIKE '%' || $2 || '%')
                 ORDER BY x.ad_arama LIMIT $3 OFFSET $4""", mahalle_id, katli, limit, atla)
    return [_kayit("sokak", s, s["ad"], [s["ad"]], None, {"sinif": s["sinif"]}) for s in satirlar]


async def sokak_getir(sokak_id: int, cizgi: bool) -> dict | None:
    """Tek sokak; istenirse GeoJSON cizgisi ve kapi numarasi sayisi."""
    async with havuz().acquire() as baglanti:
        s = await baglanti.fetchrow(
            f"""SELECT x.id, x.ad, c.kod AS sinif, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon,
                       (SELECT count(*) FROM kapi_numarasi k WHERE k.sokak_id = x.id AND k.aktif_mi) AS kapi_adet,
                       {'ST_AsGeoJSON(x.cizgi::geometry, 6)' if cizgi else 'NULL'} AS geo, {ZINCIR_ALAN}
                  FROM sokak x JOIN tnm_yol_sinifi c ON c.id = x.sinif_id {ZINCIR_JOIN} WHERE x.aktif_mi AND x.id = $1""", sokak_id)
    if s is None:
        return None
    veri = _kayit("sokak", s, s["ad"], [s["ad"]], None, {"sinif": s["sinif"], "kapi_adet": s["kapi_adet"]})
    if cizgi:
        veri["cizgi"] = json.loads(s["geo"]) if s["geo"] else None
    return veri


async def kapilar(sokak_id: int, limit: int, atla: int) -> list[dict]:
    """Bir sokaktaki kapi numaralari (sayisal siraya yakin)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT x.id, x.kapi_no, s.ad AS sokak, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon, {ZINCIR_ALAN}
                  FROM kapi_numarasi x JOIN sokak s ON s.id = x.sokak_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND x.sokak_id = $1
                 ORDER BY NULLIF(regexp_replace(x.kapi_no_arama, '\\D.*$', ''), '')::int NULLS LAST, x.kapi_no_arama LIMIT $2 OFFSET $3""",
            sokak_id, limit, atla)
    return [_kayit("kapi", s, f"{s['sokak']} No:{s['kapi_no']}", [f"{s['sokak']} No:{s['kapi_no']}"], None,
                   {"sokak": s["sokak"], "kapi_no": s["kapi_no"]}) for s in satirlar]


async def _bina_listesi(kosul: str, parametreler: list, limit: int, atla: int) -> list[dict]:
    """Ortak bina / site listesi (kosul $1 icin mahalle veya sokak kimligini bekler)."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, t.kod AS bina_turu, k.kod AS kullanim, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon,
                       {ZINCIR_ALAN}
                  FROM bina x JOIN tnm_bina_turu t ON t.id = x.tur_id LEFT JOIN tnm_bina_kullanimi k ON k.id = x.kullanim_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND {kosul} ORDER BY t.id, x.ad_arama LIMIT ${len(parametreler) + 1} OFFSET ${len(parametreler) + 2}""",
            *parametreler, limit, atla)
    return [_kayit("bina", s, s["ad"], [s["ad"]], None, {"bina_turu": s["bina_turu"], "kullanim": s["kullanim"]}) for s in satirlar]


async def sokak_binalari(sokak_id: int, limit: int, atla: int) -> list[dict]:
    """Bir sokaga bagli adli site ve binalar (acilir liste icin)."""
    return await _bina_listesi("x.sokak_id = $1", [sokak_id], limit, atla)


async def mahalle_binalari(mahalle_id: int, q: str | None, limit: int, atla: int) -> list[dict]:
    """Bir mahalle / koydeki adli site ve binalar; q ile ada gore daraltilir."""
    if q:
        return await _bina_listesi("x.mahalle_id = $1 AND x.ad_arama LIKE '%' || $2 || '%'", [mahalle_id, ad_katla(q)], limit, atla)
    return await _bina_listesi("x.mahalle_id = $1", [mahalle_id], limit, atla)


async def bina_getir(bina_id: int, sinir: bool) -> dict | None:
    """Tek site / bina; istenirse GeoJSON poligonu."""
    async with havuz().acquire() as baglanti:
        s = await baglanti.fetchrow(
            f"""SELECT x.id, x.ad, t.kod AS bina_turu, k.kod AS kullanim, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon,
                       x.sokak_id, {'ST_AsGeoJSON(x.sinir::geometry, 6)' if sinir else 'NULL'} AS geo, {ZINCIR_ALAN}
                  FROM bina x JOIN tnm_bina_turu t ON t.id = x.tur_id LEFT JOIN tnm_bina_kullanimi k ON k.id = x.kullanim_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND x.id = $1""", bina_id)
    if s is None:
        return None
    veri = _kayit("bina", s, s["ad"], [s["ad"]], None, {"bina_turu": s["bina_turu"], "kullanim": s["kullanim"], "sokak_id": s["sokak_id"]})
    if s["sokak_id"]:
        ust = await sokak_getir(s["sokak_id"], False)
        veri["ek"]["sokak"] = {"id": ust["id"], "ad": ust["ad"]} if ust else None
    if sinir:
        veri["sinir"] = json.loads(s["geo"]) if s["geo"] else None
    return veri


async def yakin_yerler(lat: float, lon: float, yaricap_m: int, tur: str | None, limit: int) -> list[dict]:
    """Noktaya yaricap icindeki onemli yerler (or. akaryakit, yeme_icme, otel), yakindan uzaga."""
    p = "ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography"
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, t.kod AS yer_turu, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon,
                       ST_Distance(x.konum, {p}) AS mesafe, {ZINCIR_ALAN}
                  FROM yer_isareti x JOIN tnm_yer_turu t ON t.id = x.tur_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_DWithin(x.konum, {p}, $3) AND ($4::text IS NULL OR t.kod = $4)
                 ORDER BY x.konum <-> {p} LIMIT $5""", lat, lon, yaricap_m, tur, limit)
    return [_kayit("yer", s, s["ad"], [s["ad"]], None, {"yer_turu": s["yer_turu"]}) for s in satirlar]


async def rota_boyunca(koordinatlar: list[list[float]], tur: str | None, tampon_m: int, limit: int) -> list[dict]:
    """Rota cizgisine tampon_m icindeki yerler; rota uzerindeki konumlarina (oran 0-1) gore sirali (or. rota boyunca benzin)."""
    wkt = "SRID=4326;LINESTRING(" + ",".join(f"{k[0]} {k[1]}" for k in koordinatlar) + ")"
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""WITH hat AS (SELECT ST_GeogFromText($1) AS g)
                SELECT x.id, x.ad, t.kod AS yer_turu, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon,
                       ST_Distance(x.konum, hat.g) AS mesafe, ST_LineLocatePoint(hat.g::geometry, x.konum::geometry) AS oran, {ZINCIR_ALAN}
                  FROM hat, yer_isareti x JOIN tnm_yer_turu t ON t.id = x.tur_id {ZINCIR_JOIN}
                 WHERE x.aktif_mi AND ST_DWithin(x.konum, hat.g, $2) AND ($3::text IS NULL OR t.kod = $3)
                 ORDER BY oran LIMIT $4""", wkt, tampon_m, tur, limit)
    return [_kayit("yer", s, s["ad"], [s["ad"]], None, {"yer_turu": s["yer_turu"], "rota_orani": round(float(s["oran"]), 4)}) for s in satirlar]


async def sekil(tur: str, nesne_id: int) -> dict | None:
    """Herhangi bir adres ogesinin GeoJSON sekli (il / ilce / mahalle ... sinir; sokak cizgi; bina / site poligon)."""
    if tur == "sokak":
        veri = await sokak_getir(nesne_id, True)
        return veri and {"tur": "sokak", "id": nesne_id, "ad": veri["ad"], "geometri": veri["cizgi"]}
    if tur == "bina":
        veri = await bina_getir(nesne_id, True)
        return veri and {"tur": "bina", "id": nesne_id, "ad": veri["ad"], "geometri": veri["sinir"]}
    veri = await yerlesim_crud.getir(nesne_id, True)
    return veri and {"tur": veri["tur"], "id": nesne_id, "ad": veri["ad"], "geometri": veri["sinir"]}
