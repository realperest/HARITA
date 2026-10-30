"""Rota, matris ve arama istek / yanit semalari."""

from typing import Literal

from pydantic import BaseModel, Field

Profil = Literal["auto", "motosiklet", "bisiklet", "yaya"]


class Nokta(BaseModel):
    """Enlem / boylam noktasi."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RotaIstegi(BaseModel):
    """Iki veya daha fazla nokta arasi rota istegi."""

    noktalar: list[Nokta] = Field(min_length=2)
    profil: Profil = "auto"
    geometri: bool = True


class RotaYaniti(BaseModel):
    """Rota sonucu: sure (sn), mesafe (m) ve GeoJSON cizgi."""

    sure_sn: float
    mesafe_m: float
    geometri: dict | None = None


class MatrisIstegi(BaseModel):
    """Kaynaklardan hedeflere sure / mesafe matrisi istegi."""

    kaynaklar: list[Nokta] = Field(min_length=1)
    hedefler: list[Nokta] = Field(min_length=1)
    profil: Profil = "auto"


class MatrisYaniti(BaseModel):
    """Matris sonucu; satir kaynak, sutun hedef. Ulasilamayan hucre null."""

    sure_sn: list[list[float | None]]
    mesafe_m: list[list[float | None]]


class ProjeOlustur(BaseModel):
    """Yeni proje kaydi."""

    ad: str = Field(min_length=2, max_length=80)
    aciklama: str | None = Field(default=None, max_length=300)
    dakika_limiti: int = Field(default=600, ge=1, le=100000)
    servisler: list[str] = Field(default_factory=lambda: ["rota", "matris", "arama", "yapilandirma", "yerlesim", "adres", "valhalla"])
    kaynaklar: list[str] = Field(default_factory=list)


class ProjeGuncelle(BaseModel):
    """Proje ayarlarini kismen gunceller."""

    aktif: bool | None = None
    dakika_limiti: int | None = Field(default=None, ge=1, le=100000)
    servisler: list[str] | None = None
    kaynaklar: list[str] | None = None
