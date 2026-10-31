"""Veritabani araci: tablo listesi, yapi, veri ve salt okunur SQL (yalniz yonetim anahtariyla erisilir)."""

import datetime
import decimal
import re
import uuid

import asyncpg

from app.db import havuz

SEMA = "public"
GIZLI_KOLON = re.compile(r"(hash|sifre|parola|password|ozet|secret|token)", re.I)
ISLEMLER = {"=": "=", "<>": "<>", ">": ">", "<": "<", ">=": ">=", "<=": "<=", "icerir": "ILIKE", "bos": "IS NULL", "dolu": "IS NOT NULL"}
COGRAFI_TIPLER = ("geography", "geometry")
SQL_ZAMAN_ASIMI_MS = 15000
SQL_SATIR_SINIRI = 1000
HUCRE_SINIRI = 300


class VeritabaniHatasi(Exception):
    """Kullaniciya gosterilebilecek gecersiz istek (tablo, kolon, sorgu)."""


def _guvenli(deger):  # noqa: ANN001, ANN202
    """JSON'a cevrilebilir degere donusturur."""
    if deger is None or isinstance(deger, (bool, int, float, str)):
        return deger
    if isinstance(deger, (datetime.datetime, datetime.date, datetime.time)):
        return deger.isoformat()
    if isinstance(deger, (decimal.Decimal, uuid.UUID)):
        return str(deger)
    if isinstance(deger, (bytes, bytearray, memoryview)):
        return "[ikili]"
    return str(deger)


def _kisalt(deger):  # noqa: ANN001, ANN202
    """Cok uzun metinleri hucre siniriyla keser."""
    deger = _guvenli(deger)
    return deger[:HUCRE_SINIRI] + "..." if isinstance(deger, str) and len(deger) > HUCRE_SINIRI else deger


async def ozet() -> dict:
    """Motor, boyut, tablo sayisi ve toplam satir."""
    async with havuz().acquire() as baglanti:
        motor = await baglanti.fetchval("SELECT version()")
        boyut = await baglanti.fetchval("SELECT pg_database_size(current_database())")
    liste = await tablolar()
    tablo = [t for t in liste if t["tur"] == "tablo"]
    return {"motor": motor.split(" on ")[0], "boyut_bayt": boyut, "tablo_adedi": len(tablo), "toplam_satir": sum(t["satir"] or 0 for t in tablo)}


async def tablolar() -> list[dict]:
    """Public semadaki tablo ve gorunumler; satir sayisi (tablolarda tam, olamazsa tahmin) ve boyut."""
    async with havuz().acquire() as baglanti:
        satirlar = await baglanti.fetch(
            """SELECT c.relname AS ad, c.relkind::text AS tur, pg_total_relation_size(c.oid) AS boyut, c.reltuples::bigint AS tahmin
                 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = $1 AND c.relkind IN ('r', 'p', 'v', 'm') ORDER BY c.relname""", SEMA)
        sonuc = []
        for s in satirlar:
            satir = None
            if s["tur"] in ("r", "p"):
                try:
                    async with baglanti.transaction():
                        await baglanti.execute("SET LOCAL statement_timeout = 5000")
                        satir = await baglanti.fetchval(f'SELECT count(*) FROM "{SEMA}"."{s["ad"]}"')
                except asyncpg.PostgresError:
                    satir = max(int(s["tahmin"]), 0)
            sonuc.append({"ad": s["ad"], "tur": "tablo" if s["tur"] in ("r", "p") else "gorunum", "satir": satir, "boyut_bayt": s["boyut"]})
    return sonuc


async def _kolonlar(baglanti: asyncpg.Connection, tablo: str) -> list[dict]:
    """Tablonun kolonlari: ad, tip, bos olabilir, varsayilan, birincil anahtar, yabanci anahtar hedefi."""
    satirlar = await baglanti.fetch(
        """SELECT a.attname AS ad, format_type(a.atttypid, a.atttypmod) AS tip, NOT a.attnotnull AS bos_olabilir,
                  pg_get_expr(d.adbin, d.adrelid) AS varsayilan,
                  EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indisprimary AND a.attnum = ANY (i.indkey)) AS birincil,
                  (SELECT fc.relname || '.' || fa.attname FROM pg_constraint k JOIN pg_class fc ON fc.oid = k.confrelid
                     JOIN pg_attribute fa ON fa.attrelid = k.confrelid AND fa.attnum = k.confkey[array_position(k.conkey, a.attnum)]
                    WHERE k.conrelid = c.oid AND k.contype = 'f' AND a.attnum = ANY (k.conkey) LIMIT 1) AS yabanci
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
             LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname = $1 AND c.relname = $2 AND c.relkind IN ('r', 'p', 'v', 'm') ORDER BY a.attnum""", SEMA, tablo)
    if not satirlar:
        raise VeritabaniHatasi("Tablo bulunamadi.")
    return [dict(s) for s in satirlar]


async def yapi(tablo: str) -> dict:
    """Tablonun kolonlari ve dizinleri."""
    async with havuz().acquire() as baglanti:
        kolonlar = await _kolonlar(baglanti, tablo)
        dizinler = await baglanti.fetch("SELECT indexname AS ad, indexdef AS tanim FROM pg_indexes WHERE schemaname = $1 AND tablename = $2 ORDER BY indexname", SEMA, tablo)
    return {"tablo": tablo, "kolonlar": kolonlar, "dizinler": [dict(d) for d in dizinler]}


def _cografi_mi(kolon: dict) -> bool:
    return kolon["tip"].startswith(COGRAFI_TIPLER)


def _secim(kolon: dict) -> str:
    """Kolonu metne ceviren SELECT ifadesi: cografi veri kisaltilir, gizli kolonlar maskelenir."""
    ad = f'"{kolon["ad"]}"'
    if GIZLI_KOLON.search(kolon["ad"]):
        return f"CASE WHEN {ad} IS NULL THEN NULL ELSE '[gizli]' END"
    if _cografi_mi(kolon):
        g = f"{ad}::geometry"
        return f"CASE WHEN {ad} IS NULL THEN NULL WHEN ST_NPoints({g}) > 20 THEN GeometryType({g}) || ' (' || ST_NPoints({g}) || ' nokta)' ELSE ST_AsText({g}) END"
    return f"left({ad}::text, {HUCRE_SINIRI})"


async def veri(tablo: str, sayfa: int, boyut: int, ara: str | None, kolon: str | None, islem: str, deger: str | None,
               sirala: str | None, yon: str) -> dict:
    """Sayfalanmis tablo verisi; tum kolonlarda arama ve tek kolon filtresi."""
    if islem not in ISLEMLER:
        raise VeritabaniHatasi("Gecersiz filtre islemi.")
    async with havuz().acquire() as baglanti:
        kolonlar = await _kolonlar(baglanti, tablo)
        tipler = {k["ad"]: k for k in kolonlar}
        if (kolon and kolon not in tipler) or (sirala and sirala not in tipler):
            raise VeritabaniHatasi("Gecersiz kolon.")
        kosullar: list[str] = []
        parametreler: list = []
        if ara:
            aranabilir = [k for k in kolonlar if not GIZLI_KOLON.search(k["ad"]) and not _cografi_mi(k)]
            if aranabilir:
                parametreler.append(f"%{ara}%")
                kosullar.append("(" + " OR ".join(f'"{k["ad"]}"::text ILIKE ${len(parametreler)}' for k in aranabilir) + ")")
        if kolon:
            if GIZLI_KOLON.search(kolon) or _cografi_mi(tipler[kolon]):
                raise VeritabaniHatasi("Bu kolonda filtre desteklenmez.")
            if islem in ("bos", "dolu"):
                kosullar.append(f'"{kolon}" {ISLEMLER[islem]}')
            elif deger is not None:
                parametreler.append(f"%{deger}%" if islem == "icerir" else deger)
                kosullar.append(f'"{kolon}"::text {ISLEMLER[islem]} ${len(parametreler)}')
        where = " WHERE " + " AND ".join(kosullar) if kosullar else ""
        birincil = next((k["ad"] for k in kolonlar if k["birincil"]), None)
        sira_kolon = sirala or birincil
        order = ""
        if sira_kolon and not _cografi_mi(tipler[sira_kolon]):
            order = f' ORDER BY "{sira_kolon}" {"DESC" if yon == "azalan" else "ASC"}'
        secim = ", ".join(f'{_secim(k)} AS "{k["ad"]}"' for k in kolonlar)
        hedef = f'"{SEMA}"."{tablo}"'
        try:
            async with baglanti.transaction(readonly=True):
                await baglanti.execute("SET LOCAL statement_timeout = 10000")
                toplam = await baglanti.fetchval(f"SELECT count(*) FROM {hedef}{where}", *parametreler)
                satirlar = await baglanti.fetch(f"SELECT {secim} FROM {hedef}{where}{order} LIMIT {boyut} OFFSET {(sayfa - 1) * boyut}", *parametreler)
        except asyncpg.PostgresError as hata:
            raise VeritabaniHatasi("Sorgu calistirilamadi (filtre degeri bu kolon tipine uymuyor olabilir).") from hata
    return {"tablo": tablo, "toplam": toplam, "sayfa": sayfa, "boyut": boyut,
            "kolonlar": [{"ad": k["ad"], "tip": k["tip"], "birincil": k["birincil"], "yabanci": k["yabanci"]} for k in kolonlar],
            "satirlar": [[_kisalt(s[k["ad"]]) for k in kolonlar] for s in satirlar]}


async def sql_calistir(sorgu: str) -> dict:
    """Tek bir salt okunur SELECT / WITH sorgusu; en fazla SQL_SATIR_SINIRI satir, zaman asimi var."""
    metin = sorgu.strip().rstrip(";").strip()
    if ";" in metin:
        raise VeritabaniHatasi("Yalniz tek bir sorgu calistirilabilir.")
    if not re.match(r"^(select|with)\b", metin, re.I):
        raise VeritabaniHatasi("Yalniz SELECT veya WITH sorgulari calistirilabilir (salt okunur).")
    async with havuz().acquire() as baglanti:
        try:
            async with baglanti.transaction(readonly=True):
                await baglanti.execute(f"SET LOCAL statement_timeout = {SQL_ZAMAN_ASIMI_MS}")
                satirlar = await baglanti.fetch(f"SELECT * FROM ({metin}) AS _sonuc LIMIT {SQL_SATIR_SINIRI + 1}")
        except asyncpg.PostgresError as hata:
            raise VeritabaniHatasi(f"Sorgu hatasi: {str(hata).splitlines()[0][:300]}") from hata
    kolonlar = list(satirlar[0].keys()) if satirlar else []
    kesildi = len(satirlar) > SQL_SATIR_SINIRI
    return {"kolonlar": kolonlar, "satirlar": [[_kisalt(s[k]) for k in kolonlar] for s in satirlar[:SQL_SATIR_SINIRI]], "kesildi": kesildi}
