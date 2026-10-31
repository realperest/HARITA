"""Veritabani araci uclari: yetki, tablo listesi, yapi, veri, maskeleme ve salt okunur SQL."""

import pytest

from tests.test_gateway import YONETIM, proje_ac

pytestmark = pytest.mark.asyncio(loop_scope="session")

TABAN = "/yonetim/veritabani"


async def test_anahtarsiz_reddedilir(istemci):
    assert (await istemci.get(f"{TABAN}/tablolar")).status_code == 401
    assert (await istemci.post(f"{TABAN}/sql", json={"sorgu": "select 1"})).status_code == 401


async def test_ozet_ve_tablolar(istemci):
    ozet = (await istemci.get(f"{TABAN}/ozet", headers=YONETIM)).json()
    assert ozet["tablo_adedi"] > 5 and ozet["motor"].startswith("PostgreSQL")
    tablolar = (await istemci.get(f"{TABAN}/tablolar", headers=YONETIM)).json()
    proje = next(t for t in tablolar if t["ad"] == "proje")
    assert proje["tur"] == "tablo" and proje["satir"] >= 0


async def test_yapi_birincil_ve_yabanci_anahtar(istemci):
    yapi = (await istemci.get(f"{TABAN}/tablo/proje_anahtar/yapi", headers=YONETIM)).json()
    kolonlar = {k["ad"]: k for k in yapi["kolonlar"]}
    assert kolonlar["id"]["birincil"] is True
    assert kolonlar["proje_id"]["yabanci"] == "proje.id"
    assert (await istemci.get(f"{TABAN}/tablo/yok_boyle_tablo/yapi", headers=YONETIM)).status_code == 422


async def test_veri_arama_filtre_ve_maskeleme(istemci):
    proje_id, _ = await proje_ac(istemci)
    yanit = (await istemci.get(f"{TABAN}/tablo/proje_anahtar/veri?kolon=proje_id&islem==&deger={proje_id}", headers=YONETIM)).json()
    assert yanit["toplam"] == 1
    ad = [k["ad"] for k in yanit["kolonlar"]]
    assert yanit["satirlar"][0][ad.index("anahtar_ozeti")] == "[gizli]"
    arama = (await istemci.get(f"{TABAN}/tablo/proje/veri?ara=test-", headers=YONETIM)).json()
    assert arama["toplam"] >= 1


async def test_gecersiz_kolon_ve_islem(istemci):
    assert (await istemci.get(f"{TABAN}/tablo/proje/veri?kolon=yok", headers=YONETIM)).status_code == 422
    assert (await istemci.get(f"{TABAN}/tablo/proje/veri?islem=drop", headers=YONETIM)).status_code == 422
    assert (await istemci.get(f"{TABAN}/tablo/proje/veri?sirala=ad;drop", headers=YONETIM)).status_code == 422


async def test_sql_salt_okunur(istemci):
    ok = await istemci.post(f"{TABAN}/sql", json={"sorgu": "SELECT 1 AS bir, 'a' AS iki;"}, headers=YONETIM)
    assert ok.status_code == 200 and ok.json()["satirlar"] == [[1, "a"]]
    for kotu in ("DELETE FROM proje", "SELECT 1; DROP TABLE proje", "UPDATE proje SET ad = 'x'"):
        assert (await istemci.post(f"{TABAN}/sql", json={"sorgu": kotu}, headers=YONETIM)).status_code == 422
    yazan = await istemci.post(f"{TABAN}/sql", json={"sorgu": "WITH x AS (DELETE FROM proje RETURNING 1) SELECT * FROM x"}, headers=YONETIM)
    assert yazan.status_code == 422
