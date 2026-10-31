"""Ortak kapi numarasi havuzu: projelerin bildirdigi teslimat / ziyaret konumlarindan OSM'de olmayan kapilari ogrenir.

Kapinin konumu son GOZLEM_SINIRI gozlemin geometrik ortancasidir; bir kapi en az GUVENILIR_GOZLEM gozlemle "dogrulandi" sayilir.
"""

from app.db import havuz

SOKAGA_EN_FAZLA_M = 250
GOZLEM_SINIRI = 50
GUVENILIR_GOZLEM = 2


def no_katla(kapi_no: str) -> str:
    """Kapi numarasini aramaya uygun bicime getirir (yukleyici ile ayni kural: kucuk harf, bosluksuz)."""
    return kapi_no.strip().lower().replace(" ", "")[:20]


_SATIR = """k.id, k.sokak_id, s.ad AS sokak, k.kapi_no, ST_Y(k.konum::geometry) AS lat, ST_X(k.konum::geometry) AS lon,
            k.gozlem_sayisi, k.proje_sayisi, k.guncelleme"""


def _kayit(s) -> dict:
    """Satiri API sozlugune cevirir."""
    return {"id": s["id"], "sokak_id": s["sokak_id"], "sokak": s["sokak"], "kapi_no": s["kapi_no"],
            "konum": {"lat": s["lat"], "lon": s["lon"]}, "gozlem_sayisi": s["gozlem_sayisi"], "proje_sayisi": s["proje_sayisi"],
            "guvenilir": s["gozlem_sayisi"] >= GUVENILIR_GOZLEM, "guncelleme": s["guncelleme"].isoformat()}


async def _yeniden_hesapla(baglanti, kapi_id: int) -> None:
    """Kapinin konumunu ve sayaclarini son gozlemlerden yeniden hesaplar; gozlemi kalmayan kapiyi siler."""
    await baglanti.execute(
        """DELETE FROM kapi_gozlem WHERE kapi_ogrenilen_id = $1 AND id NOT IN
             (SELECT id FROM kapi_gozlem WHERE kapi_ogrenilen_id = $1 ORDER BY zaman DESC LIMIT $2)""", kapi_id, GOZLEM_SINIRI)
    ozet = await baglanti.fetchrow(
        """SELECT count(*) AS adet, count(DISTINCT proje_id) AS proje,
                  ST_GeometricMedian(ST_Collect(konum::geometry)) AS orta
             FROM kapi_gozlem WHERE kapi_ogrenilen_id = $1""", kapi_id)
    if not ozet["adet"]:
        await baglanti.execute("DELETE FROM kapi_ogrenilen WHERE id = $1", kapi_id)
        return
    await baglanti.execute(
        """UPDATE kapi_ogrenilen SET konum = ST_SetSRID($2::geometry, 4326)::geography, gozlem_sayisi = $3, proje_sayisi = $4,
                  guncelleme = now() WHERE id = $1""", kapi_id, ozet["orta"], ozet["adet"], ozet["proje"])


async def ogren(proje_id: int, sokak_id: int, kapi_no: str, lat: float, lon: float, dogruluk_m: float | None) -> dict:
    """Bir kapi gozlemi ekler. Sokak yoksa ya da nokta sokaga uzaksa ValueError; OSM'de bu kapi varsa onu dondurur (havuza eklenmez)."""
    arama = no_katla(kapi_no)
    p = "ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography"
    async with havuz().acquire() as baglanti, baglanti.transaction():
        uzaklik = await baglanti.fetchval(f"SELECT ST_Distance(cizgi, {p}) FROM sokak WHERE id = $1 AND aktif_mi", sokak_id, lat, lon)
        if uzaklik is None:
            raise ValueError("Sokak bulunamadi.")
        if uzaklik > SOKAGA_EN_FAZLA_M:
            raise ValueError(f"Konum sokaga {round(uzaklik)} m uzakta (en fazla {SOKAGA_EN_FAZLA_M} m).")
        osm = await baglanti.fetchrow(
            """SELECT id, kapi_no, ST_Y(konum::geometry) AS lat, ST_X(konum::geometry) AS lon FROM kapi_numarasi
                WHERE aktif_mi AND sokak_id = $1 AND kapi_no_arama = $2 LIMIT 1""", sokak_id, arama)
        if osm:
            return {"durum": "osm_var", "kapi": {"id": osm["id"], "kapi_no": osm["kapi_no"], "konum": {"lat": osm["lat"], "lon": osm["lon"]}}}
        kapi_id = await baglanti.fetchval(
            f"""INSERT INTO kapi_ogrenilen (sokak_id, kapi_no, kapi_no_arama, konum) VALUES ($1, $4, $5, {p})
                ON CONFLICT (sokak_id, kapi_no_arama) DO UPDATE SET guncelleme = now() RETURNING id""",
            sokak_id, lat, lon, kapi_no.strip()[:20], arama)
        await baglanti.execute(
            f"INSERT INTO kapi_gozlem (kapi_ogrenilen_id, proje_id, konum, dogruluk_m) VALUES ($1, $4, {p}, $5)",
            kapi_id, lat, lon, proje_id, dogruluk_m)
        await _yeniden_hesapla(baglanti, kapi_id)
        s = await baglanti.fetchrow(f"SELECT {_SATIR} FROM kapi_ogrenilen k JOIN sokak s ON s.id = k.sokak_id WHERE k.id = $1", kapi_id)
    return {"durum": "eklendi", "kapi": _kayit(s)}


async def geri_al(proje_id: int, kapi_id: int) -> bool:
    """Projenin bu kapi icin verdigi gozlemleri siler (yanlis bildirim); kapi yeniden hesaplanir. Silinen yoksa False."""
    async with havuz().acquire() as baglanti, baglanti.transaction():
        silinen = await baglanti.execute("DELETE FROM kapi_gozlem WHERE kapi_ogrenilen_id = $1 AND proje_id = $2", kapi_id, proje_id)
        if silinen.endswith(" 0"):
            return False
        await _yeniden_hesapla(baglanti, kapi_id)
    return True


async def sokakta(baglanti, sokak_idleri: list[int], kapi_no: str) -> list[dict]:
    """Aday sokaklarda havuzdan ogrenilmis bu numarali kapilar (ayristirma icin; OSM kapilariyla ayni bicim)."""
    satirlar = await baglanti.fetch(
        """SELECT k.id, k.kapi_no, k.sokak_id, ST_Y(k.konum::geometry) AS lat, ST_X(k.konum::geometry) AS lon, k.gozlem_sayisi
             FROM kapi_ogrenilen k WHERE k.sokak_id = ANY($1::bigint[]) AND k.kapi_no_arama = $2
            ORDER BY array_position($1::bigint[], k.sokak_id)""", sokak_idleri, no_katla(kapi_no))
    return [{**dict(s), "kaynak": "havuz", "guvenilir": s["gozlem_sayisi"] >= GUVENILIR_GOZLEM} for s in satirlar]


async def en_yakin(sokak_id: int, lat: float, lon: float, yaricap_m: int) -> dict | None:
    """Sokakta noktaya en yakin ogrenilmis kapi (OSM'de kapi yoksa yedek)."""
    p = "ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography"
    async with havuz().acquire() as baglanti:
        s = await baglanti.fetchrow(
            f"""SELECT {_SATIR}, ST_Distance(k.konum, {p}) AS mesafe FROM kapi_ogrenilen k JOIN sokak s ON s.id = k.sokak_id
                 WHERE k.sokak_id = $1 AND ST_DWithin(k.konum, {p}, $4) ORDER BY k.konum <-> {p} LIMIT 1""",
            sokak_id, lat, lon, yaricap_m)
    return {**_kayit(s), "mesafe_m": round(s["mesafe"], 1)} if s else None


async def sokak_kapilari(sokak_id: int) -> list[dict]:
    """Sokakta havuzdan ogrenilmis tum kapilar."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            f"""SELECT {_SATIR} FROM kapi_ogrenilen k JOIN sokak s ON s.id = k.sokak_id WHERE k.sokak_id = $1
                 ORDER BY NULLIF(regexp_replace(k.kapi_no_arama, '\\D.*$', ''), '')::int NULLS LAST, k.kapi_no_arama""", sokak_id)
    return [_kayit(s) for s in satirlar]
