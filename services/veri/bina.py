"""Site / bina yukleyicisi: OSM Turkiye verisinden adli site (landuse) ve bina poligonlari.

Iki asamali ayiklama bellek ve disk icin: once adli yollar (name), sonra bunlardan bina / landuse. Kapali yol poligona cevrilir
(iliski tabanli cok parcali poligonlar atlanir). Mahalleye ve en yakin sokaga (80 m) mekansal baglanir.
Kaynak OpenStreetMap (c) OpenStreetMap katkicilari, ODbL.
"""

import logging
import subprocess
import time
from pathlib import Path

import osmium
import psycopg

from adres import MAHALLE_HAZIRLA, MAHALLE_TEMIZLE

log = logging.getLogger("bina")

BINA_KULLANIMLARI = {"apartments", "residential", "commercial", "office", "retail", "industrial", "dormitory", "hotel"}
SITE_KULLANIMLARI = {"residential", "commercial", "industrial", "retail"}
TOPLU_BOYUT = 20_000
KOLONLAR = "kaynak_anahtari, tur_id, kullanim_id, ad, ad_arama, wkb"


class Toplayici(osmium.SimpleHandler):
    """Adli, kapali, bina veya site yollarini toplar ve COPY ile yazar."""

    def __init__(self, baglanti: psycopg.Connection, ad_katla, kullanimlar: dict[str, int]) -> None:
        super().__init__()
        self.baglanti = baglanti
        self.ad_katla = ad_katla
        self.kullanimlar = kullanimlar
        self.tampon: list[tuple] = []
        self.sayac = 0
        self._wkb = osmium.geom.WKBFactory()

    def bosalt(self) -> None:
        """Tamponu COPY ile yazar ve onaylar."""
        if not self.tampon:
            return
        with self.baglanti.cursor() as imlec, imlec.copy(f"COPY gecici_bina ({KOLONLAR}) FROM STDIN") as kopya:
            for satir in self.tampon:
                kopya.write_row(satir)
        self.baglanti.commit()
        self.tampon = []

    def way(self, w) -> None:  # noqa: ANN001
        t = w.tags
        ad = t.get("name")
        if not ad or not w.is_closed() or len(w.nodes) < 4:
            return
        bina, arazi = t.get("building"), t.get("landuse")
        if bina:
            tur, kullanim = 2, self.kullanimlar.get(bina if bina in BINA_KULLANIMLARI else "")
        elif arazi in SITE_KULLANIMLARI:
            tur, kullanim = 1, self.kullanimlar.get(arazi)
        else:
            return
        try:
            wkb = self._wkb.create_linestring(w)
        except RuntimeError:  # konumu eksik yol atlanir
            return
        self.tampon.append((f"osm:way:{w.id}", tur, kullanim, ad[:200], self.ad_katla(ad)[:200], wkb))
        self.sayac += 1
        if len(self.tampon) >= TOPLU_BOYUT:
            self.bosalt()


def ayikla(kaynak: Path, dizin: Path) -> Path:
    """Iki asama: adli yollar, sonra bunlardan bina / site."""
    adli = dizin / "adli.osm.pbf"
    hedef = dizin / "bina.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(kaynak), "w/name", "-o", str(adli), "--overwrite"], check=True)
    subprocess.run(["osmium", "tags-filter", str(adli), "w/building", "w/landuse=residential,commercial,industrial,retail",
                    "-o", str(hedef), "--overwrite"], check=True)
    adli.unlink(missing_ok=True)
    return hedef


ISLEM_SQL = [
    "UPDATE gecici_bina SET geom = ST_SetSRID(ST_GeomFromWKB(decode(wkb, 'hex')), 4326), wkb = NULL",
    "DELETE FROM gecici_bina WHERE geom IS NULL OR NOT ST_IsClosed(geom) OR ST_NPoints(geom) < 4",
    """INSERT INTO bina (tur_id, kullanim_id, kaynak_anahtari, ad, ad_arama, sinir, merkez, mahalle_id, surum_id, aktif_mi)
       SELECT g.tur_id, g.kullanim_id, g.kaynak_anahtari, g.ad, g.ad_arama, g.poligon::geography, g.merkez::geography,
              (SELECT m.id FROM gecici_mahalle m WHERE ST_Covers(m.g, g.merkez::geometry) LIMIT 1), %(surum)s, TRUE
         FROM (SELECT *, ST_MakePolygon(geom) AS poligon, ST_PointOnSurface(ST_MakePolygon(geom)) AS merkez
                 FROM gecici_bina WHERE ST_IsValid(ST_MakePolygon(geom))) g
       ON CONFLICT (kaynak_anahtari) DO UPDATE SET tur_id = EXCLUDED.tur_id, kullanim_id = EXCLUDED.kullanim_id, ad = EXCLUDED.ad,
            ad_arama = EXCLUDED.ad_arama, sinir = EXCLUDED.sinir, merkez = EXCLUDED.merkez, mahalle_id = EXCLUDED.mahalle_id,
            sokak_id = NULL, surum_id = EXCLUDED.surum_id, aktif_mi = TRUE""",
    """UPDATE bina b SET sokak_id = (SELECT s.id FROM sokak s WHERE s.aktif_mi AND ST_DWithin(s.cizgi, b.merkez, 80)
                                    ORDER BY s.cizgi <-> b.merkez LIMIT 1) WHERE b.surum_id = %(surum)s""",
]


def tablo_bekle(baglanti: psycopg.Connection) -> None:
    """Gateway bina semasini kurana kadar bekler."""
    for _ in range(180):
        baglanti.rollback()
        if baglanti.execute("SELECT to_regclass('bina') IS NOT NULL").fetchone()[0]:
            return
        log.info("Bina semasi bekleniyor (gateway tablolari kurmali)...")
        time.sleep(10)
    raise RuntimeError("bina tablosu olusmadi")


def gerekli_mi(baglanti: psycopg.Connection, guncelleme_gun: int, zorla: bool) -> bool:
    """Son basarili bina yuklemesi yoksa veya guncelleme_gun'den eskiyse True."""
    if zorla:
        return True
    son = baglanti.execute(
        """SELECT bitis < now() - make_interval(days => %s) FROM bina_surum s JOIN tnm_islem_durumu d ON d.id = s.durum_id
            WHERE d.kod = 'tamam' ORDER BY s.bitis DESC LIMIT 1""", (guncelleme_gun,)).fetchone()
    return son is None or bool(son[0])


def calistir(baglanti: psycopg.Connection, indir, kaynak_tarihi, ad_katla, veri_dizini: Path) -> None:
    """Bir tam bina / site yukleme calismasi."""
    durum = lambda kod: f"(SELECT id FROM tnm_islem_durumu WHERE kod = '{kod}')"  # noqa: E731
    baglanti.execute(f"UPDATE bina_surum SET durum_id = {durum('hata')}, hata_mesaji = 'Yarida kaldi', bitis = now() "
                     f"WHERE durum_id = {durum('calisiyor')}")
    surum = baglanti.execute(f"INSERT INTO bina_surum (durum_id) VALUES ({durum('calisiyor')}) RETURNING id").fetchone()[0]
    baglanti.commit()
    try:
        ham = indir()
        ayiklanmis = ham  # on suzme bellek sinirini asiyordu; dosya dogrudan okunur
        tarih = kaynak_tarihi(ham)
        kullanimlar = dict(baglanti.execute("SELECT kod, id FROM tnm_bina_kullanimi").fetchall())
        baglanti.execute("CREATE UNLOGGED TABLE IF NOT EXISTS gecici_bina (kaynak_anahtari text, tur_id smallint, kullanim_id smallint, "
                         "ad text, ad_arama text, wkb text, geom geometry(LineString, 4326))")
        baglanti.execute("TRUNCATE gecici_bina")
        baglanti.commit()
        toplayici = Toplayici(baglanti, ad_katla, kullanimlar)
        indeks = veri_dizini / "bina_dugum.idx"
        try:
            toplayici.apply_file(str(ayiklanmis), locations=True, idx=f"sparse_file_array,{indeks}")
        finally:
            indeks.unlink(missing_ok=True)
        toplayici.bosalt()
        log.info("Okuma bitti: %s adli bina / site. Esleme basliyor...", toplayici.sayac)
        for sorgu in MAHALLE_HAZIRLA:
            baglanti.execute(sorgu)
        baglanti.commit()
        for sorgu in ISLEM_SQL:
            baglanti.execute(sorgu, {"surum": surum})
            baglanti.commit()
        baglanti.execute("UPDATE bina SET aktif_mi = FALSE WHERE aktif_mi AND surum_id IS DISTINCT FROM %s", (surum,))
        adet = baglanti.execute("SELECT count(*) FROM bina WHERE aktif_mi").fetchone()[0]
        baglanti.execute(f"UPDATE bina_surum SET durum_id = {durum('tamam')}, bitis = now(), adet = %s, kaynak_tarihi = %s::timestamptz WHERE id = %s",
                         (adet, tarih, surum))
        baglanti.execute("TRUNCATE gecici_bina")
        for sorgu in MAHALLE_TEMIZLE:
            baglanti.execute(sorgu)
        baglanti.commit()
        baglanti.execute("ANALYZE bina")
        baglanti.commit()
        log.info("Bina tamam: %s adli bina / site (surum %s).", adet, surum)
    except Exception as hata:
        baglanti.rollback()
        log.exception("Bina yuklemesi basarisiz")
        baglanti.execute(f"UPDATE bina_surum SET durum_id = {durum('hata')}, bitis = now(), hata_mesaji = %s WHERE id = %s", (str(hata)[:500], surum))
        baglanti.commit()
        raise
