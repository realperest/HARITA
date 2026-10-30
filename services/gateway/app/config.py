"""Ortam degiskenlerinden okunan ayarlar (degerler Coolify panelinde tutulur)."""

from pydantic_settings import BaseSettings


class Ayarlar(BaseSettings):
    """Gateway ayarlari."""

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    YONETIM_ANAHTARI: str
    ROTA_ADRESI: str = "http://rota:8002"
    ARAMA_ADRESI: str = "http://arama:2322"
    # Tarayicinin karolari cekecegi genel adres (or. https://karo.harita.example.com)
    KARO_ADRESI: str
    KARO_ADI: str = "turkiye"
    KARO_MAKS_YAKINLASTIRMA: int = 15
    UPSTREAM_ZAMAN_ASIMI_SN: float = 15.0
    ANAHTAR_ONBELLEK_SN: int = 60
    MATRIS_MAKS_NOKTA: int = 50
    ROTA_MAKS_NOKTA: int = 20
    LOG_SEVIYESI: str = "INFO"


ayarlar = Ayarlar()
