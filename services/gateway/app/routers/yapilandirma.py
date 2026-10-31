"""Istemcinin kendini yapilandirmasi icin karo / yazi tipi / simge adresleri ve cevrimdisi il paketleri."""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app import cache
from app.config import ayarlar
from app.security import yetki
from app.services.http import istemci

log = logging.getLogger(__name__)
PAKET_ONBELLEK_SN = 600

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


@router.get("/cevrimdisi/paketler")
async def cevrimdisi_paketler(_proje: dict = Depends(yetki("yapilandirma"))) -> dict:
    """Indirilebilir il paketleri (PMTiles, internet yokken harita): kod, ad, kutu, boyut, tarih, adres; varlik: yazi tipi + simge
    arsivi. Uygulama dosyayi indirip MapLibre'de pmtiles:// ile yerelden acar. Paketler ana karo dosyasi yenilenince yenilenir."""
    r = cache.istemci()
    ham = await r.get("cevrimdisi:liste:json")
    if ham is None:
        try:
            yanit = await istemci().get(f"{ayarlar.KARO_ICERI_ADRESI}/paket/liste.json", timeout=5.0)
        except httpx.HTTPError as hata:
            log.error("Paket listesi alinamadi: %s", type(hata).__name__)
            raise HTTPException(status_code=502, detail="Karo servisi su an yanit vermiyor.") from hata
        if yanit.status_code == 404:
            raise HTTPException(status_code=503, detail="Cevrimdisi paketler henuz hazirlaniyor.")
        if yanit.status_code != 200:
            log.error("Paket listesi %s dondu", yanit.status_code)
            raise HTTPException(status_code=502, detail="Karo servisi su an yanit vermiyor.")
        ham = yanit.text
        await r.set("cevrimdisi:liste:json", ham, ex=PAKET_ONBELLEK_SN)
    veri = json.loads(ham)
    kok = ayarlar.KARO_ADRESI.rstrip("/")
    return {
        "maks_yakinlastirma": veri.get("maks_yakinlastirma"),
        "varlik": f"{kok}/paket/{veri.get('varlik', 'varlik.tar.gz')}",
        "paketler": [{**p, "adres": f"{kok}/paket/{p['dosya']}"} for p in veri.get("paketler", [])],
        "atif": "© OpenStreetMap katkıcıları, Protomaps",
    }
