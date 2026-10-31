"""Adres uclari: birlesik arama, ters arama, sokak, kapi numarasi ve onemli yerler (tum Turkiye, OSM)."""

import asyncio
import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.crud import adres as adres_crud
from app.crud import adres_ayristir as adres_ayristir_crud
from app.crud import kapi_havuzu
from app.crud import yerlesim as yerlesim_crud
from app.security import yetki

router = APIRouter(prefix="/v1/adres", tags=["adres"])


@router.get("/ara")
async def ara(q: str = Query(min_length=2, max_length=200), tur: Literal["kapi", "sokak", "bina", "yer", "yerlesim"] | None = None,
              ust_id: int | None = None, lat: float | None = Query(default=None, ge=-90, le=90),
              lon: float | None = Query(default=None, ge=-180, le=180), limit: int = Query(default=10, ge=1, le=50),
              yaricap_m: int | None = Query(default=None, ge=100, le=500000),
              _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Birlesik adres arama. 'Namik Kemal Bulvari 12' gibi metinler kapi numarasina kadar eslesir.
    lat/lon verilirse esit eslesmelerde yakin olan one gelir; yaricap_m ile (lat/lon gerekir) bu yaricap disi elenir."""
    return await adres_crud.ara(q, tur, ust_id, lat, lon, limit, yaricap_m)


class TopluOge(BaseModel):
    """Toplu getirilecek oge: tur (sokak, kapi, yer, bina ya da il, ilce, mahalle_koy, sehir ...) ve kimlik."""

    tur: Literal["sokak", "kapi", "yer", "bina", "il", "ilce", "mahalle_koy", "sehir", "kasaba", "koy", "mezra", "semt"]
    id: int


class TopluIstek(BaseModel):
    """En fazla 500 oge."""

    ogeler: list[TopluOge] = Field(min_length=1, max_length=500)


class KaynakIstek(BaseModel):
    """OSM kaynak anahtarlari (osm:node:123, osm:way:456, osm:relation:789, sokak:...). En fazla 500."""

    anahtarlar: list[str] = Field(min_length=1, max_length=500)


class AyristirIstek(BaseModel):
    """Serbest adres metni (tek) ya da metinler (en fazla 100). Baglam: isletme / kullanici konumu ya da ilce kimligi;
    metinde il / ilce yazilmadiginda arama bu cevrede yapilir."""

    metin: str | None = Field(default=None, min_length=3, max_length=500)
    metinler: list[str] | None = Field(default=None, min_length=1, max_length=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    ilce_id: int | None = None


@router.post("/ayristir")
async def ayristir(istek: AyristirIstek, _proje: dict = Depends(yetki("adres"))) -> dict | list[dict]:
    """Serbest yazilmis adresi parcalarina ayirir (il, ilce, mahalle / koy, sokak, kapi no, bina / site, blok, kat, daire,
    posta kodu, tarif), adres veritabaniyla dogrular, yazim farklarini duzeltir, konum ve 0-100 guven puani verir.
    'metin' verilirse tek sonuc, 'metinler' verilirse ayni sirada liste doner."""
    if bool(istek.metin) == bool(istek.metinler):
        raise HTTPException(status_code=422, detail="'metin' ya da 'metinler' alanlarindan biri verilmeli.")
    baglam = {"lat": istek.lat, "lon": istek.lon, "ilce_id": istek.ilce_id} if (istek.lat is not None and istek.lon is not None) \
        else {"ilce_id": istek.ilce_id}
    if istek.metin:
        return await adres_ayristir_crud.ayristir_ve_dogrula(istek.metin, baglam)
    sinir = asyncio.Semaphore(4)

    async def tek(m: str) -> dict:
        async with sinir:
            return await adres_ayristir_crud.ayristir_ve_dogrula(m, baglam)

    return list(await asyncio.gather(*(tek(m) for m in istek.metinler)))


@router.post("/toplu")
async def toplu(istek: TopluIstek, _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Kimlikleri verilen ogeler tek istekte: ad, adres metni, zincir kimlikleri (ust: mahalle_id, ilce_id, il_id) ve kaynak anahtari.
    Kayitli adreslerin adlarini toplu gostermek ve secimlerin tutarliligini dogrulamak icin. Bulunamayan oge listede yer almaz."""
    return await adres_crud.toplu([(o.tur, o.id) for o in istek.ogeler])


@router.post("/kaynak")
async def kaynak(istek: KaynakIstek, _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """OSM kaynak anahtarindan HARITA kaydi (baska sistemlerdeki OSM kaynakli kayitlari eslemek icin)."""
    return await adres_crud.kaynaktan(list(dict.fromkeys(istek.anahtarlar)))


@router.get("/nokta")
async def nokta(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), yaricap_m: int = Query(default=150, ge=10, le=2000),
                limit: int = Query(default=5, ge=1, le=20), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Ters arama: noktadan adres metni, il / ilce / mahalle, en yakin sokaklar, kapi numaralari ve yerler."""
    return await adres_crud.nokta(lat, lon, yaricap_m, limit)


@router.get("/yerler")
async def yerler(bati: float = Query(ge=-180, le=180), guney: float = Query(ge=-90, le=90), dogu: float = Query(ge=-180, le=180),
                 kuzey: float = Query(ge=-90, le=90), tur: str | None = Query(default=None, max_length=30),
                 limit: int = Query(default=1000, ge=1, le=5000), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Harita katmani: kutu icindeki onemli yerler GeoJSON olarak (eczane, okul, market, restoran vb.)."""
    return await adres_crud.yerler_kutuda(bati, guney, dogu, kuzey, tur, limit)


@router.get("/mahalle/{mahalle_id}/sokaklar")
async def mahalle_sokaklari(mahalle_id: int, q: str | None = Query(default=None, max_length=100), limit: int = Query(default=200, ge=1, le=1000),
                            atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir mahalle / koyun sokaklari (acilir liste icin)."""
    return await adres_crud.sokaklar(mahalle_id, q, limit, atla)


@router.get("/sokak/{sokak_id}")
async def sokak(sokak_id: int, cizgi: bool = False, _proje: dict = Depends(yetki("adres"))) -> dict:
    """Tek sokak; cizgi=true ile GeoJSON cizgisi."""
    veri = await adres_crud.sokak_getir(sokak_id, cizgi)
    if veri is None:
        raise HTTPException(status_code=404, detail="Sokak bulunamadi.")
    return veri


@router.get("/sokak/{sokak_id}/kapilar")
async def sokak_kapilari(sokak_id: int, limit: int = Query(default=200, ge=1, le=1000), atla: int = Query(default=0, ge=0),
                         _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir sokaktaki kapi numaralari."""
    return await adres_crud.kapilar(sokak_id, limit, atla)


@router.get("/sokak/{sokak_id}/en-yakin-kapi")
async def sokak_en_yakin_kapi(sokak_id: int, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                              yaricap_m: int = Query(default=100, ge=5, le=1000), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Pin icin kapi numarasi onerisi: secilen sokaktaki en yakin kapi (mesafe_m ile). OSM'de yoksa ortak havuzdan ogrenilmis kapi
    (kaynak: "havuz"). Yaricapta kapi yoksa 404."""
    veri = await adres_crud.en_yakin_kapi(sokak_id, lat, lon, yaricap_m)
    if veri is None:
        ogrenilen = await kapi_havuzu.en_yakin(sokak_id, lat, lon, yaricap_m)
        if ogrenilen:
            return {**ogrenilen, "tur": "kapi", "kaynak": "havuz", "ad": f"{ogrenilen['sokak']} No:{ogrenilen['kapi_no']}"}
    if veri is None:
        raise HTTPException(status_code=404, detail="Bu sokakta yakinda kapi numarasi yok.")
    return veri


class KapiOgrenIstek(BaseModel):
    """Teslimat / ziyaret konumu: kapinin onunde alinan GPS (dogruluk_m 50 ustu ise kabul edilmez)."""

    sokak_id: int
    kapi_no: str = Field(min_length=1, max_length=20, pattern=r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü/ -]+$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    dogruluk_m: float | None = Field(default=None, ge=0, le=50)


@router.post("/kapi-ogren")
async def kapi_ogren(istek: KapiOgrenIstek, proje: dict = Depends(yetki("adres"))) -> dict:
    """Ortak kapi havuzuna gozlem ekler: OSM'de olmayan kapi numarasi teslimat konumundan ogrenilir ve tum projelerin
    ayristirma / en yakin kapi sonuclarinda kullanilir. Iki gozlemden sonra guvenilir sayilir. OSM'de varsa durum "osm_var"."""
    try:
        return await kapi_havuzu.ogren(proje["id"], istek.sokak_id, istek.kapi_no, istek.lat, istek.lon, istek.dogruluk_m)
    except ValueError as hata:
        raise HTTPException(status_code=422, detail=str(hata)) from hata


@router.delete("/kapi-ogren/{kapi_id}")
async def kapi_ogren_geri_al(kapi_id: int, proje: dict = Depends(yetki("adres"))) -> dict:
    """Bu projenin bu kapi icin verdigi gozlemleri geri alir (yanlis bildirim). Diger projelerin gozlemleri kalir."""
    if not await kapi_havuzu.geri_al(proje["id"], kapi_id):
        raise HTTPException(status_code=404, detail="Bu projeye ait gozlem yok.")
    return {"geri_alindi": True}


@router.get("/sokak/{sokak_id}/ogrenilen-kapilar")
async def sokak_ogrenilen_kapilari(sokak_id: int, _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Sokakta ortak havuzdan ogrenilmis kapilar (guvenilir: en az iki gozlem)."""
    return await kapi_havuzu.sokak_kapilari(sokak_id)


@router.get("/sokak/{sokak_id}/binalar")
async def sokak_binalari(sokak_id: int, limit: int = Query(default=200, ge=1, le=1000), atla: int = Query(default=0, ge=0),
                         _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir sokaga bagli adli site ve binalar (Site / Bina acilir listesi)."""
    return await adres_crud.sokak_binalari(sokak_id, limit, atla)


@router.get("/mahalle/{mahalle_id}/binalar")
async def mahalle_binalari(mahalle_id: int, q: str | None = Query(default=None, max_length=100), limit: int = Query(default=200, ge=1, le=1000),
                           atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Bir mahalle / koydeki adli site ve binalar."""
    return await adres_crud.mahalle_binalari(mahalle_id, q, limit, atla)


@router.get("/bina/{bina_id}")
async def bina(bina_id: int, sinir: bool = False, _proje: dict = Depends(yetki("adres"))) -> dict:
    """Tek site / bina; sinir=true ile GeoJSON poligonu."""
    veri = await adres_crud.bina_getir(bina_id, sinir)
    if veri is None:
        raise HTTPException(status_code=404, detail="Bina bulunamadi.")
    return veri


def _karo_kutusu(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Web Mercator karo (x, y, z) -> (bati, guney, dogu, kuzey)."""
    n = 2 ** z
    bati, dogu = x / n * 360 - 180, (x + 1) / n * 360 - 180
    kuzey = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    guney = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return bati, guney, dogu, kuzey


@router.get("/yerler/karo")
async def yerler_karo(x: int = Query(ge=0), y: int = Query(ge=0), z: int = Query(default=15, ge=10, le=20), tur: str | None = Query(default=None, max_length=30),
                      limit: int = Query(default=2000, ge=1, le=5000), _proje: dict = Depends(yetki("adres"))) -> dict:
    """Karo (x, y, z=15 varsayilan) icindeki onemli yerler GeoJSON olarak (karo bazli onbellekleme icin)."""
    bati, guney, dogu, kuzey = _karo_kutusu(x, y, z)
    return await adres_crud.yerler_kutuda(bati, guney, dogu, kuzey, tur, limit)


@router.get("/yakin")
async def yakin_yerler(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), yaricap_m: int = Query(default=5000, ge=50, le=100000),
                       tur: str | None = Query(default=None, max_length=30), limit: int = Query(default=20, ge=1, le=100),
                       _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Noktaya yakin onemli yerler (or. tur=akaryakit: en yakin benzin istasyonlari), yakindan uzaga."""
    return await adres_crud.yakin_yerler(lat, lon, yaricap_m, tur, limit)


class RotaBoyunca(BaseModel):
    """Rota cizgisi boyunca yer aramasi istegi (GeoJSON LineString koordinatlari: [boylam, enlem])."""

    koordinatlar: list[list[float]] = Field(min_length=2, max_length=5000)
    tur: str | None = Field(default=None, max_length=30)
    tampon_m: int = Field(default=500, ge=10, le=5000)
    limit: int = Field(default=100, ge=1, le=500)


@router.post("/rota-boyunca")
async def rota_boyunca(istek: RotaBoyunca, _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Rota boyunca yerler (benzin, mola, otel vb.), rota uzerindeki siraya gore."""
    return await adres_crud.rota_boyunca(istek.koordinatlar, istek.tur, istek.tampon_m, istek.limit)


@router.get("/alt")
async def alt_ogeler(ust: str = Query(pattern=r"^(il|ilce|mahalle_koy|semt|sokak):\d+$", description="tur:id, or. ilce:123"),
                     cocuk: Literal["sokak", "bina", "kapi"] | None = None, limit: int = Query(default=200, ge=1, le=1000),
                     atla: int = Query(default=0, ge=0), _proje: dict = Depends(yetki("adres"))) -> list[dict]:
    """Adres agacinda bir alt seviye: il > ilce > mahalle/koy > sokak > site-bina / kapi. Acilir listeler tek uctan beslenir."""
    tur, kimlik = ust.split(":")
    kimlik = int(kimlik)
    if tur == "ilce" and cocuk == "sokak":
        # mahalle / koy sinirina dusmeyip dogrudan ilceye bagli yollar
        return await adres_crud.ilce_sokaklari(kimlik, None, limit, atla)
    if tur in ("il", "ilce"):
        # il > ilce, ilce > mahalle / koy (sehir, kasaba, semt merkezi noktalari acilir listeye girmez)
        return await yerlesim_crud.alt_ogeler(kimlik, "ilce" if tur == "il" else "mahalle_koy", limit, atla)
    if tur in ("mahalle_koy", "semt"):
        return await (adres_crud.mahalle_binalari(kimlik, None, limit, atla) if cocuk == "bina" else adres_crud.sokaklar(kimlik, None, limit, atla))
    return await (adres_crud.kapilar(kimlik, limit, atla) if cocuk == "kapi" else adres_crud.sokak_binalari(kimlik, limit, atla))


@router.get("/sekil")
async def sekil(tur: Literal["il", "ilce", "mahalle_koy", "sehir", "kasaba", "koy", "mezra", "semt", "sokak", "bina"], id: int,
                _proje: dict = Depends(yetki("adres"))) -> dict:
    """Herhangi bir adres ogesinin GeoJSON sekli (sinir, sokak cizgisi veya bina poligonu)."""
    veri = await adres_crud.sekil(tur, id)
    if veri is None:
        raise HTTPException(status_code=404, detail="Oge bulunamadi.")
    return veri
