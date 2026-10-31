"""Canli konum ve bolge olaylari: WebSocket yayini ve REST uclari.

WebSocket /v1/canli/ws (tarayici anahtari baslikta gonderemedigi icin ilk mesajla giris yapilir):
  istemci -> {"tip": "giris", "anahtar": "...", "kanal": "kuryeler", "dinle": true}
  sunucu  -> {"tip": "hazir", "kanal": ..., "konumlar": [son konumlar]}  (hata: {"tip": "hata", "mesaj"} ve kapanis)
  istemci -> {"tip": "konum", "id": "kurye-5", "lat": .., "lon": .., "hiz": m/sn, "yon": derece, "dogruluk": m}
  sunucu  -> kanala gelen her olay: {"tip": "konum", ...} ve {"tip": "bolge", "olay": "giris" | "cikis", "id", "bolge", "bolge_ad"}
  Kalp atisi: sunucu 10 sn'de bir {"tip": "ping"} gonderir; istemci {"tip": "pong"} (ya da herhangi bir mesaj) ile yanitlar.
  35 sn mesaj gelmezse baglanti kapanir; istemci yeniden baglanip tekrar giris yapar.
"""

import asyncio
import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError, model_validator

from app import cache
from app.security import anahtar_dogrula, yetki
from app.services import canli

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/canli", tags=["canli"])

KANAL_DESENI = r"^[A-Za-z0-9_-]{1,64}$"
GIRIS_SURESI_SN = 10
KALP_ATISI_SN = 10
SESSIZLIK_SINIRI_SN = 35
SANIYEDE_EN_FAZLA = 5
MAKS_BOLGE = 500


class Konum(BaseModel):
    """Cihaz konumu; id kurye / arac / cihaz kimligidir (kisisel veri yerine takma kimlik onerilir)."""

    id: str = Field(min_length=1, max_length=64)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    hiz: float | None = Field(default=None, ge=0, le=100)
    yon: float | None = Field(default=None, ge=0, le=360)
    dogruluk: float | None = Field(default=None, ge=0, le=10000)
    zaman: float | None = None
    veri: dict | None = None


class Bolge(BaseModel):
    """Daire (merkez + yaricap_m) ya da poligon ([[lat, lon], ...] en az 3 nokta)."""

    id: str = Field(min_length=1, max_length=64)
    ad: str | None = Field(default=None, max_length=200)
    merkez: dict[str, float] | None = None
    yaricap_m: float | None = Field(default=None, gt=0, le=100_000)
    poligon: list[tuple[float, float]] | None = Field(default=None, min_length=3, max_length=2000)

    @model_validator(mode="after")
    def _tur(self) -> "Bolge":
        daire = self.merkez is not None and self.yaricap_m is not None
        if daire == (self.poligon is not None):
            raise ValueError("Bolge ya daire (merkez + yaricap_m) ya da poligon olmali.")
        if daire and not {"lat", "lon"} <= set(self.merkez):
            raise ValueError("merkez {lat, lon} olmali.")
        return self


def _kanal_dogrula(kanal: str) -> str:
    """Kanal adi deseni."""
    if not re.fullmatch(KANAL_DESENI, kanal or ""):
        raise HTTPException(status_code=422, detail="Kanal adi gecersiz (harf, rakam, - ve _; en fazla 64).")
    return kanal


@router.get("/{kanal}/konumlar")
async def konumlar(kanal: str = Path(pattern=KANAL_DESENI), proje: dict = Depends(yetki("canli"))) -> list[dict]:
    """Kanaldaki cihazlarin son konumlari (son 1 saat)."""
    return await canli.son_konumlar(proje["id"], kanal)


@router.post("/{kanal}/konum")
async def konum_gonder(konum: Konum, kanal: str = Path(pattern=KANAL_DESENI), proje: dict = Depends(yetki("canli"))) -> dict:
    """Sunucudan konum yayini (WebSocket kullanmayan arka uclar icin). Donus: yayinlanan olaylar (bolge giris / cikis dahil)."""
    return {"olaylar": await canli.konum_isle(proje["id"], kanal, konum.model_dump(exclude_none=True))}


@router.get("/{kanal}/bolgeler")
async def bolgeleri_getir(kanal: str = Path(pattern=KANAL_DESENI), proje: dict = Depends(yetki("canli"))) -> list[dict]:
    """Kanalin bolgeleri."""
    return await canli.bolgeler(proje["id"], kanal, tazele=True)


@router.put("/{kanal}/bolgeler")
async def bolgeleri_yaz(liste: list[Bolge], kanal: str = Path(pattern=KANAL_DESENI), proje: dict = Depends(yetki("canli"))) -> dict:
    """Kanalin bolgelerini verilen listeyle degistirir (en fazla 500; bos liste hepsini siler)."""
    if len(liste) > MAKS_BOLGE:
        raise HTTPException(status_code=422, detail=f"En fazla {MAKS_BOLGE} bolge tanimlanabilir.")
    if len({b.id for b in liste}) != len(liste):
        raise HTTPException(status_code=422, detail="Bolge kimlikleri tekil olmali.")
    adet = await canli.bolgeleri_yaz(proje["id"], kanal, [b.model_dump(exclude_none=True) for b in liste])
    return {"bolge_sayisi": adet}


async def _gonder(ws: WebSocket, mesaj: dict) -> None:
    """JSON mesaj gonderir."""
    await ws.send_text(json.dumps(mesaj, ensure_ascii=False))


@router.websocket("/ws")
async def canli_ws(ws: WebSocket) -> None:
    """Canli konum WebSocket'i (protokol modul aciklamasinda)."""
    await ws.accept()
    try:
        giris = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=GIRIS_SURESI_SN))
        if giris.get("tip") != "giris":
            raise ValueError("ilk mesaj giris olmali")
        kanal = _kanal_dogrula(str(giris.get("kanal") or ""))
        proje, _ = await anahtar_dogrula(giris.get("anahtar"), "canli", ws.headers.get("origin"))
    except HTTPException as hata:
        await _gonder(ws, {"tip": "hata", "mesaj": hata.detail})
        await ws.close(code=4400 + hata.status_code % 100 if hata.status_code < 500 else 1011)
        return
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, AttributeError):
        log.info("Canli baglanti girisi gecersiz ya da zaman asimi")
        try:
            await _gonder(ws, {"tip": "hata", "mesaj": "Giris mesaji bekleniyor: {tip: giris, anahtar, kanal}."})
            await ws.close(code=4400)
        except (RuntimeError, WebSocketDisconnect):
            log.debug("Canli baglanti zaten kapanmis")
        return

    proje_id = proje["id"]
    await _gonder(ws, {"tip": "hazir", "kanal": kanal, "konumlar": await canli.son_konumlar(proje_id, kanal)})
    son_mesaj = time.monotonic()
    pencere: list[float] = []
    abonelik = None
    gorevler: list[asyncio.Task] = []

    async def dinle() -> None:
        """Redis kanalindaki olaylari istemciye aktarir."""
        async for m in abonelik.listen():
            if m.get("type") == "message":
                await ws.send_text(m["data"])

    async def kalp_atisi() -> None:
        """Duzenli ping; uzun sessizlikte baglantiyi kapatir."""
        while True:
            await asyncio.sleep(KALP_ATISI_SN)
            if time.monotonic() - son_mesaj > SESSIZLIK_SINIRI_SN:
                log.info("Canli baglanti sessiz kaldi, kapatiliyor (proje %s)", proje_id)
                await ws.close(code=4408)
                return
            await _gonder(ws, {"tip": "ping", "zaman": time.time()})

    try:
        if giris.get("dinle", True):
            abonelik = cache.istemci().pubsub()
            await abonelik.subscribe(canli.kanal_adi(proje_id, kanal))
            gorevler.append(asyncio.create_task(dinle()))
        gorevler.append(asyncio.create_task(kalp_atisi()))
        while True:
            ham = await ws.receive_text()
            son_mesaj = time.monotonic()
            try:
                mesaj = json.loads(ham)
            except json.JSONDecodeError:
                await _gonder(ws, {"tip": "hata", "mesaj": "Mesaj JSON olmali."})
                continue
            tip = mesaj.get("tip") if isinstance(mesaj, dict) else None
            if tip == "ping":
                await _gonder(ws, {"tip": "pong", "zaman": time.time()})
            elif tip == "konum":
                simdi = time.monotonic()
                pencere = [z for z in pencere if simdi - z < 1] + [simdi]
                if len(pencere) > SANIYEDE_EN_FAZLA:
                    await _gonder(ws, {"tip": "hata", "mesaj": f"Saniyede en fazla {SANIYEDE_EN_FAZLA} konum gonderilebilir."})
                    continue
                try:
                    konum = Konum(**{k: v for k, v in mesaj.items() if k != "tip"})
                except ValidationError:
                    await _gonder(ws, {"tip": "hata", "mesaj": "Konum gecersiz (id, lat, lon gerekli)."})
                    continue
                await canli.konum_isle(proje_id, kanal, konum.model_dump(exclude_none=True))
            elif tip != "pong":
                await _gonder(ws, {"tip": "hata", "mesaj": "Bilinmeyen mesaj tipi."})
    except WebSocketDisconnect:
        log.debug("Canli baglanti kapandi (proje %s)", proje_id)
    except RuntimeError:
        log.debug("Canli baglanti kapanmis sokete yazildi (proje %s)", proje_id)
    finally:
        for g in gorevler:
            g.cancel()
        if abonelik is not None:
            await abonelik.unsubscribe()
            await abonelik.aclose()
