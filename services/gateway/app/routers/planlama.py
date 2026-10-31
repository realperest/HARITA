"""Cok araçli / cok kuryeli rota planlama ucu (VROOM + Valhalla matrisi).

Ornek: 5 kurye, 60 siparis -> hangi kurye hangi siparisi hangi sirayla alir; kapasite, beceri (soguk zincir, buyuk paket),
zaman araligi (teslim 12:00-13:00), oncelik ve alim-teslim ciftleri (restorandan al -> musteriye birak) desteklenir.
Zamanlar saniyedir; mutlak (Unix zamani) ya da gunun basindan itibaren saniye olarak tutarli verilmelidir.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.config import ayarlar
from app.schemas.harita import Nokta
from app.security import yetki
from app.services import planlama, valhalla
from app.services.http import AltServisHatasi, AltServisYok

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["planlama"])

ZamanAraligi = tuple[int, int]


class Arac(BaseModel):
    """Kurye / arac. bitis verilmezse son durakta biter (geri donus yok)."""

    id: str | int
    baslangic: Nokta
    bitis: Nokta | None = None
    kapasite: list[int] | None = Field(default=None, max_length=5)
    beceriler: list[int] | None = Field(default=None, max_length=20)
    calisma: ZamanAraligi | None = None
    maks_gorev: int | None = Field(default=None, ge=1)
    maks_sure_sn: int | None = Field(default=None, ge=60)


class Gorev(BaseModel):
    """Tek noktali is (teslimat ya da ziyaret). miktar araç kapasitesinden duser."""

    id: str | int
    konum: Nokta
    sure_sn: int = Field(default=0, ge=0, le=86400)
    miktar: list[int] | None = Field(default=None, max_length=5)
    beceriler: list[int] | None = Field(default=None, max_length=20)
    zaman_araliklari: list[ZamanAraligi] | None = Field(default=None, max_length=10)
    oncelik: int | None = Field(default=None, ge=0, le=100)


class GonderiUcu(BaseModel):
    """Alim ya da teslim noktasi."""

    konum: Nokta
    sure_sn: int = Field(default=0, ge=0, le=86400)
    zaman_araliklari: list[ZamanAraligi] | None = Field(default=None, max_length=10)


class Gonderi(BaseModel):
    """Alim-teslim cifti: ayni arac once alir sonra teslim eder (or. restoran -> musteri)."""

    id: str | int
    alim: GonderiUcu
    teslim: GonderiUcu
    miktar: list[int] | None = Field(default=None, max_length=5)
    beceriler: list[int] | None = Field(default=None, max_length=20)
    oncelik: int | None = Field(default=None, ge=0, le=100)


class PlanIstek(BaseModel):
    """Planlama istegi."""

    profil: str = Field(default="araba", max_length=20)
    araclar: list[Arac] = Field(min_length=1, max_length=100)
    gorevler: list[Gorev] = Field(default_factory=list, max_length=500)
    gonderiler: list[Gonderi] = Field(default_factory=list, max_length=250)
    geometri: bool = False

    @model_validator(mode="after")
    def _kontrol(self) -> "PlanIstek":
        if not self.gorevler and not self.gonderiler:
            raise ValueError("En az bir gorev ya da gonderi gerekli.")
        for ad, liste in (("arac", self.araclar), ("gorev", self.gorevler), ("gonderi", self.gonderiler)):
            kimlikler = [o.id for o in liste]
            if len(kimlikler) != len(set(kimlikler)):
                raise ValueError(f"{ad} kimlikleri tekil olmali.")
        return self


@router.post("/planla")
async def planla(istek: PlanIstek, _proje: dict = Depends(yetki("matris"))) -> dict:
    """Gorevleri ve gonderileri araçlara atar ve siralar. Donus: rotalar (arac_id, duraklar: tur, konum, varis_sn, gorev_id /
    gonderi_id, yuk), atanamayan, ozet. geometri=true ile her rotanin cizgisi (GeoJSON) eklenir."""
    maliyet = valhalla.maliyet_modeli(istek.profil)
    if maliyet is None:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    try:
        return await planlama.coz(istek, maliyet)
    except ValueError as hata:
        raise HTTPException(status_code=422, detail=str(hata)) from hata
    except AltServisYok as hata:
        raise HTTPException(status_code=404, detail="Konumlardan biri yola oturtulamadi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Planlama servisi su an yanit vermiyor.") from hata


class Aday(BaseModel):
    """Atanabilecek kurye / arac ve anlik konumu."""

    id: str | int
    konum: Nokta


class EnYakinIstek(BaseModel):
    """Bir hedefe (siparis, musteri) yol uzerinden en hizli ulasacak adaylar."""

    hedef: Nokta
    adaylar: list[Aday] = Field(min_length=1)
    profil: str = Field(default="motosiklet", max_length=20)
    adet: int = Field(default=5, ge=1, le=50)


@router.post("/en-yakin")
async def en_yakin(istek: EnYakinIstek, _proje: dict = Depends(yetki("matris"))) -> dict:
    """Adaylari hedefe gercek yol suresine gore siralar (kus ucusu degil): [{id, sure_sn, mesafe_m}], ulasamayanlar sonda."""
    maliyet = valhalla.maliyet_modeli(istek.profil)
    if maliyet is None:
        raise HTTPException(status_code=422, detail="Profil gecersiz.")
    if len(istek.adaylar) > ayarlar.MATRIS_MAKS_NOKTA:
        raise HTTPException(status_code=422, detail=f"En fazla {ayarlar.MATRIS_MAKS_NOKTA} aday verilebilir.")
    try:
        m = await valhalla.matris([a.konum for a in istek.adaylar], [istek.hedef], maliyet)
    except AltServisYok as hata:
        raise HTTPException(status_code=404, detail="Hedef yola oturtulamadi.") from hata
    except AltServisHatasi as hata:
        raise HTTPException(status_code=502, detail="Rota servisi su an yanit vermiyor.") from hata
    sonuc = [{"id": a.id, "sure_sn": m["sure_sn"][i][0], "mesafe_m": m["mesafe_m"][i][0]} for i, a in enumerate(istek.adaylar)]
    sonuc.sort(key=lambda r: (r["sure_sn"] is None, r["sure_sn"] or 0))
    return {"adaylar": sonuc[: istek.adet]}
