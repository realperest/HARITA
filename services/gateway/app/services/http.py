"""Alt servislere giden ortak httpx istemcisi ve hata tipi."""

import httpx

from app.config import ayarlar

_istemci: httpx.AsyncClient | None = None


class AltServisHatasi(Exception):
    """Alt servis ulasilamaz veya beklenmeyen yanit verdi; teknik ayrinti loglanir, kullaniciya genel mesaj gider."""


class AltServisYok(AltServisHatasi):
    """Istek gecerli ama alt servis sonuc bulamadi (or. rota yok)."""


def baslat() -> None:
    """Ortak istemciyi olusturur."""
    global _istemci
    _istemci = httpx.AsyncClient(timeout=ayarlar.UPSTREAM_ZAMAN_ASIMI_SN)


async def kapat() -> None:
    """Ortak istemciyi kapatir."""
    global _istemci
    if _istemci is not None:
        await _istemci.aclose()
        _istemci = None


def istemci() -> httpx.AsyncClient:
    """Acik istemciyi dondurur."""
    if _istemci is None:
        raise RuntimeError("HTTP istemcisi acik degil.")
    return _istemci
