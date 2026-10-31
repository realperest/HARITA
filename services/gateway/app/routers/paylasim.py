"""Rota paylasim kodu ve GPX disa / ice aktarma uclari.

/v1/paylasim: duraklar + profil kisa bir kodla paylasilir (navigasyon sayfasi ?kod=... ile acar).
/v1/gpx/olustur: rota cizgisi ve duraklardan GPX dosyasi; /v1/gpx/oku: GPX dosyasindan duraklar ve iz.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import ayarlar
from app.crud import paylasim as paylasim_crud
from app.metin import ad_katla
from app.security import yetki
from app.services import gpx, valhalla

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["paylasim"])

MAKS_GPX_BAYT = 5 * 1024 * 1024
PROFILLER = {"araba", "motosiklet", "yaya", "bisiklet", "kamyon", "auto", "motorcycle", "pedestrian", "bicycle", "truck"}
KOD_DESENI = r"^[A-Za-z0-9]{8}$"


class AraNokta(BaseModel):
    """Duraga giderken gecilecek nokta (GPX izini takip icin)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Durak(BaseModel):
    """Rota duragi; ara: oncesinde gecilecek noktalar (istege bagli)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    ad: str | None = Field(default=None, max_length=200)
    ara: list[AraNokta] | None = Field(default=None, max_length=48)


class PaylasimIstek(BaseModel):
    """Paylasilacak rota: duraklar sirayla (ilk durak genelde baslangic degil, gidilecek ilk yerdir)."""

    ad: str | None = Field(default=None, max_length=200)
    profil: str = Field(default="araba", max_length=20)
    duraklar: list[Durak] = Field(min_length=1, max_length=50)
    sure_saat: int = Field(default=72, ge=1, le=720)


@router.post("/paylasim")
async def paylasim_olustur(istek: PaylasimIstek, proje: dict = Depends(yetki("rota"))) -> dict:
    """Paylasim kodu olusturur: {kod, bitis}. Navigasyon baglantisi: <navigasyon adresi>?kod=<kod>."""
    if istek.profil.lower() not in PROFILLER:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    if len(istek.duraklar) + sum(len(d.ara or []) for d in istek.duraklar) > ayarlar.ROTA_MAKS_NOKTA - 1:
        raise HTTPException(status_code=422, detail=f"Duraklar ve ara noktalar toplam {ayarlar.ROTA_MAKS_NOKTA - 1} olabilir.")
    veri = {"ad": istek.ad, "profil": istek.profil.lower(), "duraklar": [d.model_dump(exclude_none=True) for d in istek.duraklar]}
    return await paylasim_crud.olustur(proje["id"], veri, istek.sure_saat)


@router.get("/paylasim/{kod}")
async def paylasim_getir(kod: str = Path(pattern=KOD_DESENI), _proje: dict = Depends(yetki("rota"))) -> dict:
    """Paylasilan rota: {ad, profil, duraklar, kod, bitis, acilma_sayisi}. Suresi dolmus ya da yoksa 404."""
    veri = await paylasim_crud.getir(kod)
    if veri is None:
        raise HTTPException(status_code=404, detail="Paylasim bulunamadi ya da suresi doldu.")
    return veri


@router.delete("/paylasim/{kod}")
async def paylasim_sil(kod: str = Path(pattern=KOD_DESENI), proje: dict = Depends(yetki("rota"))) -> dict:
    """Projenin kendi olusturdugu paylasimi iptal eder."""
    if not await paylasim_crud.sil(proje["id"], kod):
        raise HTTPException(status_code=404, detail="Paylasim bulunamadi.")
    return {"silindi": True}


class GpxIstek(BaseModel):
    """GPX olusturma: rota cizgisi (Valhalla polyline6 ya da [[lat, lon]]) ve / veya duraklar."""

    ad: str | None = Field(default=None, max_length=200)
    polyline: str | None = Field(default=None, max_length=2_000_000)
    hassasiyet: int = Field(default=6, ge=5, le=6)
    noktalar: list[tuple[float, float]] | None = Field(default=None, max_length=gpx.MAKS_NOKTA)
    duraklar: list[Durak] = Field(default_factory=list, max_length=200)


def _dosya_adi(ad: str | None) -> str:
    """Indirme icin guvenli dosya adi."""
    temiz = re.sub(r"[^a-z0-9_-]+", "-", ad_katla(ad or ""))[:60].strip("-")
    return f"{temiz or 'rota'}.gpx"


@router.post("/gpx/olustur")
async def gpx_olustur(istek: GpxIstek, _proje: dict = Depends(yetki("rota"))) -> Response:
    """GPX 1.1 dosyasi (application/gpx+xml): duraklar wpt + rte, cizgi trk olarak."""
    cizgi: list[list[float]] = []
    if istek.polyline:
        try:
            cizgi = valhalla.polyline_coz(istek.polyline, istek.hassasiyet)
        except (IndexError, ValueError) as hata:
            raise HTTPException(status_code=422, detail="Polyline cozulemedi.") from hata
    elif istek.noktalar:
        cizgi = [[lon, lat] for lat, lon in istek.noktalar]
    if not cizgi and not istek.duraklar:
        raise HTTPException(status_code=422, detail="Cizgi ya da durak gerekli.")
    metin = gpx.olustur(istek.ad or "Rota", cizgi, [d.model_dump(exclude={"ara"}) for d in istek.duraklar])
    return Response(content=metin, media_type="application/gpx+xml",
                    headers={"Content-Disposition": f'attachment; filename="{_dosya_adi(istek.ad)}"'})


@router.post("/gpx/oku")
async def gpx_oku(request: Request, iz_takip: bool = Query(default=False), _proje: dict = Depends(yetki("rota"))) -> dict:
    """Istek govdesindeki GPX metnini okur (en fazla 5 MB). duraklar: wpt varsa onlar, yoksa ilk rota, yoksa izin basi ve sonu.
    iz_takip=true ve dosyada iz varsa her durağa izden ara noktalar ("ara": [{lat, lon}]) eklenir; rota bunlardan "through"
    tipiyle gecirilirse navigasyon izin yollarini izler (Valhalla 50 konum siniri icinde)."""
    govde = await request.body()
    if len(govde) > MAKS_GPX_BAYT:
        raise HTTPException(status_code=413, detail="GPX en fazla 5 MB olabilir.")
    try:
        veri = gpx.oku(govde.decode("utf-8-sig"))
    except UnicodeDecodeError as hata:
        raise HTTPException(status_code=422, detail="GPX UTF-8 olmali.") from hata
    except gpx.GpxHatasi as hata:
        raise HTTPException(status_code=422, detail=str(hata)) from hata
    if veri["yol_noktalari"]:
        duraklar = veri["yol_noktalari"]
    elif veri["rotalar"]:
        duraklar = veri["rotalar"][0]
    else:
        iz = veri["izler"][0]
        duraklar = [iz[0], iz[-1]] if len(iz) > 1 else iz
    duraklar = [{k: v for k, v in d.items() if k in ("lat", "lon", "ad")} for d in duraklar[:ayarlar.ROTA_MAKS_NOKTA - 1]]
    if iz_takip and veri["izler"]:
        tum_iz = [n for parca in veri["izler"] for n in parca]
        duraklar = gpx.iz_takip(duraklar, tum_iz, ayarlar.ROTA_MAKS_NOKTA - 1 - len(duraklar))
    return {**veri, "duraklar": duraklar}
