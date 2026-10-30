"""Yerlesim yukleyicisi: OSM Turkiye verisinden il / ilce / mahalle-koy sinirlari ve sehir, kasaba, koy, mezra, semt merkezleri.

Akis: Geofabrik PBF indir -> osmium ile yalniz idari sinir iliskileri ve place dugumlerini ayikla -> pyosmium ile oku ->
PostGIS'e yaz (kaynak_anahtari uzerinden yukle-guncelle) -> ust-alt iliskisini mekansal olarak kur -> kalkanlari pasiflestir.
Kaynak OpenStreetMap (c) OpenStreetMap katkicilari, ODbL.
"""

import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import osmium
import psycopg

log = logging.getLogger("yukle")

DATABASE_URL = os.environ["DATABASE_URL"]
VERI_ADRESI = os.environ.get("VERI_ADRESI", "https://download.geofabrik.de/europe/turkey-latest.osm.pbf")
VERI_DIZINI = Path(os.environ.get("VERI_DIZINI", "/veri"))
GUNCELLEME_GUN = int(os.environ.get("GUNCELLEME_GUN", "30"))
KONTROL_SAAT = float(os.environ.get("KONTROL_SAAT", "6"))
TEK_SEFER = os.environ.get("TEK_SEFER") == "1"          # deneme: bir kez calis ve cik
ZORLA = os.environ.get("ZORLA") == "1"                  # son basarili yuklemeye bakmadan calis

# OSM admin_level -> tnm_yerlesim_turu.id (Turkiye: 4 il, 6 ilce, 8 mahalle / koy). Deneme icin "7:3" gibi degistirilebilir.
ADMIN_SEVIYELERI = {k: int(v) for k, v in (p.split(":") for p in os.environ.get("ADMIN_SEVIYELERI", "4:1,6:2,8:3").split(","))}
# OSM place -> tnm_yerlesim_turu.id
PLACE_TURLERI = {"city": 4, "town": 5, "village": 6, "hamlet": 7, "suburb": 8, "neighbourhood": 8, "quarter": 8}

_KATLAMA = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
                          "Ö": "o", "ö": "o", "Ş": "s", "ş": "s", "Ü": "u", "ü": "u"})


def ad_katla(metin: str) -> str:
    """Arama metni: kucuk harf + ASCII katlama (gateway app/metin.py ile ayni kural)."""
    return " ".join(metin.translate(_KATLAMA).lower().split())


def nufus_oku(etiketler) -> int | None:  # noqa: ANN001
    """population etiketinden tam sayi; okunamazsa None."""
    ham = (etiketler.get("population") or "").replace(".", "").replace(",", "").strip()
    return int(ham) if ham.isdigit() and int(ham) < 2_000_000_000 else None


class Toplayici(osmium.SimpleHandler):
    """Idari sinirlari (area) ve place dugumlerini toplar."""

    def __init__(self) -> None:
        super().__init__()
        self.satirlar: list[tuple] = []
        self.atlanan = 0
        self._wkb = osmium.geom.WKBFactory()

    def node(self, n) -> None:  # noqa: ANN001
        tur = PLACE_TURLERI.get(n.tags.get("place"))
        ad = n.tags.get("name")
        if tur is None or not ad or not n.location.valid():
            return
        self.satirlar.append((f"osm:node:{n.id}", tur, ad, ad_katla(ad), n.location.lon, n.location.lat,
                              nufus_oku(n.tags), None))

    def area(self, a) -> None:  # noqa: ANN001
        if a.from_way() or a.tags.get("boundary") != "administrative":
            return
        tur = ADMIN_SEVIYELERI.get(a.tags.get("admin_level", ""))
        ad = a.tags.get("name")
        if tur is None or not ad:
            return
        try:
            wkb = self._wkb.create_multipolygon(a)
        except Exception:  # geometrisi kurulamayan sinir atlanir ve sayilir; yukleme digerleriyle surer
            self.atlanan += 1
            log.warning("Sinir geometrisi kurulamadi, atlandi: %s", a.orig_id(), exc_info=True)
            return
        self.satirlar.append((f"osm:relation:{a.orig_id()}", tur, ad, ad_katla(ad), None, None, nufus_oku(a.tags), wkb))


def indir() -> Path:
    """PBF dosyasini indirir (7 gunden tazeyse mevcut kullanilir)."""
    VERI_DIZINI.mkdir(parents=True, exist_ok=True)
    hedef = VERI_DIZINI / "kaynak.osm.pbf"
    if hedef.exists() and time.time() - hedef.stat().st_mtime < 7 * 86400:
        log.info("Mevcut PBF kullaniliyor: %s", hedef)
        return hedef
    log.info("PBF indiriliyor: %s", VERI_ADRESI)
    gecici = hedef.with_suffix(".indiriliyor")
    urllib.request.urlretrieve(VERI_ADRESI, gecici)
    gecici.replace(hedef)
    return hedef


def ayikla(kaynak: Path) -> Path:
    """osmium ile yalniz idari sinir iliskilerini ve place dugumlerini (ve bunlarin dayanaklarini) ayiklar."""
    hedef = VERI_DIZINI / "ayiklanmis.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(kaynak), "r/boundary=administrative", "n/place", "-o", str(hedef), "--overwrite"],
                   check=True)
    return hedef


def kaynak_tarihi(pbf: Path) -> str | None:
    """PBF basligindaki son zaman damgasi (yoksa None)."""
    sonuc = subprocess.run(["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", str(pbf)],
                           capture_output=True, text=True, check=False)
    return sonuc.stdout.strip() or None


def oku(pbf: Path) -> Toplayici:
    """Ayiklanmis PBF'yi okur (dugum konumlari disk indeksinde tutulur)."""
    toplayici = Toplayici()
    toplayici.apply_file(str(pbf), locations=True, idx=f"sparse_file_array,{VERI_DIZINI / 'dugum.idx'}")
    return toplayici


YUKLE_SQL = """
WITH g AS (
    SELECT *, CASE WHEN wkb IS NULL THEN NULL
                   ELSE ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(decode(wkb, 'hex')), 4326)), 3)) END AS geom
      FROM yerlesim_gecici)
INSERT INTO yerlesim (tur_id, kaynak_anahtari, ad, ad_arama, merkez, sinir, nufus, surum_id, aktif_mi, guncelleme)
SELECT tur_id, kaynak_anahtari, ad, ad_arama,
       CASE WHEN geom IS NULL THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography ELSE ST_PointOnSurface(geom)::geography END,
       geom::geography, nufus, %(surum)s, TRUE, now()
  FROM g WHERE (geom IS NOT NULL AND NOT ST_IsEmpty(geom)) OR (wkb IS NULL AND lon IS NOT NULL)
ON CONFLICT (kaynak_anahtari) DO UPDATE SET
    tur_id = EXCLUDED.tur_id, ad = EXCLUDED.ad, ad_arama = EXCLUDED.ad_arama, merkez = EXCLUDED.merkez,
    sinir = EXCLUDED.sinir, nufus = EXCLUDED.nufus, surum_id = EXCLUDED.surum_id, aktif_mi = TRUE, guncelleme = now()
"""

# Ust-alt iliskisi: her satir, kendisini iceren bir ust seviyedeki en kucuk sinira baglanir
USTLER_SQL = [
    """UPDATE yerlesim c SET ust_id = (SELECT p.id FROM yerlesim p WHERE p.tur_id = 1 AND p.aktif_mi AND ST_Covers(p.sinir, c.merkez)
                                       ORDER BY ST_Area(p.sinir) LIMIT 1)
        WHERE c.tur_id = 2 AND c.surum_id = %(surum)s""",
    """UPDATE yerlesim c SET ust_id = (SELECT p.id FROM yerlesim p WHERE p.tur_id = 2 AND p.aktif_mi AND ST_Covers(p.sinir, c.merkez)
                                       ORDER BY ST_Area(p.sinir) LIMIT 1)
        WHERE c.tur_id = 3 AND c.surum_id = %(surum)s""",
    """UPDATE yerlesim c SET ust_id = (SELECT p.id FROM yerlesim p WHERE p.tur_id IN (2, 3) AND p.aktif_mi AND ST_Covers(p.sinir, c.merkez)
                                       ORDER BY p.tur_id DESC, ST_Area(p.sinir) LIMIT 1)
        WHERE c.tur_id >= 4 AND c.surum_id = %(surum)s""",
]

# Sinirin merkezi: icindeki ayni adli yerlesim noktasi varsa o (gercek sehir / koy merkezi), yoksa sinirin ic noktasi kalir
MERKEZ_SQL = """
UPDATE yerlesim b SET merkez = s.merkez
  FROM (SELECT DISTINCT ON (b2.id) b2.id, n.merkez
          FROM yerlesim b2 JOIN yerlesim n ON n.tur_id >= 4 AND n.aktif_mi AND n.ad_arama = b2.ad_arama AND ST_Covers(b2.sinir, n.merkez)
         WHERE b2.tur_id IN (1, 2, 3) AND b2.surum_id = %(surum)s
         ORDER BY b2.id, n.tur_id) s
 WHERE s.id = b.id
"""


def tablo_bekle(baglanti: psycopg.Connection) -> None:
    """Gateway semayi kurana kadar bekler (en fazla ~30 dk)."""
    for _ in range(180):
        if baglanti.execute("SELECT to_regclass('yerlesim') IS NOT NULL").fetchone()[0]:
            return
        log.info("Sema bekleniyor (gateway tablolari kurmali)...")
        time.sleep(10)
    raise RuntimeError("yerlesim tablosu olusmadi")


def calisma_gerekli(baglanti: psycopg.Connection) -> bool:
    """Son basarili yukleme yoksa veya GUNCELLEME_GUN'den eskiyse True."""
    if ZORLA:
        return True
    son = baglanti.execute(
        """SELECT bitis < now() - make_interval(days => %s) FROM yerlesim_surum s JOIN tnm_islem_durumu d ON d.id = s.durum_id
            WHERE d.kod = 'tamam' ORDER BY s.bitis DESC LIMIT 1""", (GUNCELLEME_GUN,)).fetchone()
    return son is None or bool(son[0])


def yukle(baglanti: psycopg.Connection) -> None:
    """Bir tam yukleme calismasi."""
    # Yarida kalmis (calisiyor) kayitlar hataya cekilir
    baglanti.execute("UPDATE yerlesim_surum SET durum_id = (SELECT id FROM tnm_islem_durumu WHERE kod = 'hata'), "
                     "hata_mesaji = 'Yarida kaldi', bitis = now() WHERE durum_id = (SELECT id FROM tnm_islem_durumu WHERE kod = 'calisiyor')")
    surum = baglanti.execute("INSERT INTO yerlesim_surum (durum_id) VALUES ((SELECT id FROM tnm_islem_durumu WHERE kod = 'calisiyor')) "
                             "RETURNING id").fetchone()[0]
    baglanti.commit()
    try:
        ham = indir()
        ayiklanmis = ayikla(ham)
        tarih = kaynak_tarihi(ham)
        toplayici = oku(ayiklanmis)
        log.info("Okundu: %s satir, %s sinir atlandi", len(toplayici.satirlar), toplayici.atlanan)

        baglanti.execute("CREATE TEMP TABLE IF NOT EXISTS yerlesim_gecici (kaynak_anahtari text, tur_id smallint, ad text, ad_arama text, "
                         "lon float8, lat float8, nufus int, wkb text)")
        baglanti.execute("TRUNCATE yerlesim_gecici")
        with baglanti.cursor() as imlec, imlec.copy("COPY yerlesim_gecici FROM STDIN") as kopya:
            for k, tur, ad, ad_arama, lon, lat, nufus, wkb in toplayici.satirlar:
                kopya.write_row((k, tur, ad, ad_arama, lon, lat, nufus, wkb))
        baglanti.execute(YUKLE_SQL, {"surum": surum})
        baglanti.commit()
        log.info("Yuklendi, ust-alt iliskisi kuruluyor...")
        for sorgu in USTLER_SQL:
            baglanti.execute(sorgu, {"surum": surum})
            baglanti.commit()
        baglanti.execute(MERKEZ_SQL, {"surum": surum})
        baglanti.execute("UPDATE yerlesim SET aktif_mi = FALSE, guncelleme = now() WHERE aktif_mi AND surum_id IS DISTINCT FROM %(surum)s",
                         {"surum": surum})
        adet = baglanti.execute("SELECT count(*) FROM yerlesim WHERE aktif_mi").fetchone()[0]
        baglanti.execute("UPDATE yerlesim_surum SET durum_id = (SELECT id FROM tnm_islem_durumu WHERE kod = 'tamam'), bitis = now(), "
                         "adet = %s, kaynak_tarihi = %s::timestamptz WHERE id = %s", (adet, tarih, surum))
        baglanti.commit()
        baglanti.execute("ANALYZE yerlesim")
        baglanti.commit()
        log.info("Tamam: %s aktif yerlesim (surum %s).", adet, surum)
    except Exception as hata:
        baglanti.rollback()
        log.exception("Yukleme basarisiz")
        baglanti.execute("UPDATE yerlesim_surum SET durum_id = (SELECT id FROM tnm_islem_durumu WHERE kod = 'hata'), bitis = now(), "
                         "hata_mesaji = %s WHERE id = %s", (str(hata)[:500], surum))
        baglanti.commit()
        raise


def main() -> None:
    """Sonsuz dongu: gerektiginde yukle, sonra bekle."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            with psycopg.connect(DATABASE_URL) as baglanti:
                tablo_bekle(baglanti)
                if calisma_gerekli(baglanti):
                    yukle(baglanti)
                else:
                    log.info("Veri guncel, yukleme gerekmiyor.")
        except Exception:
            log.exception("Yukleyici dongusunde hata; bir sonraki kontrolde yeniden denenecek")
        if TEK_SEFER:
            return
        time.sleep(KONTROL_SAAT * 3600)


if __name__ == "__main__":
    main()
