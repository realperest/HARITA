"""Ortam degiskenlerinden okunan ayarlar (degerler Coolify panelinde tutulur)."""

from pydantic_settings import BaseSettings


class Ayarlar(BaseSettings):
    """Gateway ayarlari."""

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    YONETIM_ANAHTARI: str
    ROTA_ADRESI: str = "http://rota:8002"
    # Tarayicinin karolari cekecegi genel adres (or. https://karo.harita.example.com)
    KARO_ADRESI: str
    KARO_ADI: str = "turkiye"
    KARO_MAKS_YAKINLASTIRMA: int = 15
    UPSTREAM_ZAMAN_ASIMI_SN: float = 15.0
    ANAHTAR_ONBELLEK_SN: int = 60
    MATRIS_MAKS_NOKTA: int = 50
    ROTA_MAKS_NOKTA: int = 50
    # Cok araçli planlama (VROOM); matris Valhalla'dan 50x50 bloklarla alinir
    PLAN_ADRESI: str = "http://plan:3000"
    PLAN_MAKS_NOKTA: int = 300
    # Hava durumu: Open-Meteo (ucretsiz sunucu ticari olmayan kullanim icindir; ticari kullanimda
    # https://customer-api.open-meteo.com ve HAVA_ANAHTARI)
    HAVA_ADRESI: str = "https://api.open-meteo.com"
    HAVA_ANAHTARI: str = ""
    LOG_SEVIYESI: str = "INFO"


ayarlar = Ayarlar()
