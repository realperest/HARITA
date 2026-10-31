"""Anahtar kapisi, izin, kaynak, kota, OSRM uyumu ve yonetim akisi testleri."""

import uuid

import httpx
import pytest
import respx

pytestmark = pytest.mark.asyncio(loop_scope="session")

YONETIM = {"X-Yonetim-Anahtari": "test-yonetim"}

VALHALLA_OSRM_YANITI = {
    "code": "Ok",
    "routes": [{"duration": 123.4, "distance": 4567.8,
                "geometry": {"type": "LineString", "coordinates": [[28.97, 41.01], [28.98, 41.02]]}, "legs": []}],
    "waypoints": [],
}


async def proje_ac(istemci, **ek) -> tuple[int, str]:
    govde = {"ad": f"test-{uuid.uuid4().hex[:8]}", **ek}
    yanit = await istemci.post("/yonetim/projeler", json=govde, headers=YONETIM)
    assert yanit.status_code == 201, yanit.text
    return yanit.json()["proje_id"], yanit.json()["anahtar"]


async def test_saglik(istemci):
    assert (await istemci.get("/saglik")).json() == {"durum": "ok"}


async def test_yonetim_anahtarsiz_reddedilir(istemci):
    assert (await istemci.get("/yonetim/projeler")).status_code == 401


async def test_anahtarsiz_ve_yanlis_anahtar(istemci):
    assert (await istemci.get("/v1/yapilandirma")).status_code == 401
    assert (await istemci.get("/v1/yapilandirma", headers={"X-Harita-Anahtar": "hk_yanlis"})).status_code == 401


async def test_yapilandirma(istemci):
    _, anahtar = await proje_ac(istemci)
    yanit = await istemci.get("/v1/yapilandirma", headers={"X-Harita-Anahtar": anahtar})
    assert yanit.status_code == 200
    assert yanit.json()["karo"]["adres"] == "https://karo.test/tiles/turkiye/{z}/{x}/{y}.mvt"


@respx.mock
async def test_rota_ve_osrm_uyumu(istemci):
    respx.post("http://rota.test:8002/route").mock(return_value=httpx.Response(200, json=VALHALLA_OSRM_YANITI))
    _, anahtar = await proje_ac(istemci)
    baslik = {"X-Harita-Anahtar": anahtar}

    kendi = await istemci.post("/v1/rota", headers=baslik, json={"noktalar": [{"lat": 41.0, "lon": 28.9}, {"lat": 41.1, "lon": 29.0}]})
    assert kendi.status_code == 200
    assert kendi.json()["sure_sn"] == 123.4 and kendi.json()["geometri"]["type"] == "LineString"

    osrm = await istemci.get("/osrm/route/v1/driving/28.9,41.0;29.0,41.1?overview=simplified&geometries=geojson", headers=baslik)
    assert osrm.status_code == 200 and osrm.json()["code"] == "Ok" and "geometry" in osrm.json()["routes"][0]

    sade = await istemci.get(f"/k/{anahtar}/osrm/route/v1/driving/28.9,41.0;29.0,41.1?overview=false")
    assert sade.status_code == 200 and "geometry" not in sade.json()["routes"][0]

    kotu = await istemci.get("/osrm/route/v1/ucak/28.9,41.0;29.0,41.1", headers=baslik)
    assert kotu.status_code == 400 and kotu.json()["code"] == "InvalidQuery"


@respx.mock
async def test_rota_bulunamadi(istemci):
    respx.post("http://rota.test:8002/route").mock(return_value=httpx.Response(400, json={"error_code": 442}))
    _, anahtar = await proje_ac(istemci)
    yanit = await istemci.get("/osrm/route/v1/driving/28.9,41.0;29.0,41.1", headers={"X-Harita-Anahtar": anahtar})
    assert yanit.status_code == 400 and yanit.json()["code"] == "NoRoute"


@respx.mock
async def test_matris(istemci):
    respx.post("http://rota.test:8002/sources_to_targets").mock(return_value=httpx.Response(200, json={
        "sources_to_targets": [[{"time": 60, "distance": 1.5}, {"time": None, "distance": None}]]}))
    _, anahtar = await proje_ac(istemci)
    yanit = await istemci.post("/v1/matris", headers={"X-Harita-Anahtar": anahtar}, json={
        "kaynaklar": [{"lat": 41.0, "lon": 28.9}], "hedefler": [{"lat": 41.1, "lon": 29.0}, {"lat": 41.2, "lon": 29.1}]})
    assert yanit.status_code == 200
    assert yanit.json() == {"sure_sn": [[60, None]], "mesafe_m": [[1500.0, None]]}


async def test_arama(istemci):
    _, anahtar = await proje_ac(istemci)
    yanit = await istemci.get("/v1/arama?q=kadikoy", headers={"X-Harita-Anahtar": anahtar})
    assert yanit.status_code == 200 and yanit.json()["type"] == "FeatureCollection"
    assert (await istemci.get("/v1/arama?q=k", headers={"X-Harita-Anahtar": anahtar})).status_code == 422
    assert (await istemci.get("/v1/ters-arama?lat=41&lon=28", headers={"X-Harita-Anahtar": anahtar})).json()["type"] == "FeatureCollection"


async def test_servis_izni_yok(istemci):
    _, anahtar = await proje_ac(istemci, servisler=["yapilandirma"])
    yanit = await istemci.get("/v1/arama?q=kadikoy", headers={"X-Harita-Anahtar": anahtar})
    assert yanit.status_code == 403


async def test_kaynak_kisiti(istemci):
    _, anahtar = await proje_ac(istemci, kaynaklar=["https://izinli.example.com"])
    baslik = {"X-Harita-Anahtar": anahtar}
    assert (await istemci.get("/v1/yapilandirma", headers={**baslik, "Origin": "https://baska.example.com"})).status_code == 403
    assert (await istemci.get("/v1/yapilandirma", headers={**baslik, "Origin": "https://izinli.example.com"})).status_code == 200
    assert (await istemci.get("/v1/yapilandirma", headers=baslik)).status_code == 200  # sunucudan sunucuya (Origin yok)


async def test_kota(istemci):
    _, anahtar = await proje_ac(istemci, dakika_limiti=2)
    baslik = {"X-Harita-Anahtar": anahtar}
    kodlar = [(await istemci.get("/v1/yapilandirma", headers=baslik)).status_code for _ in range(3)]
    assert kodlar == [200, 200, 429]


async def test_anahtar_iptal_ve_pasif_proje(istemci):
    proje_id, anahtar = await proje_ac(istemci)
    baslik = {"X-Harita-Anahtar": anahtar}
    assert (await istemci.get("/v1/yapilandirma", headers=baslik)).status_code == 200

    ek = await istemci.post(f"/yonetim/projeler/{proje_id}/anahtarlar", headers=YONETIM)
    assert ek.status_code == 201
    on_ek = anahtar[:10]
    assert (await istemci.delete(f"/yonetim/projeler/{proje_id}/anahtarlar/{on_ek}", headers=YONETIM)).status_code == 200
    assert (await istemci.get("/v1/yapilandirma", headers=baslik)).status_code == 401

    yeni = {"X-Harita-Anahtar": ek.json()["anahtar"]}
    assert (await istemci.get("/v1/yapilandirma", headers=yeni)).status_code == 200
    assert (await istemci.patch(f"/yonetim/projeler/{proje_id}", headers=YONETIM, json={"aktif": False})).status_code == 200
    assert (await istemci.get("/v1/yapilandirma", headers=yeni)).status_code == 401


async def test_kullanim_sayaci(istemci):
    proje_id, anahtar = await proje_ac(istemci)
    for _ in range(3):
        await istemci.get("/v1/yapilandirma", headers={"X-Harita-Anahtar": anahtar})
    kullanim = (await istemci.get(f"/yonetim/projeler/{proje_id}/kullanim", headers=YONETIM)).json()
    assert kullanim and kullanim[0]["servis"] == "yapilandirma" and kullanim[0]["adet"] == 3


async def test_yeni_servis_mevcut_projelere_otomatik_acilir(istemci):
    """Sonradan eklenen servis, mevcut tum projelere bir kez acilir; yeni projeler her servisle baslar."""
    from app import db
    proje_id, _ = await proje_ac(istemci, servisler=["rota"])
    kod = "test_" + uuid.uuid4().hex[:6]
    async with db.havuz().acquire() as baglanti:
        servis_id = await baglanti.fetchval("INSERT INTO tnm_servis (id, kod, ad) VALUES ((SELECT max(id) + 1 FROM tnm_servis), $1, 'test') RETURNING id", kod)
        await db._yeni_servisleri_ac(baglanti)
        assert await baglanti.fetchval("SELECT 1 FROM proje_servis_izni WHERE proje_id = $1 AND servis_id = $2", proje_id, servis_id) == 1
        # yonetici izni kaldirirsa sonraki acilista geri eklenmez
        await baglanti.execute("DELETE FROM proje_servis_izni WHERE proje_id = $1 AND servis_id = $2", proje_id, servis_id)
        await db._yeni_servisleri_ac(baglanti)
        assert await baglanti.fetchval("SELECT 1 FROM proje_servis_izni WHERE proje_id = $1 AND servis_id = $2", proje_id, servis_id) is None
        await baglanti.execute("DELETE FROM sema_gocu WHERE ad = $1", "servis_otomatik_" + kod)
        await baglanti.execute("DELETE FROM proje_servis_izni WHERE servis_id = $1", servis_id)
        await baglanti.execute("DELETE FROM tnm_servis WHERE id = $1", servis_id)
    # servisler verilmeyen yeni proje tum servisleri alir
    yeni_id, _ = await proje_ac(istemci)
    async with db.havuz().acquire() as baglanti:
        eksik = await baglanti.fetchval(
            "SELECT count(*) FROM tnm_servis s WHERE NOT EXISTS (SELECT 1 FROM proje_servis_izni i WHERE i.proje_id = $1 AND i.servis_id = s.id)", yeni_id)
    assert eksik == 0
