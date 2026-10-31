"""Proje entegrasyonu icin eklenen uclar: kapi aramasinda yakinlik, ilceye bagli sokaklar, toplu getirme, kaynak anahtari,
en yakin kapi, yol bilgisi ve harita baglantisi cozme."""

import httpx
import pytest
import pytest_asyncio
import respx

from app.db import havuz
from tests.test_adres import adres_tohum, baslik  # noqa: F401
from tests.test_yerlesim import tohum  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def uzak_tohum(adres_tohum):  # noqa: F811
    """Ayni adli (Namik Kemal Bulvari 12) uzak bir kapi ve mahallesiz, ilceye bagli bir yol tohumlar; sonda pasiflestirir
    (diger dosyalardaki konumsuz aramalarin sonucu degismesin)."""
    async with havuz().acquire() as b:
        ilce = await b.fetchval("SELECT ust_id FROM yerlesim WHERE id = $1", adres_tohum["mahalle"])
        uzak_sokak = await b.fetchval(
            """INSERT INTO sokak (kaynak_anahtari, ad, ad_arama, sinif_id, mahalle_id, cizgi, merkez)
               VALUES ('test:sokak:uzak', 'Namık Kemal Bulvarı', 'namik kemal bulvari', 3, NULL,
                       ST_GeogFromText('SRID=4326;MULTILINESTRING((39.90 41.00,39.91 41.00))'),
                       ST_SetSRID(ST_MakePoint(39.905, 41.0), 4326)::geography)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE RETURNING id""")
        await b.execute(
            """INSERT INTO kapi_numarasi (kaynak_anahtari, kapi_no, kapi_no_arama, sokak_ad, sokak_id, konum)
               VALUES ('osm:node:990001', '12', '12', 'Namık Kemal Bulvarı', $1, ST_SetSRID(ST_MakePoint(39.905, 41.0), 4326)::geography)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE, sokak_id = EXCLUDED.sokak_id""", uzak_sokak)
        ilce_yolu = await b.fetchval(
            """INSERT INTO sokak (kaynak_anahtari, ad, ad_arama, sinif_id, mahalle_id, ilce_id, cizgi, merkez)
               VALUES ('test:sokak:ilce', 'Çevre Yolu', 'cevre yolu', 3, NULL, $1,
                       ST_GeogFromText('SRID=4326;MULTILINESTRING((27.83 41.17,27.84 41.17))'),
                       ST_SetSRID(ST_MakePoint(27.835, 41.17), 4326)::geography)
               ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE, ilce_id = EXCLUDED.ilce_id RETURNING id""", ilce)
    yield {"uzak_sokak": uzak_sokak, "ilce_yolu": ilce_yolu, "ilce": ilce}
    async with havuz().acquire() as b:
        await b.execute("UPDATE sokak SET aktif_mi = FALSE WHERE kaynak_anahtari IN ('test:sokak:uzak', 'test:sokak:ilce')")
        await b.execute("UPDATE kapi_numarasi SET aktif_mi = FALSE WHERE kaynak_anahtari = 'osm:node:990001'")


async def test_kapi_aramasinda_yakin_olan_once(istemci, adres_tohum, uzak_tohum):  # noqa: F811
    b = await baslik(istemci)
    # Corlu yakininda: Corlu'daki kapi once; uzaktaki (Trabzon civari) sonra
    yakin = (await istemci.get("/v1/adres/ara?q=namik kemal bulvari 12&tur=kapi&lat=41.16&lon=27.805", headers=b)).json()
    assert yakin[0]["il"] == "Tekirdağ" and yakin[0]["mesafe_m"] < 1000 and yakin[1]["mesafe_m"] > 900000
    # Uzak noktanin yakininda sira tersine doner
    uzak = (await istemci.get("/v1/adres/ara?q=namik kemal bulvari 12&tur=kapi&lat=41.0&lon=39.905", headers=b)).json()
    assert uzak[0]["mesafe_m"] < 1000 and uzak[0]["kaynak"] == "osm:node:990001"
    # Yaricap siniri uzak sonucu eler
    sinirli = (await istemci.get("/v1/adres/ara?q=namik kemal bulvari 12&tur=kapi&lat=41.16&lon=27.805&yaricap_m=50000", headers=b)).json()
    assert len(sinirli) == 1 and sinirli[0]["il"] == "Tekirdağ"


async def test_ilceye_bagli_sokaklar(istemci, tohum, uzak_tohum):  # noqa: F811
    b = await baslik(istemci)
    liste = (await istemci.get(f"/v1/adres/alt?ust=ilce:{uzak_tohum['ilce']}&cocuk=sokak", headers=b)).json()
    assert [s["ad"] for s in liste] == ["Çevre Yolu"] and liste[0]["ilce"] == "Çorlu" and liste[0]["il"] == "Tekirdağ"
    assert liste[0]["ust"]["ilce_id"] == uzak_tohum["ilce"] and liste[0]["ust"]["mahalle_id"] is None
    # ilce filtresiyle aramada da bulunur
    ara = (await istemci.get(f"/v1/adres/ara?q=cevre yolu&tur=sokak&ust_id={uzak_tohum['ilce']}", headers=b)).json()
    assert ara and ara[0]["ad"] == "Çevre Yolu"
    # ilce > mahalle listesi degismedi
    assert [x["ad"] for x in (await istemci.get(f"/v1/adres/alt?ust=ilce:{uzak_tohum['ilce']}", headers=b)).json()] == ["Cumhuriyet Mahallesi"]


async def test_toplu_getirme(istemci, tohum, adres_tohum, uzak_tohum):  # noqa: F811
    b = await baslik(istemci)
    ogeler = [{"tur": "sokak", "id": adres_tohum["sokak"]}, {"tur": "bina", "id": adres_tohum["bina"]},
              {"tur": "mahalle_koy", "id": tohum["mahalle"]}, {"tur": "ilce", "id": tohum["ilce"]}, {"tur": "sokak", "id": 999999999}]
    v = (await istemci.post("/v1/adres/toplu", headers=b, json={"ogeler": ogeler})).json()
    turler = {(x["tur"], x["id"]): x for x in v}
    assert len(v) == 4 and ("sokak", 999999999) not in turler
    sokak = turler[("sokak", adres_tohum["sokak"])]
    assert sokak["ad"] == "Namık Kemal Bulvarı" and sokak["ust"]["mahalle_id"] == tohum["mahalle"] and sokak["ust"]["ilce_id"] == tohum["ilce"]
    assert turler[("bina", adres_tohum["bina"])]["ek"]["sokak_id"] == adres_tohum["sokak"]
    assert turler[("ilce", tohum["ilce"])]["ad"] == "Çorlu"
    assert (await istemci.post("/v1/adres/toplu", headers=b, json={"ogeler": []})).status_code == 422


async def test_kaynak_anahtariyla_esleme(istemci, adres_tohum, uzak_tohum):  # noqa: F811
    b = await baslik(istemci)
    v = (await istemci.post("/v1/adres/kaynak", headers=b, json={"anahtarlar": ["osm:node:990001", "test:yer:1", "yok:1"]})).json()
    assert {x["kaynak"] for x in v} == {"osm:node:990001", "test:yer:1"}
    kapi = next(x for x in v if x["tur"] == "kapi")
    assert kapi["ek"]["sokak_id"] == uzak_tohum["uzak_sokak"]
    # arama sonuclari da kaynak anahtarini tasir
    ara = (await istemci.get("/v1/adres/ara?q=deniz eczane&tur=yer", headers=b)).json()
    assert ara[0]["kaynak"] == "test:yer:1"


async def test_en_yakin_kapi(istemci, adres_tohum):  # noqa: F811
    b = await baslik(istemci)
    v = (await istemci.get(f"/v1/adres/sokak/{adres_tohum['sokak']}/en-yakin-kapi?lat=41.1601&lon=27.8051", headers=b)).json()
    assert v["ek"]["kapi_no"] == "12" and v["mesafe_m"] < 20
    yok = await istemci.get(f"/v1/adres/sokak/{adres_tohum['sokak']}/en-yakin-kapi?lat=41.20&lon=27.90&yaricap_m=50", headers=b)
    assert yok.status_code == 404


async def test_adres_ayristirma_ucu(istemci, tohum, adres_tohum):  # noqa: F811
    b = await baslik(istemci)
    v = (await istemci.post("/v1/adres/ayristir", headers=b, json={
        "metin": "cumhuriyet mh namık kemal blv. no 12 d 5 kat 2 güneş apt çorlu tekirdağ 0532 111 22 33"})).json()
    p = v["parcalar"]
    assert p["il"]["ad"] == "Tekirdağ" and p["ilce"]["ad"] == "Çorlu" and p["mahalle"]["ad"] == "Cumhuriyet Mahallesi"
    assert p["sokak"]["id"] == adres_tohum["sokak"] and p["kapi_no"]["durum"] == "dogrulandi" and p["daire"] == "5" and p["kat"] == "2"
    assert p["bina"]["id"] == adres_tohum["bina"]
    assert v["konum"]["kesinlik"] == "kapi" and v["puan"] == 100 and v["uyarilar"]
    assert v["duzgun"].startswith("Cumhuriyet Mahallesi, Namık Kemal Bulvarı No: 12")
    # Tek harf yazim hatasi uzun adda kesin sayilir; daha cok hata "benzer" olur ve puan onay onerecek kadar duser
    tek = (await istemci.post("/v1/adres/ayristir", headers=b, json={"metin": "Namk Kemal Bulvari no 12 corlu"})).json()
    assert tek["parcalar"]["sokak"]["id"] == adres_tohum["sokak"]
    hatali = (await istemci.post("/v1/adres/ayristir", headers=b, json={"metin": "Nmk Kemel Bulvari no 12 corlu"})).json()
    assert hatali["parcalar"]["sokak"]["id"] == adres_tohum["sokak"] and hatali["parcalar"]["sokak"]["durum"] == "benzer" and hatali["puan"] < 85
    assert any(o["alan"] == "sokak_yazimi" for o in hatali["oneriler"])
    # Baglam konumuyla ilce yazmadan
    baglamli = (await istemci.post("/v1/adres/ayristir", headers=b, json={"metin": "namik kemal bulvari 12", "lat": 41.16, "lon": 27.805})).json()
    assert baglamli["parcalar"]["kapi_no"]["durum"] == "dogrulandi"
    # Toplu
    liste = (await istemci.post("/v1/adres/ayristir", headers=b, json={"metinler": ["namik kemal bulvari 12 corlu", "olmayan sokak 5 corlu"]})).json()
    assert len(liste) == 2 and liste[0]["puan"] >= 85 and liste[1]["parcalar"]["sokak"]["durum"] in ("bulunamadi", "benzer")
    assert (await istemci.post("/v1/adres/ayristir", headers=b, json={})).status_code == 422


@respx.mock
async def test_baglanti_coz_kisa_baglanti(istemci):
    b = await baslik(istemci)
    respx.get("https://maps.app.goo.gl/abc").mock(return_value=httpx.Response(
        302, headers={"location": "https://www.google.com/maps/place/X/@41.0,29.0,15z/data=!3d41.0011!4d29.0022"}))
    v = (await istemci.get("/v1/baglanti/coz?adres=https://maps.app.goo.gl/abc", headers=b)).json()
    assert v["noktalar"] == [{"lat": 41.0011, "lon": 29.0022}]
    # izin verilmeyen alan adi ve izin disina yonlendirme reddedilir
    assert (await istemci.get("/v1/baglanti/coz?adres=https://ornek.example/x", headers=b)).status_code == 422
    respx.get("https://goo.gl/kotu").mock(return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}))
    assert (await istemci.get("/v1/baglanti/coz?adres=https://goo.gl/kotu", headers=b)).status_code == 422


@respx.mock
async def test_yol_bilgisi(istemci, tohum):  # noqa: F811
    b = await baslik(istemci)
    respx.post("http://rota.test:8002/locate").mock(return_value=httpx.Response(200, json=[{"edges": [{
        "distance": 3.2, "percent_along": 0.75,
        "edge": {"forward": True, "traffic_signal": True, "stop_sign": False, "toll": False, "tunnel": False, "bridge": False,
                 "lane_count": 2, "speeds": {"default": 50}, "geo_attributes": {"length": 200},
                 "classification": {"classification": "primary", "use": "road", "surface": "paved_smooth", "link": False}},
        "edge_info": {"names": ["Omurtak Caddesi"], "speed_limit": 50, "way_id": 123}}]}]))
    v = (await istemci.get("/v1/yol/nokta?lat=41.16&lon=27.805", headers=b)).json()
    yol = v["yol"]
    assert yol["sinif"] == "primary" and yol["trafik_isigi"] is True and yol["kavsaga_kalan_m"] == 50 and yol["hiz_siniri_kmh"] == 50
    assert yol["adlar"] == ["Omurtak Caddesi"] and v["ilce"] == "Çorlu"
    respx.post("http://rota.test:8002/locate").mock(return_value=httpx.Response(400, json={"error": "no edges"}))
    assert (await istemci.get("/v1/yol/nokta?lat=41.16&lon=27.805", headers=b)).status_code == 404
