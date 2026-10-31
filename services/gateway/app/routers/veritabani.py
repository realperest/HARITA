"""Veritabani araci uclari (yalniz yonetim anahtariyla): tablo listesi, yapi, veri ve salt okunur SQL."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.crud import veritabani as vt_crud
from app.schemas.veritabani import SqlIstegi
from app.security import yonetim_kapisi

log = logging.getLogger(__name__)
router = APIRouter(prefix="/yonetim/veritabani", tags=["veritabani"], dependencies=[Depends(yonetim_kapisi)])


def _hata(hata: vt_crud.VeritabaniHatasi) -> HTTPException:
    """Gecersiz istegi 422 olarak doner."""
    return HTTPException(status_code=422, detail=str(hata))


@router.get("/ozet")
async def ozet() -> dict:
    """Motor surumu, veritabani boyutu, tablo sayisi ve toplam satir."""
    return await vt_crud.ozet()


@router.get("/tablolar")
async def tablolar() -> list[dict]:
    """Tablo ve gorunum listesi (satir sayisi ve boyut ile)."""
    return await vt_crud.tablolar()


@router.get("/tablo/{tablo}/yapi")
async def yapi(tablo: str) -> dict:
    """Tablonun kolonlari (tip, birincil / yabanci anahtar) ve dizinleri."""
    try:
        return await vt_crud.yapi(tablo)
    except vt_crud.VeritabaniHatasi as hata:
        raise _hata(hata) from hata


@router.get("/tablo/{tablo}/veri")
async def veri(tablo: str, sayfa: int = Query(default=1, ge=1, le=100000), boyut: int = Query(default=50, ge=1, le=500),
               ara: str | None = Query(default=None, max_length=100), kolon: str | None = Query(default=None, max_length=80),
               islem: Literal["=", "<>", ">", "<", ">=", "<=", "icerir", "bos", "dolu"] = "icerir",
               deger: str | None = Query(default=None, max_length=200), sirala: str | None = Query(default=None, max_length=80),
               yon: Literal["artan", "azalan"] = "artan") -> dict:
    """Sayfalanmis tablo verisi (arama, filtre, siralama)."""
    try:
        return await vt_crud.veri(tablo, sayfa, boyut, ara, kolon, islem, deger, sirala, yon)
    except vt_crud.VeritabaniHatasi as hata:
        raise _hata(hata) from hata


@router.post("/sql")
async def sql(istek: SqlIstegi) -> dict:
    """Salt okunur SQL (tek SELECT / WITH, en fazla 1.000 satir)."""
    try:
        return await vt_crud.sql_calistir(istek.sorgu)
    except vt_crud.VeritabaniHatasi as hata:
        raise _hata(hata) from hata
