"""Trafik profili uclari: anonim GPS izi gonderme ve ogrenilmis hizlarla rota suresi tahmini.

Kendi kuryelerinizin / suruculerinizin izleri ne kadar cok gelirse tahmin o kadar iyilesir; veri tum projelerin ortak havuzudur
ama kimlik, cihaz ya da iz saklanmaz (yalniz yol parcasi + haftanin saati basina ortalama hiz).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.routers.yol import UyariIstek, _cizgi
from app.security import yetki
from app.services import trafik, valhalla
from app.services.http import AltServisHatasi, AltServisYok

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/trafik", tags=["trafik"])


class IzNoktasi(BaseModel):
    """GPS olcumu; zaman Unix saniyesi."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    zaman: float = Field(gt=1_500_000_000)


class IzIstek(BaseModel):
    """Bir surusun GPS izi (1-10 sn aralikli olcumler en iyi sonucu verir)."""

    profil: str = Field(default="motosiklet", max_length=20)
    noktalar: list[IzNoktasi] = Field(min_length=5, max_length=5000)

    @field_validator("noktalar")
    @classmethod
    def _sirali(cls, noktalar: list[IzNoktasi]) -> list[IzNoktasi]:
        if any(b.zaman <= a.zaman for a, b in zip(noktalar, noktalar[1:])):
            raise ValueError("Noktalar zamana gore artan sirada olmali.")
        if noktalar[-1].zaman - noktalar[0].zaman > 6 * 3600:
            raise ValueError("Bir iz en fazla 6 saatlik olabilir.")
        return noktalar


@router.post("/iz")
async def iz_gonder(istek: IzIstek, _proje: dict = Depends(yetki("rota"))) -> dict:
    """GPS izinden yol hizlarini ogrenir. Donus: eslenen_kenar, kaydedilen (yol sayisi), haftanin_saati."""
    maliyet = valhalla.maliyet_modeli(istek.profil)
    if maliyet is None:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    try:
        return await trafik.iz_ogren([n.model_dump() for n in istek.noktalar], maliyet)
    except AltServisYok as hata:
        raise HTTPException(status_code=422, detail="Iz yola eslenemedi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata


class SureIstek(UyariIstek):
    """Rota cizgisi (polyline / noktalar), profil ve yola cikis zamani (bos ise simdi)."""

    profil: str = Field(default="motosiklet", max_length=20)
    zaman: datetime | None = None


@router.post("/sure")
async def sure_tahmini(istek: SureIstek, _proje: dict = Depends(yetki("rota"))) -> dict:
    """Ogrenilmis hizlarla rota suresi: valhalla_sure_sn (varsayilan hizlar), tahmini_sure_sn, kapsama (verisi olan yol orani)."""
    maliyet = valhalla.maliyet_modeli(istek.profil)
    if maliyet is None:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    try:
        return await trafik.sure_tahmini(_cizgi(istek), maliyet, istek.zaman)
    except AltServisYok as hata:
        raise HTTPException(status_code=422, detail="Rota yola eslenemedi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
