"""Adres, uyumlu uclar ve Valhalla gecisi testleri (gercek PostGIS; kucuk deneme verisi tohumlanir)."""

import httpx
import pytest
import pytest_asyncio
import respx

from app.db import havuz
from tests.test_gateway import proje_ac
from tests.test_yerlesim import tohum  # noqa: F401  (il > ilce > mahalle tohumu)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def adres_tohum(tohum) -> dict:  # noqa: F811
    """Mahalleye bir sokak, kapi numarasi ve eczane tohumlar."""
    async with havuz().acquire() as b:
        sokak = await b.fetchval(
            """INSERT INTO sokak (kaynak_anahtari, ad, ad_arama, sinif_id, mahalle_id, cizgi, merkez)
               VALUES ('test:sokak:1', 'Namık Kemal Bulvarı', 'namik kemal bulvari', 3, $1,
                       ST_GeogFromText('SRID=4326;MULTILINESTRING((27.8040 41.1595,27.8060 41.1605))'),
                       ST_SetSRID(ST_MakePoint(27.805, 41.16), 4326)::geography)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE RETURNING id""", tohum["mahalle"])
        await b.execute(
            """INSERT INTO kapi_numarasi (kaynak_anahtari, kapi_no, kapi_no_arama, sokak_ad, sokak_id, konum, mahalle_id)
               VALUES ('test:kapi:1', '12', '12', 'Namık Kemal Bulvarı', $1, ST_SetSRID(ST_MakePoint(27.8052, 41.1601), 4326)::geography, $2)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE, sokak_id = EXCLUDED.sokak_id""", sokak, tohum["mahalle"])
        await b.execute(
            """INSERT INTO yer_isareti (tur_id, kaynak_anahtari, ad, ad_arama, konum, mahalle_id)
               VALUES (1, 'test:yer:1', 'Deniz Eczanesi', 'deniz eczanesi', ST_SetSRID(ST_MakePoint(27.8051, 41.1602), 4326)::geography, $1)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE""", tohum["mahalle"])
        bina = await b.fetchval(
            """INSERT INTO bina (tur_id, kullanim_id, kaynak_anahtari, ad, ad_arama, sinir, merkez, mahalle_id, sokak_id)
               VALUES (2, 1, 'test:bina:1', 'Güneş Apartmanı', 'gunes apartmani',
                       ST_GeogFromText('SRID=4326;POLYGON((27.8050 41.1599,27.8054 41.1599,27.8054 41.1603,27.8050 41.1603,27.8050 41.1599))'),
                       ST_SetSRID(ST_MakePoint(27.8052, 41.1601), 4326)::geography, $1, $2)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE, sokak_id = EXCLUDED.sokak_id RETURNING id""", tohum["mahalle"], sokak)
    return {"sokak": sokak, "mahalle": tohum["mahalle"], "bina": bina}


async def baslik(istemci) -> dict:
    _, anahtar = await proje_ac(istemci)
    return {"X-Harita-Anahtar": anahtar}


async def test_sokak_arama_ve_adres_metni(istemci, adres_tohum):
    b = await baslik(istemci)
    r = (await istemci.get("/v1/adres/ara?q=namik kemal bulvari&tur=sokak", headers=b)).json()
    assert r[0]["tur"] == "sokak" and r[0]["ad"] == "Namık Kemal Bulvarı"
    assert r[0]["adres"] == "Namık Kemal Bulvarı, Cumhuriyet Mahallesi, Çorlu / Tekirdağ"


async def test_kapi_numarasi_aramasi(istemci, adres_tohum):
    b = await baslik(istemci)
    r = (await istemci.get("/v1/adres/ara?q=namik kemal bulvari 12", headers=b)).json()
    assert r[0]["tur"] == "kapi" and r[0]["ek"]["kapi_no"] == "12"
    assert "No:12" in r[0]["adres"]


async def test_yer_aramasi_ve_yakinlik(istemci, adres_tohum):
    b = await baslik(istemci)
    r = (await istemci.get("/v1/adres/ara?q=deniz eczane&tur=yer&lat=41.16&lon=27.805", headers=b)).json()
    assert r[0]["ad"] == "Deniz Eczanesi" and r[0]["ek"]["yer_turu"] == "eczane" and r[0]["mesafe_m"] is not None


async def test_ters_arama(istemci, adres_tohum):
    b = await baslik(istemci)
    v = (await istemci.get("/v1/adres/nokta?lat=41.1601&lon=27.8052", headers=b)).json()
    assert "Namık Kemal Bulvarı No:12" in v["adres"] and v["il"] == "Tekirdağ" and v["ilce"] == "Çorlu"
    assert v["sokaklar"][0]["ad"] == "Namık Kemal Bulvarı" and v["yerler"][0]["ad"] == "Deniz Eczanesi"


async def test_bina_ve_site_uclari(istemci, adres_tohum):
    b = await baslik(istemci)
    ters = (await istemci.get("/v1/adres/nokta?lat=41.1601&lon=27.8052", headers=b)).json()
    assert ters["binalar"][0]["ad"] == "Güneş Apartmanı" and ters["adres"].startswith("Güneş Apartmanı, Namık Kemal Bulvarı No:12")
    ara = (await istemci.get("/v1/adres/ara?q=gunes apartman&tur=bina", headers=b)).json()
    assert ara[0]["tur"] == "bina" and ara[0]["ek"]["kullanim"] == "apartments"
    assert [x["ad"] for x in (await istemci.get(f"/v1/adres/sokak/{adres_tohum['sokak']}/binalar", headers=b)).json()] == ["Güneş Apartmanı"]
    assert (await istemci.get(f"/v1/adres/mahalle/{adres_tohum['mahalle']}/binalar?q=gunes", headers=b)).json()[0]["ek"]["bina_turu"] == "bina"
    detay = (await istemci.get(f"/v1/adres/bina/{adres_tohum['bina']}?sinir=true", headers=b)).json()
    assert detay["sinir"]["type"] == "Polygon" and detay["ek"]["sokak_id"] == adres_tohum["sokak"]
    assert (await istemci.get("/v1/adres/bina/999999999", headers=b)).status_code == 404


async def test_yerler_kutuda_ve_sokak_listeleri(istemci, adres_tohum):
    b = await baslik(istemci)
    fc = (await istemci.get("/v1/adres/yerler?bati=27.80&guney=41.15&dogu=27.81&kuzey=41.17&tur=eczane", headers=b)).json()
    assert fc["type"] == "FeatureCollection" and fc["features"][0]["properties"]["tur"] == "eczane"
    liste = (await istemci.get(f"/v1/adres/mahalle/{adres_tohum['mahalle']}/sokaklar", headers=b)).json()
    assert [s["ad"] for s in liste] == ["Namık Kemal Bulvarı"]
    detay = (await istemci.get(f"/v1/adres/sokak/{adres_tohum['sokak']}?cizgi=true", headers=b)).json()
    assert detay["cizgi"]["type"] == "MultiLineString" and detay["ek"]["kapi_adet"] == 1
    kapilar = (await istemci.get(f"/v1/adres/sokak/{adres_tohum['sokak']}/kapilar", headers=b)).json()
    assert kapilar[0]["ek"]["kapi_no"] == "12"


async def test_nominatim_ve_photon_uyumu(istemci, adres_tohum):
    b = await baslik(istemci)
    n = (await istemci.get("/nominatim/search?q=namik kemal bulvari 12", headers=b)).json()
    assert n[0]["address"]["house_number"] == "12" and n[0]["address"]["suburb"] == "Cumhuriyet Mahallesi" and float(n[0]["lat"]) > 41
    nr = (await istemci.get("/nominatim/reverse?lat=41.1601&lon=27.8052", headers=b)).json()
    assert nr["address"]["road"] == "Namık Kemal Bulvarı" and nr["address"]["state"] == "Tekirdağ"
    p = (await istemci.get("/photon/api?q=namik kemal bulvari", headers=b)).json()
    assert p["type"] == "FeatureCollection" and p["features"][0]["properties"]["name"] == "Namık Kemal Bulvarı"
    assert (await istemci.get("/photon/reverse?lat=41.1601&lon=27.8052", headers=b)).json()["features"]


@respx.mock
async def test_valhalla_gecisi(istemci):
    rota = respx.post("http://rota.test:8002/isochrone").mock(return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    _, anahtar = await proje_ac(istemci)
    b = {"X-Harita-Anahtar": anahtar}
    yanit = await istemci.post("/valhalla/isochrone", headers=b, json={"locations": [{"lat": 41.0, "lon": 28.9}], "costing": "auto",
                                                                      "contours": [{"time": 10}]})
    assert yanit.status_code == 200 and yanit.json()["type"] == "FeatureCollection" and rota.called
    assert (await istemci.post("/valhalla/bilinmeyen", headers=b, json={})).status_code == 404


async def test_adres_izni_yok(istemci, adres_tohum):
    _, anahtar = await proje_ac(istemci, servisler=["rota"])
    assert (await istemci.get("/v1/adres/ara?q=namik", headers={"X-Harita-Anahtar": anahtar})).status_code == 403
    assert (await istemci.post("/valhalla/route", headers={"X-Harita-Anahtar": anahtar}, json={})).status_code == 403
