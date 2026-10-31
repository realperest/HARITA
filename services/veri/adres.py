"""Adres yukleyicisi: OSM Turkiye verisinden sokak / cadde, onemli yerler (yer isareti) ve kapi numaralari.

Akis: osmium ile yalniz gerekli ogeleri ayikla -> pyosmium ile akisli oku (bellek dostu, COPY ile toplu yaz) ->
mahalle / koy sinirina gore mekansal esle (yerlesim tablosu) -> sokaklari mahalle bazinda birlestir -> kapi numaralarini sokaga bagla.
Kaynak OpenStreetMap (c) OpenStreetMap katkicilari, ODbL.
"""

import logging
import subprocess
from pathlib import Path

import osmium
import psycopg

log = logging.getLogger("adres")

# OSM etiketi -> tnm_yer_turu.kod (SIPARIS ile ayni eslesme)
AMENITY_TURLERI = {
    "pharmacy": "eczane",
    "hospital": "saglik", "clinic": "saglik", "doctors": "saglik", "dentist": "saglik",
    "school": "egitim", "kindergarten": "egitim", "university": "egitim", "college": "egitim",
    "place_of_worship": "ibadet",
    "townhall": "kamu", "police": "kamu", "post_office": "kamu", "courthouse": "kamu", "fire_station": "kamu",
    "bank": "banka",
    "fuel": "akaryakit",
    "restaurant": "yeme_icme", "fast_food": "yeme_icme", "cafe": "yeme_icme",
    "marketplace": "market",
}
SHOP_TURLERI = {
    "supermarket": "market", "convenience": "market", "greengrocer": "market", "butcher": "market",
    "bakery": "firin", "pastry": "firin", "confectionery": "firin",
}
TOURISM_TURLERI = {"hotel": "otel", "motel": "otel", "guest_house": "otel"}

ARAMA_KOLONLARI = {
    "gecici_sokak_parca": "ad, ad_arama, sinif_id, wkb",
    "gecici_yer": "kaynak_anahtari, tur_id, ad, ad_arama, lon, lat",
    "gecici_kapi": "kaynak_anahtari, kapi_no, kapi_no_arama, sokak_ad, sokak_ad_arama, lon, lat",
}
TOPLU_BOYUT = 50_000


def yer_turu(etiketler) -> str | None:  # noqa: ANN001
    """OSM etiketlerinden tnm_yer_turu.kod; onemli yer degilse None. Bos / 'vacant' dukkan alinmaz."""
    tur = AMENITY_TURLERI.get(etiketler.get("amenity")) or TOURISM_TURLERI.get(etiketler.get("tourism"))
    if tur:
        return tur
    dukkan = etiketler.get("shop")
    if dukkan and dukkan not in ("vacant", "no"):
        return SHOP_TURLERI.get(dukkan, "dukkan")
    return None


class Toplayici(osmium.SimpleHandler):
    """Dugum ve yollari akisli okur; satirlari biriktirip TOPLU_BOYUT'ta veritabanina COPY ile yazar."""

    def __init__(self, baglanti: psycopg.Connection, ad_katla, yol_siniflari: dict[str, int], yer_turleri: dict[str, int]) -> None:
        super().__init__()
        self.baglanti = baglanti
        self.ad_katla = ad_katla
        self.yol_siniflari = yol_siniflari
        self.yer_turleri = yer_turleri
        self.tamponlar: dict[str, list[tuple]] = {tablo: [] for tablo in ARAMA_KOLONLARI}
        self.sayac = {"sokak_parca": 0, "yer": 0, "kapi": 0}
        self._wkb = osmium.geom.WKBFactory()

    def _ekle(self, tablo: str, satir: tuple, sayac: str) -> None:
        self.tamponlar[tablo].append(satir)
        self.sayac[sayac] += 1
        if len(self.tamponlar[tablo]) >= TOPLU_BOYUT:
            self.bosalt(tablo)

    def bosalt(self, tablo: str | None = None) -> None:
        """Tamponu COPY ile yazar ve islemi onaylar."""
        for ad in ([tablo] if tablo else list(self.tamponlar)):
            satirlar = self.tamponlar[ad]
            if not satirlar:
                continue
            with self.baglanti.cursor() as imlec, imlec.copy(f"COPY {ad} ({ARAMA_KOLONLARI[ad]}) FROM STDIN") as kopya:
                for satir in satirlar:
                    kopya.write_row(satir)
            self.baglanti.commit()
            self.tamponlar[ad] = []
        toplam = sum(self.sayac.values())
        if toplam and toplam % 500_000 < TOPLU_BOYUT:
            log.info("Okunan: sokak parcasi=%s yer=%s kapi=%s", self.sayac["sokak_parca"], self.sayac["yer"], self.sayac["kapi"])

    def _kapi(self, anahtar: str, etiketler, lon: float, lat: float) -> None:  # noqa: ANN001
        no = (etiketler.get("addr:housenumber") or "").strip()
        if no:
            sokak = (etiketler.get("addr:street") or "").strip()
            self._ekle("gecici_kapi", (anahtar, no[:20], no.lower().replace(" ", "")[:20], sokak or None,
                                       self.ad_katla(sokak) if sokak else None, lon, lat), "kapi")

    def _yer(self, anahtar: str, etiketler, lon: float, lat: float) -> None:  # noqa: ANN001
        ad = etiketler.get("name")
        tur = yer_turu(etiketler)
        if ad and tur:
            self._ekle("gecici_yer", (anahtar, self.yer_turleri[tur], ad[:200], self.ad_katla(ad)[:200], lon, lat), "yer")

    def node(self, n) -> None:  # noqa: ANN001
        if not n.tags or not n.location.valid():
            return
        lon, lat = n.location.lon, n.location.lat
        self._kapi(f"osm:node:{n.id}", n.tags, lon, lat)
        self._yer(f"osm:node:{n.id}", n.tags, lon, lat)

    def way(self, w) -> None:  # noqa: ANN001
        t = w.tags
        sinif = self.yol_siniflari.get(t.get("highway"))
        ad = t.get("name")
        if sinif and ad:
            try:
                self._ekle("gecici_sokak_parca", (ad[:200], self.ad_katla(ad)[:200], sinif, self._wkb.create_linestring(w)), "sokak_parca")
            except RuntimeError:  # konumu eksik / gecersiz yol atlanir
                return
            return
        if "addr:housenumber" in t or ("name" in t and yer_turu(t)):
            konumlar = [n.location for n in w.nodes if n.location.valid()]
            if not konumlar:
                return
            lon = sum(k.lon for k in konumlar) / len(konumlar)
            lat = sum(k.lat for k in konumlar) / len(konumlar)
            self._kapi(f"osm:way:{w.id}", t, lon, lat)
            self._yer(f"osm:way:{w.id}", t, lon, lat)


def ayikla(kaynak: Path, hedef_dizin: Path) -> Path:
    """osmium ile yalniz adres icin gerekli ogeleri (ve dayanaklarini) ayiklar."""
    hedef = hedef_dizin / "adres.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(kaynak), "n/addr:housenumber", "n/amenity", "n/shop", "n/tourism",
                    "w/highway", "w/addr:housenumber", "w/amenity", "w/shop", "w/tourism", "-o", str(hedef), "--overwrite"], check=True)
    return hedef


GECICI_SEMA = [
    "CREATE UNLOGGED TABLE IF NOT EXISTS gecici_sokak_parca (ad text, ad_arama text, sinif_id smallint, wkb text, mahalle_id bigint, geom geometry(LineString, 4326))",
    "CREATE UNLOGGED TABLE IF NOT EXISTS gecici_yer (kaynak_anahtari text, tur_id smallint, ad text, ad_arama text, lon float8, lat float8)",
    "CREATE UNLOGGED TABLE IF NOT EXISTS gecici_kapi (kaynak_anahtari text, kapi_no text, kapi_no_arama text, sokak_ad text, sokak_ad_arama text, lon float8, lat float8)",
]

# Mahalle eslemesi geography yerine geometry + GiST dizinli gecici tabloda yapilir (Turkiye olceginde cok daha hizli)
MAHALLE_HAZIRLA = [
    "DROP TABLE IF EXISTS gecici_mahalle",
    "CREATE UNLOGGED TABLE gecici_mahalle AS SELECT id, sinir::geometry AS g FROM yerlesim WHERE tur_id = 3 AND aktif_mi AND sinir IS NOT NULL",
    "CREATE INDEX ix_gecici_mahalle_g ON gecici_mahalle USING gist (g)",
    "ANALYZE gecici_mahalle",
]

MAHALLE_BUL = """(SELECT m.id FROM gecici_mahalle m WHERE ST_Covers(m.g, ({nokta})::geometry) LIMIT 1)"""

ISLEM_SQL = [
    # 1) sokak parcalarinin geometrisi ve mahallesi
    "UPDATE gecici_sokak_parca SET geom = ST_SetSRID(ST_GeomFromWKB(decode(wkb, 'hex')), 4326), wkb = NULL",
    "DELETE FROM gecici_sokak_parca WHERE geom IS NULL OR ST_NPoints(geom) < 2",
    "UPDATE gecici_sokak_parca SET mahalle_id = " + MAHALLE_BUL.format(nokta="ST_LineInterpolatePoint(geom, 0.5)"),
    # 2) ayni mahalle + ayni ad = tek sokak
    """INSERT INTO sokak (kaynak_anahtari, ad, ad_arama, sinif_id, mahalle_id, cizgi, merkez, surum_id, aktif_mi)
       SELECT 'sokak:' || COALESCE(mahalle_id::text, '0') || ':' || ad_arama, min(ad), ad_arama, min(sinif_id), mahalle_id,
              ST_Multi(ST_LineMerge(ST_Collect(geom)))::geography,
              ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom)))::geography, %(surum)s, TRUE
         FROM gecici_sokak_parca GROUP BY mahalle_id, ad_arama
       ON CONFLICT (kaynak_anahtari) DO UPDATE SET ad = EXCLUDED.ad, sinif_id = EXCLUDED.sinif_id, cizgi = EXCLUDED.cizgi,
            merkez = EXCLUDED.merkez, surum_id = EXCLUDED.surum_id, aktif_mi = TRUE""",
    # 3) yer isaretleri
    """INSERT INTO yer_isareti (tur_id, kaynak_anahtari, ad, ad_arama, konum, mahalle_id, surum_id, aktif_mi)
       SELECT g.tur_id, g.kaynak_anahtari, g.ad, g.ad_arama, k.konum, """ + MAHALLE_BUL.format(nokta="k.konum") + """, %(surum)s, TRUE
         FROM gecici_yer g CROSS JOIN LATERAL (SELECT ST_SetSRID(ST_MakePoint(g.lon, g.lat), 4326)::geography AS konum) k
       ON CONFLICT (kaynak_anahtari) DO UPDATE SET tur_id = EXCLUDED.tur_id, ad = EXCLUDED.ad, ad_arama = EXCLUDED.ad_arama,
            konum = EXCLUDED.konum, mahalle_id = EXCLUDED.mahalle_id, surum_id = EXCLUDED.surum_id, aktif_mi = TRUE""",
    # 4) kapi numaralari (once mahalle, sonra sokak baglama)
    """INSERT INTO kapi_numarasi (kaynak_anahtari, kapi_no, kapi_no_arama, sokak_ad, konum, mahalle_id, surum_id, aktif_mi)
       SELECT g.kaynak_anahtari, g.kapi_no, g.kapi_no_arama, g.sokak_ad, k.konum, """ + MAHALLE_BUL.format(nokta="k.konum") + """, %(surum)s, TRUE
         FROM gecici_kapi g CROSS JOIN LATERAL (SELECT ST_SetSRID(ST_MakePoint(g.lon, g.lat), 4326)::geography AS konum) k
       ON CONFLICT (kaynak_anahtari) DO UPDATE SET kapi_no = EXCLUDED.kapi_no, kapi_no_arama = EXCLUDED.kapi_no_arama,
            sokak_ad = EXCLUDED.sokak_ad, sokak_id = NULL, konum = EXCLUDED.konum, mahalle_id = EXCLUDED.mahalle_id,
            surum_id = EXCLUDED.surum_id, aktif_mi = TRUE""",
]

def tablo_bekle(baglanti: psycopg.Connection) -> None:
    """Gateway adres semasini kurana kadar bekler."""
    import time
    for _ in range(180):
        baglanti.rollback()
        if baglanti.execute("SELECT to_regclass('sokak') IS NOT NULL AND to_regclass('kapi_numarasi') IS NOT NULL").fetchone()[0]:
            return
        log.info("Adres semasi bekleniyor (gateway tablolari kurmali)...")
        time.sleep(10)
    raise RuntimeError("adres tablolari olusmadi")


def gerekli_mi(baglanti: psycopg.Connection, guncelleme_gun: int, zorla: bool) -> bool:
    """Son basarili adres yuklemesi yoksa veya guncelleme_gun'den eskiyse True."""
    if zorla:
        return True
    son = baglanti.execute(
        """SELECT bitis < now() - make_interval(days => %s) FROM adres_surum s JOIN tnm_islem_durumu d ON d.id = s.durum_id
            WHERE d.kod = 'tamam' ORDER BY s.bitis DESC LIMIT 1""", (guncelleme_gun,)).fetchone()
    return son is None or bool(son[0])


def calistir(baglanti: psycopg.Connection, indir, kaynak_tarihi, ad_katla, veri_dizini: Path) -> None:
    """Bir tam adres yukleme calismasi. indir() PBF yolunu, kaynak_tarihi(pbf) tarih metnini dondurur."""
    durum = lambda kod: f"(SELECT id FROM tnm_islem_durumu WHERE kod = '{kod}')"  # noqa: E731
    baglanti.execute(f"UPDATE adres_surum SET durum_id = {durum('hata')}, hata_mesaji = 'Yarida kaldi', bitis = now() "
                     f"WHERE durum_id = {durum('calisiyor')}")
    surum = baglanti.execute(f"INSERT INTO adres_surum (durum_id) VALUES ({durum('calisiyor')}) RETURNING id").fetchone()[0]
    baglanti.commit()
    try:
        ham = indir()
        # Turkiye olceginde osmium tags-filter bellek sinirini asiyor (SIGKILL); dosya dogrudan, diskte konum indeksiyle okunur
        ayiklanmis = ham
        tarih = kaynak_tarihi(ham)
        yol_siniflari = dict(baglanti.execute("SELECT kod, id FROM tnm_yol_sinifi").fetchall())
        yer_turleri = dict(baglanti.execute("SELECT kod, id FROM tnm_yer_turu").fetchall())

        for sorgu in GECICI_SEMA:
            baglanti.execute(sorgu)
        for tablo in ARAMA_KOLONLARI:
            baglanti.execute(f"TRUNCATE {tablo}")
        baglanti.commit()

        toplayici = Toplayici(baglanti, ad_katla, yol_siniflari, yer_turleri)
        indeks = veri_dizini / "adres_dugum.idx"
        try:
            toplayici.apply_file(str(ayiklanmis), locations=True, idx=f"sparse_file_array,{indeks}")
        finally:
            indeks.unlink(missing_ok=True)
        toplayici.bosalt()
        log.info("Okuma bitti: sokak parcasi=%s yer=%s kapi=%s. Eslestirme basliyor...", *toplayici.sayac.values())

        for sorgu in MAHALLE_HAZIRLA:
            baglanti.execute(sorgu)
        baglanti.commit()
        for sorgu in ISLEM_SQL:
            baglanti.execute(sorgu, {"surum": surum})
            baglanti.commit()
        # Adi yazili kapilari sokaga bagla: ayni mahallede ayni (katlanmis) adli sokak
        baglanti.execute("CREATE INDEX IF NOT EXISTS ix_gecici_kapi_anahtar ON gecici_kapi (kaynak_anahtari)")
        baglanti.execute("UPDATE kapi_numarasi k SET sokak_id = s.id FROM gecici_kapi g, sokak s WHERE k.surum_id = %s "
                         "AND g.kaynak_anahtari = k.kaynak_anahtari AND g.sokak_ad_arama IS NOT NULL AND s.aktif_mi "
                         "AND s.ad_arama = g.sokak_ad_arama AND k.mahalle_id IS NOT DISTINCT FROM s.mahalle_id", (surum,))
        baglanti.commit()
        # Adi yazili ama tam eslesmeyen kapilar: ayni mahallede benzer adli sokak (yazim farki); yoksa sokaga baglanmaz
        baglanti.execute("UPDATE kapi_numarasi k SET sokak_id = (SELECT s.id FROM sokak s WHERE s.aktif_mi AND s.ad_arama %% g.sokak_ad_arama "
                         "AND similarity(s.ad_arama, g.sokak_ad_arama) > 0.6 AND k.mahalle_id IS NOT DISTINCT FROM s.mahalle_id "
                         "ORDER BY similarity(s.ad_arama, g.sokak_ad_arama) DESC LIMIT 1) FROM gecici_kapi g "
                         "WHERE k.surum_id = %s AND k.sokak_id IS NULL AND g.kaynak_anahtari = k.kaynak_anahtari AND g.sokak_ad_arama IS NOT NULL", (surum,))
        baglanti.commit()
        # Sokak adi hic yazilmamis kapilar: 60 m icindeki en yakin sokak
        baglanti.execute("UPDATE kapi_numarasi k SET sokak_id = (SELECT s.id FROM sokak s WHERE s.aktif_mi AND ST_DWithin(s.cizgi, k.konum, 60) "
                         "ORDER BY s.cizgi <-> k.konum LIMIT 1) WHERE k.surum_id = %s AND k.sokak_id IS NULL AND k.sokak_ad IS NULL", (surum,))
        baglanti.commit()
        for tablo in ("sokak", "yer_isareti", "kapi_numarasi"):
            baglanti.execute(f"UPDATE {tablo} SET aktif_mi = FALSE WHERE aktif_mi AND surum_id IS DISTINCT FROM %s", (surum,))
        sayilar = [baglanti.execute(f"SELECT count(*) FROM {t} WHERE aktif_mi").fetchone()[0] for t in ("sokak", "yer_isareti", "kapi_numarasi")]
        baglanti.execute(f"UPDATE adres_surum SET durum_id = {durum('tamam')}, bitis = now(), sokak_adet = %s, yer_adet = %s, kapi_adet = %s, "
                         "kaynak_tarihi = %s::timestamptz WHERE id = %s", (*sayilar, tarih, surum))
        baglanti.commit()
        for tablo in ARAMA_KOLONLARI:
            baglanti.execute(f"TRUNCATE {tablo}")
        baglanti.commit()
        for tablo in ("sokak", "yer_isareti", "kapi_numarasi"):
            baglanti.execute(f"ANALYZE {tablo}")
        baglanti.commit()
        log.info("Adres tamam: sokak=%s yer=%s kapi=%s (surum %s).", *sayilar, surum)
    except Exception as hata:
        baglanti.rollback()
        log.exception("Adres yuklemesi basarisiz")
        baglanti.execute(f"UPDATE adres_surum SET durum_id = {durum('hata')}, bitis = now(), hata_mesaji = %s WHERE id = %s",
                         (str(hata)[:500], surum))
        baglanti.commit()
        raise
