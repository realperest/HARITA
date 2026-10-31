"""Yol uyarisi yukleyicisi: OSM Turkiye verisinden hiz kamerasi (highway=speed_camera) ve hiz kesici (traffic_calming) noktalari.

Kucuk bir veri: once osmium ile yalniz bu dugumler ayiklanir, sonra tek seferde yazilir.
Kaynak OpenStreetMap (c) OpenStreetMap katkicilari, ODbL.
"""

import logging
import re
import subprocess
import time
from pathlib import Path

import osmium
import psycopg

from dogrulama import aktif_say, oran_dogrula

log = logging.getLogger("uyari")

KESICI_TURLERI = {"bump", "hump", "table", "cushion", "yes"}
HIZ = re.compile(r"^\s*(\d{2,3})\s*(?:km/h|kmh)?\s*$")
YON = re.compile(r"^\s*(\d{1,3})\s*$")


def hiz_oku(deger: str | None) -> int | None:
    """maxspeed etiketinden km/sa ("50", "50 km/h"); okunamazsa None."""
    m = HIZ.match(deger or "")
    return int(m.group(1)) if m and 5 <= int(m.group(1)) <= 160 else None


def yon_oku(deger: str | None) -> int | None:
    """direction etiketinden derece ("90"); "forward" gibi degerler None."""
    m = YON.match(deger or "")
    return int(m.group(1)) % 360 if m else None


class Toplayici(osmium.SimpleHandler):
    """Hiz kamerasi ve hiz kesici dugumlerini toplar."""

    def __init__(self) -> None:
        super().__init__()
        self.satirlar: list[tuple] = []

    def node(self, n) -> None:  # noqa: ANN001
        t = n.tags
        if t.get("highway") == "speed_camera":
            tur = 1
        elif t.get("traffic_calming") in KESICI_TURLERI:
            tur = 2
        else:
            return
        if not n.location.valid():
            return
        self.satirlar.append((f"osm:node:{n.id}", tur, n.location.lon, n.location.lat, hiz_oku(t.get("maxspeed")),
                              yon_oku(t.get("direction") or t.get("camera:direction"))))


def tablo_bekle(baglanti: psycopg.Connection) -> None:
    """Gateway yol uyari semasini kurana kadar bekler."""
    for _ in range(180):
        baglanti.rollback()
        if baglanti.execute("SELECT to_regclass('yol_uyari') IS NOT NULL").fetchone()[0]:
            return
        log.info("Yol uyari semasi bekleniyor (gateway tablolari kurmali)...")
        time.sleep(10)
    raise RuntimeError("yol_uyari tablosu olusmadi")


def gerekli_mi(baglanti: psycopg.Connection, esik_sn: float, zorla: bool) -> bool:
    """Son basarili yukleme yoksa veya esik_sn'den eskiyse True."""
    if zorla:
        return True
    son = baglanti.execute(
        """SELECT bitis < now() - make_interval(secs => %s) FROM yol_uyari_surum s JOIN tnm_islem_durumu d ON d.id = s.durum_id
            WHERE d.kod = 'tamam' ORDER BY s.bitis DESC LIMIT 1""", (esik_sn,)).fetchone()
    return son is None or bool(son[0])


def calistir(baglanti: psycopg.Connection, indir, kaynak_tarihi, veri_dizini: Path) -> None:
    """Bir tam yol uyarisi yukleme calismasi."""
    durum = lambda kod: f"(SELECT id FROM tnm_islem_durumu WHERE kod = '{kod}')"  # noqa: E731
    baglanti.execute(f"UPDATE yol_uyari_surum SET durum_id = {durum('hata')}, hata_mesaji = 'Yarida kaldi', bitis = now() "
                     f"WHERE durum_id = {durum('calisiyor')}")
    surum = baglanti.execute(f"INSERT INTO yol_uyari_surum (durum_id) VALUES ({durum('calisiyor')}) RETURNING id").fetchone()[0]
    baglanti.commit()
    hedef = veri_dizini / "uyari.osm.pbf"
    onceki = aktif_say(baglanti, "yol_uyari")
    try:
        ham = indir()
        tarih = kaynak_tarihi(ham)
        subprocess.run(["osmium", "tags-filter", str(ham), "n/highway=speed_camera", "n/traffic_calming", "-o", str(hedef), "--overwrite"],
                       check=True)
        toplayici = Toplayici()
        toplayici.apply_file(str(hedef))
        with baglanti.cursor() as imlec:
            imlec.executemany(
                """INSERT INTO yol_uyari (kaynak_anahtari, tur_id, konum, hiz_siniri, yon, surum_id, aktif_mi)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, TRUE)
                   ON CONFLICT (kaynak_anahtari) DO UPDATE SET tur_id = EXCLUDED.tur_id, konum = EXCLUDED.konum,
                        hiz_siniri = EXCLUDED.hiz_siniri, yon = EXCLUDED.yon, surum_id = EXCLUDED.surum_id, aktif_mi = TRUE""",
                [(*s, surum) for s in toplayici.satirlar])
        oran_dogrula(baglanti, "yol_uyari", surum, onceki)
        baglanti.execute("UPDATE yol_uyari SET aktif_mi = FALSE WHERE aktif_mi AND surum_id IS DISTINCT FROM %s", (surum,))
        adet = baglanti.execute("SELECT count(*) FROM yol_uyari WHERE aktif_mi").fetchone()[0]
        baglanti.execute(f"UPDATE yol_uyari_surum SET durum_id = {durum('tamam')}, bitis = now(), adet = %s, kaynak_tarihi = %s::timestamptz "
                         "WHERE id = %s", (adet, tarih, surum))
        baglanti.commit()
        log.info("Yol uyarilari tamam: %s nokta (surum %s).", adet, surum)
    except Exception as hata:
        baglanti.rollback()
        log.exception("Yol uyarisi yuklemesi basarisiz")
        baglanti.execute(f"UPDATE yol_uyari_surum SET durum_id = {durum('hata')}, bitis = now(), hata_mesaji = %s WHERE id = %s",
                         (str(hata)[:500], surum))
        baglanti.commit()
        raise
    finally:
        hedef.unlink(missing_ok=True)
