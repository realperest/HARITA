"""Yerlesim uclari testleri (gercek PostGIS; kucuk deneme verisi tohumlanir)."""

import pytest
import pytest_asyncio

from app.db import havuz
from tests.test_gateway import proje_ac

pytestmark = pytest.mark.asyncio(loop_scope="session")


def kutu(boylam_min: float, enlem_min: float, boylam_max: float, enlem_max: float) -> str:
    """Dikdortgen MULTIPOLYGON (EWKT) uretir."""
    return (f"SRID=4326;MULTIPOLYGON((({boylam_min} {enlem_min},{boylam_max} {enlem_min},{boylam_max} {enlem_max},"
            f"{boylam_min} {enlem_max},{boylam_min} {enlem_min})))")


async def ekle(baglanti, anahtar: str, tur_id: int, ad: str, ad_arama: str, lon: float, lat: float,
               sinir: str | None, ust_id: int | None, nufus: int | None = None) -> int:
    """Deneme satirini ekler (tekrar calistirilabilir) ve id'sini dondurur."""
    return await baglanti.fetchval(
        """INSERT INTO yerlesim (tur_id, ust_id, kaynak_anahtari, ad, ad_arama, merkez, sinir, nufus)
           VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography,
                   CASE WHEN $8::text IS NULL THEN NULL ELSE ST_GeogFromText($8) END, $9)
           ON CONFLICT (kaynak_anahtari) DO UPDATE SET ad = EXCLUDED.ad, aktif_mi = TRUE RETURNING id""",
        tur_id, ust_id, anahtar, ad, ad_arama, lon, lat, sinir, nufus)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def tohum(istemci) -> dict:
    """Il > ilce > mahalle ve bir sehir merkezi tohumlar."""
    async with havuz().acquire() as b:
        il = await ekle(b, "test:il:1", 1, "Tekirdağ", "tekirdag", 27.5, 41.1, kutu(27.0, 40.8, 28.0, 41.4), None, 1100000)
        ilce = await ekle(b, "test:ilce:1", 2, "Çorlu", "corlu", 27.8, 41.15, kutu(27.7, 41.1, 27.9, 41.25), il, 300000)
        mahalle = await ekle(b, "test:mah:1", 3, "Cumhuriyet Mahallesi", "cumhuriyet mahallesi", 27.805, 41.16,
                             kutu(27.79, 41.15, 27.82, 41.17), ilce)
        sehir = await ekle(b, "test:sehir:1", 4, "Çorlu", "corlu", 27.8, 41.159, None, ilce, 300000)
    return {"il": il, "ilce": ilce, "mahalle": mahalle, "sehir": sehir}


async def baslik(istemci) -> dict:
    _, anahtar = await proje_ac(istemci)
    return {"X-Harita-Anahtar": anahtar}


async def test_ara_turkce_duyarsiz(istemci, tohum):
    b = await baslik(istemci)
    yanit = await istemci.get("/v1/yerlesim/ara?q=CORLU", headers=b)
    assert yanit.status_code == 200
    turler = {s["tur"] for s in yanit.json()}
    assert {"ilce", "sehir"} <= turler
    dar = await istemci.get("/v1/yerlesim/ara?q=çorlu&tur=ilce", headers=b)
    assert [s["tur"] for s in dar.json()] == ["ilce"]
    assert dar.json()[0]["ust"]["ad"] == "Tekirdağ"


async def test_getir_zincir_ve_sinir(istemci, tohum):
    b = await baslik(istemci)
    yanit = await istemci.get(f"/v1/yerlesim/{tohum['mahalle']}?sinir=true", headers=b)
    veri = yanit.json()
    assert [z["tur"] for z in veri["zincir"]] == ["il", "ilce"]
    assert veri["sinir"]["type"] == "MultiPolygon"
    assert (await istemci.get("/v1/yerlesim/999999999", headers=b)).status_code == 404


async def test_alt_ogeler(istemci, tohum):
    b = await baslik(istemci)
    yanit = await istemci.get(f"/v1/yerlesim/{tohum['il']}/alt?tur=ilce", headers=b)
    assert [s["ad"] for s in yanit.json()] == ["Çorlu"]


async def test_nokta_icinde_ve_en_yakin(istemci, tohum):
    b = await baslik(istemci)
    yanit = await istemci.get("/v1/yerlesim/nokta?lat=41.16&lon=27.805", headers=b)
    veri = yanit.json()
    assert [s["tur"] for s in veri["icinde"]] == ["il", "ilce", "mahalle_koy"]
    assert veri["en_yakin_merkez"]["tur"] == "sehir" and veri["en_yakin_merkez"]["mesafe_m"] < 2000
    disarida = await istemci.get("/v1/yerlesim/nokta?lat=39.0&lon=35.0", headers=b)
    assert disarida.json()["icinde"] == []


async def test_yakin(istemci, tohum):
    b = await baslik(istemci)
    yanit = await istemci.get("/v1/yerlesim/yakin?lat=41.16&lon=27.8&yaricap_m=5000&tur=sehir", headers=b)
    assert yanit.status_code == 200 and yanit.json()[0]["ad"] == "Çorlu"
    assert (await istemci.get("/v1/yerlesim/yakin?lat=39.0&lon=35.0&yaricap_m=1000", headers=b)).json() == []


async def test_yerlesim_izni_yok(istemci, tohum):
    _, anahtar = await proje_ac(istemci, servisler=["rota"])
    yanit = await istemci.get("/v1/yerlesim/ara?q=corlu", headers={"X-Harita-Anahtar": anahtar})
    assert yanit.status_code == 403
