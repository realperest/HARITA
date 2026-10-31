"""Ek ozellikler: yol uyarilari (hiz kamerasi / hiz kesici), ortak kapi numarasi havuzu, paylasim kodu, GPX, rota boyunca hava, cok araçli planlama, trafik profili ve canli konum."""

import json
import math
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
import respx

from app import cache

from app.db import havuz
from tests.test_adres import adres_tohum, baslik  # noqa: F401
from tests.test_yerlesim import tohum  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def uyari_tohum():
    """Dogu-bati bir rota uzerinde iki kamera, bir kasis ve rotadan uzak bir kamera."""
    async with havuz().acquire() as b:
        surum = await b.fetchval("INSERT INTO yol_uyari_surum (durum_id) SELECT id FROM tnm_islem_durumu WHERE kod = 'tamam' RETURNING id")
        for anahtar, tur, lon, lat, hiz in [("test:u:1", 1, 27.802, 41.1600, 50), ("test:u:2", 1, 27.808, 41.16005, 70),
                                            ("test:u:3", 2, 27.805, 41.1601, None), ("test:u:4", 1, 27.805, 41.17, 50)]:
            await b.execute(
                """INSERT INTO yol_uyari (kaynak_anahtari, tur_id, konum, hiz_siniri, surum_id)
                   VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, $5, $6)
                   ON CONFLICT (kaynak_anahtari) DO UPDATE SET aktif_mi = TRUE""", anahtar, tur, lon, lat, hiz, surum)
    yield
    async with havuz().acquire() as b:
        await b.execute("UPDATE yol_uyari SET aktif_mi = FALSE WHERE kaynak_anahtari LIKE 'test:u:%'")


async def test_rota_boyunca_uyarilar(istemci, uyari_tohum):
    b = await baslik(istemci)
    v = (await istemci.post("/v1/yol/uyarilar", headers=b, json={"noktalar": [[41.16, 27.80], [41.16, 27.81]]})).json()
    turler = [(u["tur"], u["hiz_siniri_kmh"]) for u in v["uyarilar"]]
    assert turler == [("hiz_kamerasi", 50), ("hiz_kesici", None), ("hiz_kamerasi", 70)]
    assert 150 < v["uyarilar"][0]["rota_m"] < 190 and v["uyarilar"][0]["rota_m"] < v["uyarilar"][2]["rota_m"]
    yalniz = (await istemci.post("/v1/yol/uyarilar", headers=b, json={"noktalar": [[41.16, 27.80], [41.16, 27.81]],
                                                                       "turler": ["hiz_kamerasi"]})).json()
    assert len(yalniz["uyarilar"]) == 2
    # Valhalla polyline6 ile ayni sonuc: (41.16, 27.80) -> (41.16, 27.81)
    poli = "_seomA_{w_t@?_pR"
    assert len((await istemci.post("/v1/yol/uyarilar", headers=b, json={"polyline": poli})).json()["uyarilar"]) == 3
    assert (await istemci.post("/v1/yol/uyarilar", headers=b, json={"turler": ["x"], "noktalar": [[41, 27], [41, 28]]})).status_code == 422
    assert (await istemci.post("/v1/yol/uyarilar", headers=b, json={})).status_code == 422


async def test_kutudaki_uyarilar(istemci, uyari_tohum):
    b = await baslik(istemci)
    v = (await istemci.get("/v1/yol/uyarilar?kutu=27.79,41.15,27.82,41.18", headers=b)).json()
    assert len([u for u in v["uyarilar"] if u["kaynak"].startswith("test:u:")]) == 4
    assert (await istemci.get("/v1/yol/uyarilar?kutu=20,30,40,50", headers=b)).status_code == 422


async def test_kapi_havuzu(istemci, adres_tohum):  # noqa: F811
    sokak = adres_tohum["sokak"]
    async with havuz().acquire() as b:
        await b.execute("DELETE FROM kapi_ogrenilen WHERE sokak_id = $1", sokak)
    b1, b2 = await baslik(istemci), await baslik(istemci)
    metin = {"metin": "namik kemal bulvari no 48 corlu"}
    once = (await istemci.post("/v1/adres/ayristir", headers=b1, json=metin)).json()
    assert once["parcalar"]["kapi_no"]["durum"] == "bulunamadi"
    # OSM'de olan kapi havuza eklenmez; sokaga uzak konum reddedilir
    osm = (await istemci.post("/v1/adres/kapi-ogren", headers=b1, json={"sokak_id": sokak, "kapi_no": "12", "lat": 41.16, "lon": 27.805})).json()
    assert osm["durum"] == "osm_var"
    uzak = await istemci.post("/v1/adres/kapi-ogren", headers=b1, json={"sokak_id": sokak, "kapi_no": "48", "lat": 41.17, "lon": 27.805})
    assert uzak.status_code == 422
    ilk = (await istemci.post("/v1/adres/kapi-ogren", headers=b1, json={"sokak_id": sokak, "kapi_no": "48", "lat": 41.16035, "lon": 27.8058})).json()
    assert ilk["durum"] == "eklendi" and ilk["kapi"]["gozlem_sayisi"] == 1 and not ilk["kapi"]["guvenilir"]
    tek = (await istemci.post("/v1/adres/ayristir", headers=b1, json=metin)).json()
    assert tek["parcalar"]["kapi_no"]["durum"] == "tek_gozlem" and tek["parcalar"]["kapi_no"]["kaynak"] == "havuz" and tek["puan"] <= 84
    # Ikinci projeden ikinci gozlem: guvenilir; konum ortancadir
    iki = (await istemci.post("/v1/adres/kapi-ogren", headers=b2, json={"sokak_id": sokak, "kapi_no": "48", "lat": 41.16037, "lon": 27.80582,
                                                                         "dogruluk_m": 8})).json()
    assert iki["kapi"]["gozlem_sayisi"] == 2 and iki["kapi"]["proje_sayisi"] == 2 and iki["kapi"]["guvenilir"]
    assert abs(iki["kapi"]["konum"]["lat"] - 41.16036) < 0.0001
    son = (await istemci.post("/v1/adres/ayristir", headers=b1, json=metin)).json()
    assert son["parcalar"]["kapi_no"]["durum"] == "dogrulandi" and son["konum"]["kesinlik"] == "kapi" and son["puan"] >= 85
    yakin = (await istemci.get(f"/v1/adres/sokak/{sokak}/en-yakin-kapi?lat=41.1604&lon=27.8059&yaricap_m=30", headers=b1)).json()
    assert yakin["kapi_no"] == "48" and yakin["kaynak"] == "havuz"
    assert len((await istemci.get(f"/v1/adres/sokak/{sokak}/ogrenilen-kapilar", headers=b1)).json()) == 1
    # Geri alma yalniz kendi gozlemini siler
    kapi_id = iki["kapi"]["id"]
    assert (await istemci.delete(f"/v1/adres/kapi-ogren/{kapi_id}", headers=b2)).json()["geri_alindi"]
    assert (await istemci.delete(f"/v1/adres/kapi-ogren/{kapi_id}", headers=b2)).status_code == 404
    kalan = (await istemci.get(f"/v1/adres/sokak/{sokak}/ogrenilen-kapilar", headers=b1)).json()
    assert kalan[0]["gozlem_sayisi"] == 1
    assert (await istemci.delete(f"/v1/adres/kapi-ogren/{kapi_id}", headers=b1)).json()["geri_alindi"]
    assert (await istemci.get(f"/v1/adres/sokak/{sokak}/ogrenilen-kapilar", headers=b1)).json() == []


async def test_paylasim_kodu(istemci):
    b, baska = await baslik(istemci), await baslik(istemci)
    v = (await istemci.post("/v1/paylasim", headers=b, json={"ad": "Teslimat", "profil": "motosiklet", "sure_saat": 2,
                                                             "duraklar": [{"lat": 41.16, "lon": 27.8, "ad": "Depo"}, {"lat": 41.17, "lon": 27.81}]})).json()
    assert len(v["kod"]) == 8 and "0" not in v["kod"] and "O" not in v["kod"]
    acilan = (await istemci.get(f"/v1/paylasim/{v['kod'].lower()}", headers=baska)).json()
    assert acilan["profil"] == "motosiklet" and acilan["duraklar"][0]["ad"] == "Depo" and acilan["acilma_sayisi"] == 1
    assert (await istemci.delete(f"/v1/paylasim/{v['kod']}", headers=baska)).status_code == 404  # baska proje silemez
    assert (await istemci.delete(f"/v1/paylasim/{v['kod']}", headers=b)).json()["silindi"]
    assert (await istemci.get(f"/v1/paylasim/{v['kod']}", headers=b)).status_code == 404
    assert (await istemci.post("/v1/paylasim", headers=b, json={"duraklar": [], "profil": "araba"})).status_code == 422
    assert (await istemci.post("/v1/paylasim", headers=b, json={"duraklar": [{"lat": 1, "lon": 1}], "profil": "uzay"})).status_code == 422


async def test_gpx_olustur_ve_oku(istemci):
    b = await baslik(istemci)
    y = await istemci.post("/v1/gpx/olustur", headers=b, json={"ad": "Çorlu turu <1>", "noktalar": [[41.16, 27.80], [41.165, 27.805], [41.17, 27.81]],
                                                               "duraklar": [{"lat": 41.16, "lon": 27.8, "ad": "A & B"}, {"lat": 41.17, "lon": 27.81}]})
    assert y.status_code == 200 and y.headers["content-type"].startswith("application/gpx+xml")
    assert 'filename="corlu-turu-1.gpx"' in y.headers["content-disposition"] and "A &amp; B" in y.text
    o = (await istemci.post("/v1/gpx/oku", headers=b, content=y.content)).json()
    assert o["ad"] == "Çorlu turu <1>" and len(o["izler"][0]) == 3 and o["duraklar"][0] == {"lat": 41.16, "lon": 27.8, "ad": "A & B"}
    # Yalniz iz iceren GPX: duraklar izin basi ve sonu
    iz = ('<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg><trkpt lat="41.1" lon="27.1"><ele>12</ele></trkpt>'
          '<trkpt lat="41.2" lon="27.2"/><trkpt lat="41.3" lon="27.3"/></trkseg></trk></gpx>')
    o2 = (await istemci.post("/v1/gpx/oku", headers=b, content=iz.encode())).json()
    assert [d["lat"] for d in o2["duraklar"]] == [41.1, 41.3] and o2["izler"][0][0]["yukseklik_m"] == 12
    kotu = '<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY a "x">]><gpx>&a;</gpx>'
    assert (await istemci.post("/v1/gpx/oku", headers=b, content=kotu.encode())).status_code == 422
    assert (await istemci.post("/v1/gpx/oku", headers=b, content=b"<html/>")).status_code == 422


def _saatlik(sicaklik: float, kod: int, hamle: float) -> dict:
    """Simdiden itibaren 48 saatlik sahte Open-Meteo yaniti."""
    bas = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    saatler = [(bas + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(48)]
    n = len(saatler)
    return {"hourly": {"time": saatler, "temperature_2m": [sicaklik] * n, "precipitation": [0.0] * n, "precipitation_probability": [10] * n,
                       "weather_code": [kod] * n, "wind_speed_10m": [12.0] * n, "wind_gusts_10m": [hamle] * n, "visibility": [20000.0] * n}}


@respx.mock
async def test_rota_boyunca_hava(istemci):
    b = await baslik(istemci)
    anahtarlar = [a async for a in cache.istemci().scan_iter("hava:*")]
    if anahtarlar:
        await cache.istemci().delete(*anahtarlar)

    def yanit(istek: httpx.Request) -> httpx.Response:
        # Bati yarisi acik, dogu yarisi karli ve ruzgarli; istenen her konum icin bir sonuc
        boylamlar = [float(x) for x in istek.url.params["longitude"].split(",")]
        return httpx.Response(200, json=[_saatlik(14.0, 1, 20.0) if x < 29.4 else _saatlik(-2.0, 73, 65.0) for x in boylamlar])

    rota = respx.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=yanit)
    # ~83 km: ornekler 10 km arayla; iki farkli 0,1 derecelik hucre grubu tek istekte
    govde = {"noktalar": [[41.0, 28.9], [41.0, 29.9]], "sure_sn": 3600}
    v = (await istemci.post("/v1/yol/hava", headers=b, json=govde)).json()
    assert rota.call_count == 1 and len(v["noktalar"]) >= 9
    assert v["noktalar"][0]["rota_m"] == 0 and v["noktalar"][-1]["rota_m"] > 80000
    assert v["noktalar"][0]["durum"] == "Az bulutlu" and v["noktalar"][0]["tahmin_var"]
    assert {"kar", "kuvvetli_ruzgar"} <= set(v["uyarilar"])
    # Ikinci istek onbellekten (yeni dis istek yok)
    await istemci.post("/v1/yol/hava", headers=b, json=govde)
    assert rota.call_count == 1
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(500))
    assert (await istemci.post("/v1/yol/hava", headers=b, json={"noktalar": [[38.0, 30.0], [38.0, 30.5]]})).status_code == 502


def _valhalla_matris(istek: httpx.Request) -> httpx.Response:
    """Kus ucusu mesafeden sahte Valhalla matrisi (30 km/sa)."""
    govde = json.loads(istek.content)

    def km(a: dict, b: dict) -> float:
        return math.hypot((a["lat"] - b["lat"]) * 111.0, (a["lon"] - b["lon"]) * 84.0)

    satirlar = [[{"distance": km(k, h), "time": km(k, h) / 30 * 3600} for h in govde["targets"]] for k in govde["sources"]]
    return httpx.Response(200, json={"sources_to_targets": satirlar})


def _plan_istegi() -> dict:
    """Iki kurye (bati ve dogu ucta), her uca yakin ikiser siparis, bir alim-teslim cifti ve kapasiteyi asan bir is."""
    return {"profil": "motosiklet", "araclar": [
        {"id": "bati", "baslangic": {"lat": 41.16, "lon": 27.70}, "kapasite": [10]},
        {"id": "dogu", "baslangic": {"lat": 41.16, "lon": 27.90}, "kapasite": [10]}],
        "gorevler": [{"id": "b1", "konum": {"lat": 41.16, "lon": 27.71}, "miktar": [1], "sure_sn": 120},
                     {"id": "b2", "konum": {"lat": 41.17, "lon": 27.72}, "miktar": [1]},
                     {"id": "d1", "konum": {"lat": 41.16, "lon": 27.89}, "miktar": [1]},
                     {"id": "d2", "konum": {"lat": 41.15, "lon": 27.88}, "miktar": [1]},
                     {"id": "agir", "konum": {"lat": 41.16, "lon": 27.80}, "miktar": [50]}],
        "gonderiler": [{"id": "s1", "alim": {"konum": {"lat": 41.16, "lon": 27.885}}, "teslim": {"konum": {"lat": 41.17, "lon": 27.895}},
                        "miktar": [2]}]}


@respx.mock
async def test_cok_kuryeli_planlama(istemci):
    b = await baslik(istemci)
    respx.post("http://rota.test:8002/sources_to_targets").mock(side_effect=_valhalla_matris)
    gercek = os.environ.get("PLAN_ADRESI")
    if gercek:
        respx.route(url__startswith=gercek).pass_through()
    else:
        respx.post("http://plan:3000").mock(return_value=httpx.Response(200, json={
            "code": 0, "summary": {"duration": 900, "distance": 7000},
            "unassigned": [{"id": 5, "type": "job"}],
            "routes": [
                {"vehicle": 1, "duration": 300, "distance": 2500, "steps": [
                    {"type": "start", "location_index": 0, "arrival": 0}, {"type": "job", "id": 1, "location_index": 2, "arrival": 100},
                    {"type": "job", "id": 2, "location_index": 3, "arrival": 300}, {"type": "end", "location_index": 3, "arrival": 300}]},
                {"vehicle": 2, "duration": 600, "distance": 4500, "steps": [
                    {"type": "start", "location_index": 1, "arrival": 0}, {"type": "job", "id": 3, "location_index": 4, "arrival": 120},
                    {"type": "pickup", "id": 1, "location_index": 7, "arrival": 200}, {"type": "job", "id": 4, "location_index": 5, "arrival": 300},
                    {"type": "delivery", "id": 1, "location_index": 8, "arrival": 600}, {"type": "end", "location_index": 8, "arrival": 600}]}]}))
    v = (await istemci.post("/v1/planla", headers=b, json=_plan_istegi())).json()
    atama = {r["arac_id"]: {d.get("gorev_id") or d.get("gonderi_id") for d in r["duraklar"]} - {None} for r in v["rotalar"]}
    assert atama["bati"] == {"b1", "b2"} and atama["dogu"] == {"d1", "d2", "s1"}
    assert v["atanamayan"] == [{"gorev_id": "agir"}] and v["ozet"]["arac_sayisi"] == 2
    dogu = next(r for r in v["rotalar"] if r["arac_id"] == "dogu")
    turler = [d["tur"] for d in dogu["duraklar"] if d.get("gonderi_id") == "s1"]
    assert turler == ["alim", "teslim"]
    kotu = _plan_istegi()
    kotu["gorevler"].append(dict(kotu["gorevler"][0]))
    assert (await istemci.post("/v1/planla", headers=b, json=kotu)).status_code == 422
    assert (await istemci.post("/v1/planla", headers=b, json={**_plan_istegi(), "profil": "uzay"})).status_code == 422


@respx.mock
async def test_en_yakin_kurye(istemci):
    b = await baslik(istemci)
    respx.post("http://rota.test:8002/sources_to_targets").mock(side_effect=_valhalla_matris)
    v = (await istemci.post("/v1/en-yakin", headers=b, json={"hedef": {"lat": 41.16, "lon": 27.80}, "adet": 2, "adaylar": [
        {"id": "uzak", "konum": {"lat": 41.16, "lon": 27.90}}, {"id": "yakin", "konum": {"lat": 41.161, "lon": 27.801}},
        {"id": "orta", "konum": {"lat": 41.17, "lon": 27.82}}]})).json()
    assert [a["id"] for a in v["adaylar"]] == ["yakin", "orta"] and v["adaylar"][0]["sure_sn"] < 60


def _esleme(istek: httpx.Request) -> httpx.Response:
    """Sahte trace_attributes: 5 kenar (yol 9001..9005), her biri 0,5 km; zamanli izde kenar basina 60 sn (30 km/sa)."""
    govde = json.loads(istek.content)
    zamanli = govde.get("use_timestamps")
    kenarlar = [{"way_id": 9000 + i, "length": 0.5, "speed": 50, "end_node": {"elapsed_time": i * 60.0 if zamanli else i * 36.0}}
                for i in range(1, 6)]
    return httpx.Response(200, json={"edges": kenarlar})


@respx.mock
async def test_trafik_profili(istemci):
    b = await baslik(istemci)
    async with havuz().acquire() as bag:
        await bag.execute("DELETE FROM trafik_hiz WHERE osm_yol_id BETWEEN 9001 AND 9005")
    anahtarlar = [a async for a in cache.istemci().scan_iter("trafik:900*")]
    if anahtarlar:
        await cache.istemci().delete(*anahtarlar)
    respx.post("http://rota.test:8002/trace_attributes").mock(side_effect=_esleme)
    simdi = datetime.now(timezone.utc).timestamp()
    iz = {"profil": "motosiklet", "noktalar": [{"lat": 41.16, "lon": 27.80 + i * 0.001, "zaman": simdi - 300 + i * 30} for i in range(10)]}
    for _ in range(3):
        v = (await istemci.post("/v1/trafik/iz", headers=b, json=iz)).json()
    # Ilk ve son kenar kismi sayilir: 9002, 9003, 9004 ogrenilir
    assert v["kaydedilen"] == 3
    async with havuz().acquire() as bag:
        s = await bag.fetchrow("SELECT ornek, ortalama FROM trafik_hiz WHERE osm_yol_id = 9003")
    assert s["ornek"] == 3 and abs(s["ortalama"] - 30) < 0.01
    tahmin = (await istemci.post("/v1/trafik/sure", headers=b, json={"noktalar": [[41.16, 27.80], [41.16, 27.83]]})).json()
    # 5 x 0,5 km: varsayilan 50 km/sa (180 sn); 3 kenar 30 km/sa (canli) -> 2 x 36 + 3 x 60 = 252 sn
    assert tahmin["valhalla_sure_sn"] == 180 and tahmin["tahmini_sure_sn"] == 252 and tahmin["kapsama"] == 0.6 and tahmin["canli_yol"] == 3
    sirasiz = {**iz, "noktalar": list(reversed(iz["noktalar"]))}
    assert (await istemci.post("/v1/trafik/iz", headers=b, json=sirasiz)).status_code == 422


async def test_canli_konum_ve_bolgeler(istemci):
    b = await baslik(istemci)
    bolgeler = [{"id": "depo", "ad": "Depo", "merkez": {"lat": 41.16, "lon": 27.80}, "yaricap_m": 100},
                {"id": "alan", "poligon": [[41.15, 27.85], [41.15, 27.87], [41.17, 27.87], [41.17, 27.85]]}]
    assert (await istemci.put("/v1/canli/kuryeler/bolgeler", headers=b, json=bolgeler)).json()["bolge_sayisi"] == 2
    assert len((await istemci.get("/v1/canli/kuryeler/bolgeler", headers=b)).json()) == 2
    git = lambda lat, lon: istemci.post("/v1/canli/kuryeler/konum", headers=b, json={"id": "k1", "lat": lat, "lon": lon})  # noqa: E731
    olay = lambda v: [(o["olay"], o["bolge"]) for o in v.json()["olaylar"] if o["tip"] == "bolge"]  # noqa: E731
    assert olay(await git(41.1601, 27.8001)) == [("giris", "depo")]
    assert olay(await git(41.1602, 27.8002)) == []
    assert olay(await git(41.16, 27.86)) == [("giris", "alan"), ("cikis", "depo")]
    son = (await istemci.get("/v1/canli/kuryeler/konumlar", headers=b)).json()
    assert len(son) == 1 and son[0]["id"] == "k1" and son[0]["bolgeler"] == ["alan"]
    # Kanallar projeye ozeldir
    baska = await baslik(istemci)
    assert (await istemci.get("/v1/canli/kuryeler/konumlar", headers=baska)).json() == []
    assert (await istemci.put("/v1/canli/kuryeler/bolgeler", headers=b, json=[{"id": "x", "merkez": {"lat": 1, "lon": 1}}])).status_code == 422
    assert (await istemci.get("/v1/canli/k%20x/konumlar", headers=b)).status_code == 422
