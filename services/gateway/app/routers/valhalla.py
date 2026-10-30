"""Valhalla'nin tum API'sine tam erisim (izokron, harita eslestirme, optimize rota, konum bulma, genisleme vb.).

Govde Valhalla'ya aynen iletilir; gateway yalniz anahtar, izin, kota ve boyut siniri uygular.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.config import ayarlar
from app.security import yetki
from app.services.http import istemci

log = logging.getLogger(__name__)
router = APIRouter(prefix="/valhalla", tags=["valhalla"])

UCLAR = {"route", "optimized_route", "sources_to_targets", "isochrone", "trace_route", "trace_attributes", "locate", "expansion",
         "status", "centroid", "height"}
MAKS_GOVDE_BAYT = 2_000_000


@router.api_route("/{uc}", methods=["GET", "POST"], include_in_schema=False)
async def gecir(uc: str, istek: Request, _proje: dict = Depends(yetki("valhalla"))) -> Response:
    """Valhalla ucuna aynen iletir. GET icin ?json={...} (Valhalla'nin kendi bicimi), POST icin JSON govde."""
    if uc not in UCLAR:
        raise HTTPException(status_code=404, detail="Bilinmeyen Valhalla ucu.")
    if istek.method == "POST":
        govde = await istek.body()
        if len(govde) > MAKS_GOVDE_BAYT:
            raise HTTPException(status_code=413, detail="Istek govdesi cok buyuk.")
    else:
        govde = (istek.query_params.get("json") or "{}").encode("utf-8")
    try:
        if uc == "status":
            yanit = await istemci().get(f"{ayarlar.ROTA_ADRESI}/status")
        else:
            yanit = await istemci().post(f"{ayarlar.ROTA_ADRESI}/{uc}", content=govde, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as hata:
        log.error("Valhalla gecisi basarisiz (%s): %s", uc, type(hata).__name__)
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
    return Response(content=yanit.content, status_code=yanit.status_code, media_type="application/json")
