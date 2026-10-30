"""Canlilik ve hazirlik uclari (anahtar istemez)."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import cache
from app.db import havuz
from app.services import photon, valhalla

log = logging.getLogger(__name__)
router = APIRouter(tags=["saglik"])


@router.get("/saglik")
async def canlilik() -> dict:
    """Surec ayakta mi."""
    return {"durum": "ok"}


@router.get("/saglik/hazir")
async def hazirlik() -> JSONResponse:
    """Veritabani, Redis ve alt servislerin durumu. Alt servis yoksa 503 doner ama gateway calismaya devam eder."""
    durum = {"veritabani": False, "redis": False, "rota": await valhalla.hazir_mi(), "arama": await photon.hazir_mi()}
    try:
        async with havuz().acquire() as baglanti:
            durum["veritabani"] = await baglanti.fetchval("SELECT 1") == 1
    except Exception:
        log.exception("Veritabani hazirlik kontrolu basarisiz")
    try:
        durum["redis"] = bool(await cache.istemci().ping())
    except Exception:
        log.exception("Redis hazirlik kontrolu basarisiz")
    cekirdek = durum["veritabani"] and durum["redis"]
    return JSONResponse(status_code=200 if cekirdek and durum["rota"] and durum["arama"] else 503, content=durum)
