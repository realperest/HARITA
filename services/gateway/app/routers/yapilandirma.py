"""Istemcinin kendini yapilandirmasi icin karo / yazi tipi / simge adresleri."""

from fastapi import APIRouter, Depends

from app.config import ayarlar
from app.security import yetki

router = APIRouter(prefix="/v1", tags=["yapilandirma"])


@router.get("/yapilandirma")
async def yapilandirma(proje: dict = Depends(yetki("yapilandirma"))) -> dict:
    """Karo adresi sablonu, yazi tipi ve simge adresleri; istemci harita stilini bunlarla kurar."""
    kok = ayarlar.KARO_ADRESI.rstrip("/")
    return {
        "proje": proje["ad"],
        "karo": {
            "adres": f"{kok}/tiles/{ayarlar.KARO_ADI}/{{z}}/{{x}}/{{y}}.mvt",
            "maksYakinlastirma": ayarlar.KARO_MAKS_YAKINLASTIRMA,
        },
        "yaziTipleri": f"{kok}/assets/fonts/{{fontstack}}/{{range}}.pbf",
        "simgeler": f"{kok}/assets/sprites/v4",
        "merkez": [35.0, 39.0],
        "sinirlar": [25.6, 35.8, 44.9, 42.2],
        "atif": "© OpenStreetMap katkıcıları, Protomaps",
    }
