"""HARITA canli duman testi: yayindaki karo, API, uyumlu uclar, yonetim ve deneme sayfalarini uctan uca dener.

Yalniz Python standart kutuphanesini kullanir; ek paket gerekmez.

Ortam degiskenleri:
    HARITA_ANAHTAR           Tum servislere izinli bir proje anahtari (zorunlu; or. kontrol anahtari)
    HARITA_YONETIM_ANAHTARI  Verilirse yonetim ve veritabani uclari da denenir
    HARITA_API               Varsayilan: https://harita-api.89.45.45.152.sslip.io
    HARITA_KARO              Varsayilan: https://harita-karo.89.45.45.152.sslip.io
    HARITA_DENEME            Varsayilan: https://harita-deneme.89.45.45.152.sslip.io (bos verilirse atlanir)

Kullanim:
    python scripts/canli-test.py

Cikis kodu: tum kontroller gecerse 0, en az biri basarisizsa 1. Anahtarlar ciktiya yazilmaz.
"""

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("HARITA_API", "https://harita-api.89.45.45.152.sslip.io").rstrip("/")
KARO = os.environ.get("HARITA_KARO", "https://harita-karo.89.45.45.152.sslip.io").rstrip("/")
DENEME = os.environ.get("HARITA_DENEME", "https://harita-deneme.89.45.45.152.sslip.io").rstrip("/")
ANAHTAR = os.environ.get("HARITA_ANAHTAR", "")
YONETIM = os.environ.get("HARITA_YONETIM_ANAHTARI", "")

# Ornek konumlar: Kadikoy iskele ve Moda (Istanbul)
A = {"lat": 40.9909, "lon": 29.0237}
B = {"lat": 40.9800, "lon": 29.0270}
C = {"lat": 40.9870, "lon": 29.0360}

sonuclar: list[tuple[str, bool, str, float]] = []


class Yanit:
    """Basit HTTP yaniti."""

    def __init__(self, durum: int, basliklar: dict, govde: bytes):
        self.durum = durum
        self.basliklar = {k.lower(): v for k, v in basliklar.items()}
        self.govde = govde

    def json(self):
        """Govdeyi JSON olarak cozer."""
        return json.loads(self.govde.decode("utf-8"))


def istek(yontem: str, adres: str, govde: dict | None = None, basliklar: dict | None = None, zaman_asimi: float = 30) -> Yanit:
    """HTTP istegi atar; hata kodlarinda da yaniti dondurur (istisna atmaz)."""
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    b = {"User-Agent": "harita-canli-test/1.0", **(basliklar or {})}
    if veri is not None:
        b["Content-Type"] = "application/json"
    r = urllib.request.Request(adres, data=veri, method=yontem, headers=b)
    try:
        with urllib.request.urlopen(r, timeout=zaman_asimi) as y:
            return Yanit(y.status, dict(y.headers), y.read())
    except urllib.error.HTTPError as h:
        return Yanit(h.code, dict(h.headers or {}), h.read() or b"")


def api(yontem: str, yol: str, govde: dict | None = None, **kw) -> Yanit:
    """Proje anahtariyla API istegi."""
    return istek(yontem, f"{API}{yol}", govde, {"X-Harita-Anahtar": ANAHTAR, **kw.pop("basliklar", {})}, **kw)


def yonetim(yontem: str, yol: str, govde: dict | None = None) -> Yanit:
    """Yonetim anahtariyla istek."""
    return istek(yontem, f"{API}{yol}", govde, {"X-Yonetim-Anahtari": YONETIM})


def kontrol(ad: str):
    """Bir kontrol fonksiyonunu calistirir; dondurdugu metin ayrintidir, AssertionError basarisizliktir."""

    def sar(islev):
        bas = time.monotonic()
        try:
            ayrinti = islev() or ""
            sonuclar.append((ad, True, str(ayrinti), time.monotonic() - bas))
        except AssertionError as h:
            sonuclar.append((ad, False, str(h), time.monotonic() - bas))
        except Exception as h:  # Ag hatasi vb. de basarisizlik sayilir ve raporlanir
            sonuclar.append((ad, False, f"{type(h).__name__}: {h}", time.monotonic() - bas))
        return islev

    return sar


def esit(y: Yanit, beklenen: int = 200) -> None:
    """Durum kodunu dogrular."""
    assert y.durum == beklenen, f"HTTP {y.durum} (beklenen {beklenen}): {y.govde[:160]!r}"


def karo_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    """Enlem / boylamdan web mercator karo numarasi."""
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


paylasim: dict = {}


def calistir() -> None:
    """Tum kontrolleri sirayla tanimlar ve calistirir."""

    # ---------- Karo servisi ----------
    @kontrol("karo: saglik")
    def _():
        esit(istek("GET", f"{KARO}/saglik"))

    @kontrol("karo: TileJSON")
    def _():
        y = istek("GET", f"{KARO}/tiles/turkiye.json")
        esit(y)
        tj = y.json()
        assert tj.get("tiles"), "tiles alani yok"
        return f"maxzoom {tj.get('maxzoom')}"

    @kontrol("karo: vektor karo (z14 Kadikoy)")
    def _():
        x, y_ = karo_xy(A["lat"], A["lon"], 14)
        y = istek("GET", f"{KARO}/tiles/turkiye/14/{x}/{y_}.mvt")
        esit(y)
        assert len(y.govde) > 1000, f"karo cok kucuk ({len(y.govde)} bayt)"
        return f"{len(y.govde)} bayt"

    @kontrol("karo: yazi tipi ve simge")
    def _():
        esit(istek("GET", f"{KARO}/assets/fonts/Noto%20Sans%20Regular/0-255.pbf"))
        esit(istek("GET", f"{KARO}/assets/sprites/v4/light.json"))

    @kontrol("karo: CORS izinli alan adlarina acik")
    def _():
        for koken in ("https://musteri.lezzetsepeti.net", "https://app.motoconvoy.net", "https://localhost", "capacitor://localhost"):
            y = istek("GET", f"{KARO}/tiles/turkiye.json", basliklar={"Origin": koken})
            assert y.basliklar.get("access-control-allow-origin") == koken, f"{koken}: ACAO={y.basliklar.get('access-control-allow-origin')}"

    @kontrol("karo: CORS yabanci alan adina kapali")
    def _():
        y = istek("GET", f"{KARO}/tiles/turkiye.json", basliklar={"Origin": "https://yabanci-site.example"})
        assert not y.basliklar.get("access-control-allow-origin"), "yabanci alan adina izin verildi"

    # ---------- Saglik ve anahtar kapisi ----------
    @kontrol("api: saglik")
    def _():
        esit(istek("GET", f"{API}/saglik"))

    @kontrol("api: hazirlik (veritabani, redis, rota, adres)")
    def _():
        y = istek("GET", f"{API}/saglik/hazir")
        esit(y)
        v = y.json()
        assert all(v.values()), f"hazir olmayan: {[k for k, d in v.items() if not d]}"
        return ", ".join(v)

    @kontrol("api: anahtarsiz istek 401")
    def _():
        esit(istek("GET", f"{API}/v1/yapilandirma"), 401)

    @kontrol("api: gecersiz anahtar 401")
    def _():
        esit(istek("GET", f"{API}/v1/yapilandirma", basliklar={"X-Harita-Anahtar": "hk_gecersiz_deneme_anahtari_0000"}), 401)

    @kontrol("api: CORS on kontrol (preflight)")
    def _():
        y = istek("OPTIONS", f"{API}/v1/rota", basliklar={
            "Origin": "https://ornek-proje.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-harita-anahtar,content-type"})
        esit(y)

    @kontrol("api: yapilandirma")
    def _():
        y = api("GET", "/v1/yapilandirma")
        esit(y)
        v = y.json()
        assert v["karo"]["adres"].startswith("http"), "karo adresi yok"
        return f"proje {v.get('proje')}"

    # ---------- Rota ----------
    for profil in ("auto", "motosiklet", "bisiklet", "yaya"):
        @kontrol(f"rota: /v1/rota {profil}")
        def _(profil=profil):
            y = api("POST", "/v1/rota", {"noktalar": [A, B], "profil": profil})
            esit(y)
            v = y.json()
            assert v["mesafe_m"] > 0 and v["geometri"]["type"] == "LineString", "rota bos"
            if profil == "auto":
                paylasim["cizgi"] = v["geometri"]["coordinates"]
            return f"{v['mesafe_m'] / 1000:.2f} km, {v['sure_sn'] / 60:.1f} dk"

    @kontrol("rota: /v1/matris 2x2")
    def _():
        y = api("POST", "/v1/matris", {"kaynaklar": [A, B], "hedefler": [B, C]})
        esit(y)
        v = y.json()
        assert len(v["sure_sn"]) == 2 and len(v["sure_sn"][0]) == 2, "matris boyutu yanlis"

    koordinat = f"{A['lon']},{A['lat']};{B['lon']},{B['lat']}"

    @kontrol("rota: OSRM uyumlu (baslikta anahtar)")
    def _():
        y = api("GET", f"/osrm/route/v1/driving/{koordinat}?overview=full&geometries=polyline")
        esit(y)
        v = y.json()
        assert v.get("code") == "Ok" and v["routes"][0]["distance"] > 0, f"code={v.get('code')}"

    @kontrol("rota: OSRM uyumlu (yolda anahtar)")
    def _():
        y = istek("GET", f"{API}/k/{urllib.parse.quote(ANAHTAR)}/osrm/route/v1/driving/{koordinat}")
        esit(y)
        assert y.json().get("code") == "Ok", "OSRM yaniti Ok degil"

    # ---------- Valhalla tam API ----------
    @kontrol("valhalla: route (Turkce talimat)")
    def _():
        y = api("POST", "/valhalla/route", {"locations": [A, B], "costing": "auto",
                                              "directions_options": {"language": "tr-TR", "units": "kilometers"}})
        esit(y)
        v = y.json()
        assert v["trip"]["language"] == "tr-TR", f"dil {v['trip'].get('language')}"
        paylasim["shape"] = v["trip"]["legs"][0]["shape"]
        return v["trip"]["legs"][0]["maneuvers"][1]["instruction"]

    @kontrol("valhalla: optimized_route")
    def _():
        esit(api("POST", "/valhalla/optimized_route", {"locations": [A, C, B], "costing": "auto"}))

    @kontrol("valhalla: sources_to_targets")
    def _():
        esit(api("POST", "/valhalla/sources_to_targets", {"sources": [A], "targets": [B, C], "costing": "auto"}))

    @kontrol("valhalla: isochrone")
    def _():
        y = api("POST", "/valhalla/isochrone", {"locations": [A], "costing": "auto", "contours": [{"time": 5}], "polygons": True})
        esit(y)
        assert y.json()["features"], "izokron bos"

    @kontrol("valhalla: trace_attributes (GPS izini yola oturtma)")
    def _():
        assert paylasim.get("shape"), "onceki route kontrolu basarisiz"
        y = api("POST", "/valhalla/trace_attributes", {"encoded_polyline": paylasim["shape"], "costing": "auto", "shape_match": "map_snap"})
        esit(y)
        return f"{len(y.json().get('edges', []))} yol parcasi"

    @kontrol("valhalla: locate")
    def _():
        esit(api("POST", "/valhalla/locate", {"locations": [A], "costing": "auto"}))

    @kontrol("valhalla: status")
    def _():
        esit(api("GET", "/valhalla/status"))

    @kontrol("valhalla: bilinmeyen uc 404")
    def _():
        esit(api("POST", "/valhalla/yok", {}), 404)

    # ---------- Arama ----------
    @kontrol("arama: /v1/arama")
    def _():
        y = api("GET", "/v1/arama?" + urllib.parse.urlencode({"q": "kadıköy", "lat": A["lat"], "lon": A["lon"]}))
        esit(y)
        f = y.json()["features"]
        assert f, "sonuc yok"
        return f[0]["properties"].get("name")

    @kontrol("arama: /v1/ters-arama")
    def _():
        y = api("GET", f"/v1/ters-arama?lat={A['lat']}&lon={A['lon']}")
        esit(y)
        assert y.json()["features"], "sonuc yok"

    # ---------- Yerlesim ----------
    @kontrol("yerlesim: ara (ilce)")
    def _():
        y = api("GET", "/v1/yerlesim/ara?" + urllib.parse.urlencode({"q": "kadıköy", "tur": "ilce"}))
        esit(y)
        v = y.json()
        assert v, "ilce bulunamadi"
        paylasim["ilce"] = v[0]["id"]
        return f"{v[0].get('ad')} (id {v[0]['id']})"

    @kontrol("yerlesim: getir + sinir")
    def _():
        esit(api("GET", f"/v1/yerlesim/{paylasim['ilce']}?sinir=true"))

    @kontrol("yerlesim: alt (mahalleler)")
    def _():
        y = api("GET", f"/v1/yerlesim/{paylasim['ilce']}/alt?tur=mahalle_koy")
        esit(y)
        v = y.json()
        assert v, "mahalle yok"
        paylasim["mahalle"] = v[0]["id"]
        return f"{len(v)} mahalle"

    @kontrol("yerlesim: nokta")
    def _():
        esit(api("GET", f"/v1/yerlesim/nokta?lat={A['lat']}&lon={A['lon']}"))

    @kontrol("yerlesim: yakin")
    def _():
        esit(api("GET", f"/v1/yerlesim/yakin?lat={A['lat']}&lon={A['lon']}"))

    # ---------- Adres ----------
    @kontrol("adres: ara (sokak / kapi)")
    def _():
        y = api("GET", "/v1/adres/ara?" + urllib.parse.urlencode({"q": "moda caddesi", "lat": A["lat"], "lon": A["lon"]}))
        esit(y)
        assert y.json(), "sonuc yok"

    @kontrol("adres: nokta (ters adres)")
    def _():
        y = api("GET", f"/v1/adres/nokta?lat={A['lat']}&lon={A['lon']}")
        esit(y)

    @kontrol("adres: mahalle sokaklari")
    def _():
        y = api("GET", f"/v1/adres/mahalle/{paylasim['mahalle']}/sokaklar")
        esit(y)
        v = y.json()
        assert v, "sokak yok"
        paylasim["sokak"] = v[0]["id"]
        return f"{len(v)} sokak"

    @kontrol("adres: sokak + cizgi")
    def _():
        esit(api("GET", f"/v1/adres/sokak/{paylasim['sokak']}?cizgi=true"))

    @kontrol("adres: sokak kapilari ve binalari")
    def _():
        esit(api("GET", f"/v1/adres/sokak/{paylasim['sokak']}/kapilar"))
        esit(api("GET", f"/v1/adres/sokak/{paylasim['sokak']}/binalar"))

    @kontrol("adres: mahalle binalari + bina")
    def _():
        y = api("GET", f"/v1/adres/mahalle/{paylasim['mahalle']}/binalar")
        esit(y)
        v = y.json()
        if v:
            esit(api("GET", f"/v1/adres/bina/{v[0]['id']}?sinir=true"))
        return f"{len(v)} bina"

    @kontrol("adres: alt agac (ilce > mahalle)")
    def _():
        y = api("GET", f"/v1/adres/alt?ust=ilce:{paylasim['ilce']}")
        esit(y)
        assert y.json(), "alt oge yok"

    @kontrol("adres: sekil (ilce siniri)")
    def _():
        esit(api("GET", f"/v1/adres/sekil?tur=ilce&id={paylasim['ilce']}"))

    @kontrol("adres: yer katmani (kutu ve karo)")
    def _():
        esit(api("GET", f"/v1/adres/yerler?bati=29.01&guney=40.98&dogu=29.04&kuzey=41.0"))
        x, y_ = karo_xy(A["lat"], A["lon"], 15)
        esit(api("GET", f"/v1/adres/yerler/karo?x={x}&y={y_}&z=15"))

    @kontrol("adres: yakin yerler (akaryakit)")
    def _():
        esit(api("GET", f"/v1/adres/yakin?lat={A['lat']}&lon={A['lon']}&tur=akaryakit"))

    @kontrol("adres: rota boyunca yerler")
    def _():
        assert paylasim.get("cizgi"), "onceki rota kontrolu basarisiz"
        esit(api("POST", "/v1/adres/rota-boyunca", {"koordinatlar": paylasim["cizgi"], "tampon_m": 300}))

    # ---------- Proje entegrasyonu icin eklenen uclar ----------
    @kontrol("adres: kapi aramasinda yakin olan once")
    def _():
        # Cerkezkoy'de bilinen bir kapi: yakinliktan bagimsiz ad cok yaygin (Ataturk Caddesi)
        n = api("GET", "/v1/adres/nokta?lat=41.2850&lon=28.0000").json()
        kapi = next((k for k in n.get("kapilar", []) if k["ek"].get("sokak")), None)
        assert kapi, "ornek kapi yok"
        q = f"{kapi['ek']['sokak']} {kapi['ek']['kapi_no']}"
        v = api("GET", "/v1/adres/ara?" + urllib.parse.urlencode({"q": q, "tur": "kapi", "lat": 41.285, "lon": 28.0})).json()
        mesafeler = [x["mesafe_m"] for x in v]
        assert mesafeler and mesafeler[0] < 1000, f"{q}: {mesafeler[:5]}"
        sinirli = api("GET", "/v1/adres/ara?" + urllib.parse.urlencode({"q": q, "tur": "kapi", "lat": 41.285, "lon": 28.0, "yaricap_m": 20000})).json()
        assert all(x["mesafe_m"] <= 20000 for x in sinirli), "yaricap siniri uygulanmadi"
        return f"{q}: {len(v)} sonuc, ilk {mesafeler[0]} m"

    @kontrol("adres: ilceye bagli (mahallesiz) sokaklar")
    def _():
        y = api("GET", f"/v1/adres/alt?ust=ilce:{paylasim['ilce']}&cocuk=sokak&limit=1000")
        esit(y)
        v = y.json()
        assert all(x["tur"] == "sokak" for x in v), "sokak disi oge dondu"
        return f"{len(v)} yol"

    @kontrol("adres: toplu getirme ve kaynak anahtari")
    def _():
        y = api("POST", "/v1/adres/toplu", {"ogeler": [{"tur": "sokak", "id": paylasim["sokak"]}, {"tur": "ilce", "id": paylasim["ilce"]}]})
        esit(y)
        v = y.json()
        assert len(v) == 2 and all(x.get("kaynak") for x in v), "kayit ya da kaynak anahtari eksik"
        k = api("POST", "/v1/adres/kaynak", {"anahtarlar": [x["kaynak"] for x in v]})
        esit(k)
        assert {(x["tur"], x["id"]) for x in k.json()} >= {(x["tur"], x["id"]) for x in v}, "kaynak anahtariyla eslesmedi"

    @kontrol("adres: sokaktaki en yakin kapi")
    def _():
        n = api("GET", "/v1/adres/nokta?lat=41.2850&lon=28.0000").json()
        kapi = next((k for k in n.get("kapilar", []) if k["ek"].get("sokak_id")), None)
        assert kapi, "sokaga bagli ornek kapi yok"
        y = api("GET", f"/v1/adres/sokak/{kapi['ek']['sokak_id']}/en-yakin-kapi?lat=41.2850&lon=28.0000&yaricap_m=200")
        esit(y)
        return f"{y.json()['ad']} ({y.json()['mesafe_m']} m)"

    @kontrol("rota: /v1/rota 30 durak")
    def _():
        noktalar = [{"lat": 40.985 + (i // 6) * 0.006, "lon": 29.035 + (i % 6) * 0.006} for i in range(30)]
        esit(api("POST", "/v1/rota", {"noktalar": noktalar, "profil": "motosiklet", "geometri": False}))

    @kontrol("yol: konumdaki yol bilgisi")
    def _():
        y = api("GET", "/v1/yol/nokta?lat=41.0369&lon=28.9850")
        esit(y)
        v = y.json()
        assert v["yol"]["sinif"] and v["il"], "yol sinifi ya da il yok"
        return f"{v['yol']['adlar'][:1]} {v['yol']['sinif']}, isik={v['yol']['trafik_isigi']}, {v['ilce']}"

    @kontrol("yol: harita baglantisi cozme")
    def _():
        y = api("GET", "/v1/baglanti/coz?" + urllib.parse.urlencode({"adres": "https://www.google.com/maps/dir/41.0082,28.9784/40.9909,29.0237/"}))
        esit(y)
        assert len(y.json()["noktalar"]) == 2, "nokta sayisi yanlis"
        esit(api("GET", "/v1/baglanti/coz?" + urllib.parse.urlencode({"adres": "https://yabanci.example/x"})), 422)

    # ---------- Uyumlu uclar ----------
    @kontrol("uyumlu: Nominatim search + reverse")
    def _():
        esit(api("GET", "/nominatim/search?" + urllib.parse.urlencode({"q": "kadıköy"})))
        esit(api("GET", f"/nominatim/reverse?lat={A['lat']}&lon={A['lon']}"))

    @kontrol("uyumlu: Photon api + reverse")
    def _():
        esit(api("GET", "/photon/api?" + urllib.parse.urlencode({"q": "kadıköy"})))
        esit(api("GET", f"/photon/reverse?lat={A['lat']}&lon={A['lon']}"))

    # ---------- Yonetim ----------
    if YONETIM:
        @kontrol("yonetim: anahtarsiz 401")
        def _():
            esit(istek("GET", f"{API}/yonetim/projeler"), 401)

        @kontrol("yonetim: proje listesi")
        def _():
            y = yonetim("GET", "/yonetim/projeler")
            esit(y)
            return f"{len(y.json())} proje"

        @kontrol("yonetim: veritabani ozeti")
        def _():
            esit(yonetim("GET", "/yonetim/veritabani/ozet"))

        @kontrol("yonetim: salt okunur SQL okur, yazmayi reddeder")
        def _():
            okuma = yonetim("POST", "/yonetim/veritabani/sql", {"sorgu": "SELECT 1 AS bir"})
            esit(okuma)  # alan adi dogru mu: okuma 200 donmeli, yoksa asagidaki red yanlis nedenle gecer
            # Kabul edilse bile zararsiz: oturuma ozel gecici tablo (canli veriye dokunmaz)
            y = yonetim("POST", "/yonetim/veritabani/sql", {"sorgu": "CREATE TEMP TABLE canli_test_gecici (x int)"})
            assert y.durum >= 400 and y.durum != 422, f"yazma sorgusu reddedilmedi ya da istek gecersiz (HTTP {y.durum})"

    # ---------- Deneme sayfalari ----------
    if DENEME:
        for sayfa in ("index.html", "navigasyon.html", "veritabani.html", "surum.json"):
            @kontrol(f"deneme: {sayfa}")
            def _(sayfa=sayfa):
                y = istek("GET", f"{DENEME}/{sayfa}")
                esit(y)
                assert "no-cache" in y.basliklar.get("cache-control", ""), "onbellek basligi yok"

        @kontrol("deneme: yapilandirma.json onbelleklenmez ve anahtarlar dolu")
        def _():
            y = istek("GET", f"{DENEME}/yapilandirma.json")
            esit(y)
            assert "no-store" in y.basliklar.get("cache-control", ""), "no-store yok"
            v = y.json()
            assert len(v.get("anahtar", "")) >= 16 and len(v.get("mtAnahtar", "")) >= 16, "anahtar eksik"


def main() -> int:
    """Testleri calistirir, tabloyu yazar, sonuca gore cikis kodu dondurur."""
    if not ANAHTAR:
        print("HARITA_ANAHTAR ortam degiskeni gerekli.", file=sys.stderr)
        return 2
    calistir()
    genislik = max(len(s[0]) for s in sonuclar)
    for ad, tamam, ayrinti, sure in sonuclar:
        print(f"{'GECTI ' if tamam else 'HATA  '} {ad.ljust(genislik)}  {sure * 1000:6.0f} ms  {ayrinti[:110]}")
    basarisiz = [s for s in sonuclar if not s[1]]
    print(f"\n{len(sonuclar) - len(basarisiz)}/{len(sonuclar)} kontrol gecti.")
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(main())
