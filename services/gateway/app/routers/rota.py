"""Kendi bicimimizdeki rota ve matris uclari."""

from fastapi import APIRouter, Depends, HTTPException

from app.config import ayarlar
from app.schemas.harita import MatrisIstegi, MatrisYaniti, RotaIstegi, RotaYaniti
from app.security import yetki
from app.services import valhalla
from app.services.http import AltServisHatasi, AltServisYok

router = APIRouter(prefix="/v1", tags=["rota"])


@router.post("/rota", response_model=RotaYaniti)
async def rota(istek: RotaIstegi, _proje: dict = Depends(yetki("rota"))) -> RotaYaniti:
    """Noktalar arasi rota: sure (sn), mesafe (m) ve istenirse GeoJSON cizgi."""
    if len(istek.noktalar) > ayarlar.ROTA_MAKS_NOKTA:
        raise HTTPException(status_code=422, detail=f"En fazla {ayarlar.ROTA_MAKS_NOKTA} nokta verilebilir.")
    try:
        veri = await valhalla.rota(istek.noktalar, valhalla.maliyet_modeli(istek.profil) or "auto")
    except AltServisYok as hata:
        raise HTTPException(status_code=404, detail="Bu noktalar arasinda rota bulunamadi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
    ilk = veri["routes"][0]
    return RotaYaniti(
        sure_sn=float(ilk["duration"]),
        mesafe_m=float(ilk["distance"]),
        geometri=valhalla.geojson_geometri(ilk) if istek.geometri else None,
    )


@router.post("/matris", response_model=MatrisYaniti)
async def matris(istek: MatrisIstegi, _proje: dict = Depends(yetki("matris"))) -> MatrisYaniti:
    """Kaynaklardan hedeflere sure ve mesafe matrisi."""
    if len(istek.kaynaklar) > ayarlar.MATRIS_MAKS_NOKTA or len(istek.hedefler) > ayarlar.MATRIS_MAKS_NOKTA:
        raise HTTPException(status_code=422, detail=f"En fazla {ayarlar.MATRIS_MAKS_NOKTA} kaynak ve hedef verilebilir.")
    try:
        sonuc = await valhalla.matris(istek.kaynaklar, istek.hedefler, valhalla.maliyet_modeli(istek.profil) or "auto")
    except AltServisYok as hata:
        raise HTTPException(status_code=404, detail="Matris hesaplanamadi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
    return MatrisYaniti(**sonuc)
