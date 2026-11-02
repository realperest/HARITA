"""Yukleme dogrulamasi ve aylik zamanlama yardimcilari.

Zamanlama: her ayin 1'i 05:00 Turkiye saati (Turkiye kalici UTC+3, yani 02:00 UTC). Yukleyici, son basarili yuklemesi
bu zamanlamadan eskiyse calisir; hizmet o an kapaliysa acilista telafi eder.
Dogrulama: yeni yukleme onceki aktif kayit sayisinin en az %90'ini uretmeli; degilse yukleme hata sayilir ve eski kayitlar
pasiflestirilmez (canli veri korunur).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

EN_AZ_ORAN = float(os.environ.get("VERI_EN_AZ_ORAN", "0.9"))
ZAMANLAMA_GUN = 1
ZAMANLAMA_SAAT_UTC = 2


def aktif_say(baglanti: psycopg.Connection, tablo: str) -> int:
    """Tablodaki aktif kayit sayisi."""
    return baglanti.execute(f"SELECT count(*) FROM {tablo} WHERE aktif_mi").fetchone()[0]


def oran_dogrula(baglanti: psycopg.Connection, tablo: str, surum: int, onceki: int) -> None:
    """Bu yuklemede uretilen kayit sayisi, oncekinin EN_AZ_ORAN'indan azsa hata verir (onceki 0 ise denetlenmez)."""
    yeni = baglanti.execute(f"SELECT count(*) FROM {tablo} WHERE surum_id = %s", (surum,)).fetchone()[0]
    if onceki and yeni < onceki * EN_AZ_ORAN:
        raise RuntimeError(f"{tablo}: yeni yukleme {yeni} kayit uretti, onceki {onceki} (en az %{EN_AZ_ORAN * 100:.0f} beklenir)")


def _ayin_zamani(yil: int, ay: int) -> datetime:
    return datetime(yil, ay, ZAMANLAMA_GUN, ZAMANLAMA_SAAT_UTC, tzinfo=timezone.utc)


def son_zamanlama(simdi: datetime | None = None) -> datetime:
    """Simdiye en yakin gecmis zamanlama aniyi (ayin 1'i 02:00 UTC)."""
    simdi = simdi or datetime.now(timezone.utc)
    bu_ay = _ayin_zamani(simdi.year, simdi.month)
    if simdi >= bu_ay:
        return bu_ay
    onceki = bu_ay - timedelta(days=1)
    return _ayin_zamani(onceki.year, onceki.month)


def sonraki_zamanlama(simdi: datetime | None = None) -> datetime:
    """Simdiden sonraki ilk zamanlama ani."""
    simdi = simdi or datetime.now(timezone.utc)
    son = son_zamanlama(simdi)
    sonraki = son + timedelta(days=32)
    return _ayin_zamani(sonraki.year, sonraki.month)


def esik_sn(simdi: datetime | None = None) -> float:
    """Son zamanlama aninin kac saniye once oldugu; 'bitis < now() - esik' olan (zamanlamadan once biten) yukleme yeniden yapilir."""
    simdi = simdi or datetime.now(timezone.utc)
    return max(1.0, (simdi - son_zamanlama(simdi)).total_seconds())


def bekleme_sn(azami_sn: float, simdi: datetime | None = None) -> float:
    """Bir sonraki kontrole kadar beklenecek sure: azami_sn ile sonraki zamanlamaya (+30 sn) kalan sureden kucuk olan."""
    simdi = simdi or datetime.now(timezone.utc)
    return max(30.0, min(azami_sn, (sonraki_zamanlama(simdi) - simdi).total_seconds() + 30))
