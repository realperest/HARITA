"""Proje ve anahtar yonetimi (yalniz yonetim anahtariyla)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.crud import proje as proje_crud
from app.schemas.harita import ProjeGuncelle, ProjeOlustur
from app.security import onbellegi_temizle, ozet_al, yeni_anahtar, yonetim_kapisi

log = logging.getLogger(__name__)
router = APIRouter(prefix="/yonetim", tags=["yonetim"], dependencies=[Depends(yonetim_kapisi)])


@router.post("/projeler", status_code=201)
async def proje_olustur(istek: ProjeOlustur) -> dict:
    """Yeni proje + ilk anahtar. Anahtar yalniz bu yanitta gorunur; kaybolursa yenisi uretilir."""
    anahtar, ozet, on_ek = yeni_anahtar()
    try:
        proje_id = await proje_crud.olustur(istek.ad, istek.aciklama, istek.dakika_limiti, istek.servisler,
                                            istek.kaynaklar, ozet, on_ek)
    except ValueError as hata:
        raise HTTPException(status_code=422, detail="Gecerli servis kodu bulunamadi.") from hata
    except Exception as hata:
        log.exception("Proje olusturulamadi")
        raise HTTPException(status_code=409, detail="Proje olusturulamadi (ad kullanimda olabilir).") from hata
    return {"proje_id": proje_id, "anahtar": anahtar}


@router.get("/projeler")
async def projeleri_listele() -> list[dict]:
    """Tum projeler, izinleri, kaynaklari ve anahtar on ekleri."""
    return await proje_crud.listele()


@router.patch("/projeler/{proje_id}")
async def proje_guncelle(proje_id: int, istek: ProjeGuncelle) -> dict:
    """Proje ayarlarini gunceller (aktiflik, kota, servis izinleri, izinli kaynaklar)."""
    try:
        bulundu = await proje_crud.guncelle(proje_id, istek.aktif, istek.dakika_limiti, istek.servisler, istek.kaynaklar)
    except ValueError as hata:
        raise HTTPException(status_code=422, detail="Gecerli servis kodu bulunamadi.") from hata
    if not bulundu:
        raise HTTPException(status_code=404, detail="Proje bulunamadi.")
    await onbellegi_temizle(await proje_crud.anahtar_ozetleri(proje_id))
    return {"durum": "guncellendi"}


@router.post("/projeler/{proje_id}/anahtarlar", status_code=201)
async def anahtar_ekle(proje_id: int) -> dict:
    """Projeye yeni anahtar uretir (anahtar donusumu icin eskisi sonra iptal edilir)."""
    anahtar, ozet, on_ek = yeni_anahtar()
    if not await proje_crud.anahtar_ekle(proje_id, ozet, on_ek):
        raise HTTPException(status_code=404, detail="Proje bulunamadi.")
    return {"anahtar": anahtar, "on_ek": on_ek}


@router.delete("/projeler/{proje_id}/anahtarlar/{on_ek}")
async def anahtar_iptal(proje_id: int, on_ek: str) -> dict:
    """On eki verilen anahtari kapatir."""
    ozetler = await proje_crud.anahtar_iptal(proje_id, on_ek)
    if not ozetler:
        raise HTTPException(status_code=404, detail="Anahtar bulunamadi.")
    await onbellegi_temizle(ozetler)
    return {"durum": "iptal edildi"}


@router.get("/projeler/{proje_id}/kullanim")
async def kullanim(proje_id: int, gun: int = Query(default=30, ge=1, le=366)) -> list[dict]:
    """Projenin son N gunluk servis bazli kullanimi."""
    return await proje_crud.kullanim(proje_id, gun)
