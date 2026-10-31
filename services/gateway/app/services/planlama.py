"""Cok araçli / cok kuryeli rota planlama: sure-mesafe matrisi Valhalla'dan, cozum VROOM'dan.

Akis: tum konumlar tekillestirilir -> Valhalla'dan 50x50'lik bloklar halinde matris (paralel) -> VROOM'a hazir matrisle istek
-> sonuc araç bazinda duraklar, varis saatleri, toplam sure / mesafe; istenirse her aracin rota cizgisi Valhalla'dan.
Ulasilamayan hucreler cok buyuk maliyetle doldurulur (VROOM o atamadan kacinir, gorev atanamazsa "atanamayan" listesine duser).
"""

import asyncio
import logging

import httpx

from app.config import ayarlar
from app.schemas.harita import Nokta
from app.services import valhalla
from app.services.http import AltServisHatasi, AltServisYok, istemci

log = logging.getLogger(__name__)

BLOK = 50
ULASILAMAZ = 10_000_000


def _anahtar(n: Nokta) -> tuple[float, float]:
    """Konum tekillestirme anahtari (~1 m)."""
    return round(n.lat, 5), round(n.lon, 5)


async def tam_matris(konumlar: list[Nokta], maliyet: str) -> tuple[list[list[int]], list[list[int]]]:
    """N x N sure ve mesafe matrisi; Valhalla cift sinirini asmamak icin 50x50 bloklar ayni anda en fazla 4 istekle."""
    n = len(konumlar)
    sure = [[0] * n for _ in range(n)]
    mesafe = [[0] * n for _ in range(n)]
    kilit = asyncio.Semaphore(4)

    async def blok(i: int, j: int) -> None:
        async with kilit:
            m = await valhalla.matris(konumlar[i:i + BLOK], konumlar[j:j + BLOK], maliyet)
        for a, satir in enumerate(m["sure_sn"]):
            for b, deger in enumerate(satir):
                sure[i + a][j + b] = ULASILAMAZ if deger is None else round(deger)
                d = m["mesafe_m"][a][b]
                mesafe[i + a][j + b] = ULASILAMAZ if d is None else round(d)

    await asyncio.gather(*(blok(i, j) for i in range(0, n, BLOK) for j in range(0, n, BLOK)))
    for k in range(n):
        sure[k][k] = mesafe[k][k] = 0
    return sure, mesafe


async def coz(istek, maliyet: str) -> dict:  # noqa: ANN001  (PlanIstek, dongusel ice aktarmayi onlemek icin tipsiz)
    """Planlama istegini cozer ve sade bir yanit dondurur."""
    konumlar: list[Nokta] = []
    indeks: dict[tuple[float, float], int] = {}

    def yer(n: Nokta) -> int:
        k = _anahtar(n)
        if k not in indeks:
            indeks[k] = len(konumlar)
            konumlar.append(n)
        return indeks[k]

    araclar, gorevler, gonderiler = [], [], []
    arac_kimlik, gorev_kimlik, gonderi_kimlik = {}, {}, {}
    for i, a in enumerate(istek.araclar, 1):
        v = {"id": i, "profile": "car", "start_index": yer(a.baslangic)}
        if a.bitis:
            v["end_index"] = yer(a.bitis)
        if a.kapasite:
            v["capacity"] = a.kapasite
        if a.beceriler:
            v["skills"] = a.beceriler
        if a.calisma:
            v["time_window"] = list(a.calisma)
        if a.maks_gorev:
            v["max_tasks"] = a.maks_gorev
        if a.maks_sure_sn:
            v["max_travel_time"] = a.maks_sure_sn
        araclar.append(v)
        arac_kimlik[i] = a.id
    for i, g in enumerate(istek.gorevler, 1):
        j = {"id": i, "location_index": yer(g.konum), "service": g.sure_sn}
        if g.miktar:
            j["delivery"] = g.miktar
        if g.beceriler:
            j["skills"] = g.beceriler
        if g.zaman_araliklari:
            j["time_windows"] = [list(z) for z in g.zaman_araliklari]
        if g.oncelik:
            j["priority"] = g.oncelik
        gorevler.append(j)
        gorev_kimlik[i] = g.id
    for i, s in enumerate(istek.gonderiler, 1):
        def ucu(u) -> dict:  # noqa: ANN001
            d = {"id": i, "location_index": yer(u.konum), "service": u.sure_sn}
            if u.zaman_araliklari:
                d["time_windows"] = [list(z) for z in u.zaman_araliklari]
            return d
        g = {"pickup": ucu(s.alim), "delivery": ucu(s.teslim)}
        if s.miktar:
            g["amount"] = s.miktar
        if s.beceriler:
            g["skills"] = s.beceriler
        if s.oncelik:
            g["priority"] = s.oncelik
        gonderiler.append(g)
        gonderi_kimlik[i] = s.id
    if len(konumlar) > ayarlar.PLAN_MAKS_NOKTA:
        raise ValueError(f"En fazla {ayarlar.PLAN_MAKS_NOKTA} farkli konum planlanabilir.")

    sure, mesafe = await tam_matris(konumlar, maliyet)
    govde = {"vehicles": araclar, "jobs": gorevler, "shipments": gonderiler,
             "matrices": {"car": {"durations": sure, "distances": mesafe}}}
    try:
        yanit = await istemci().post(ayarlar.PLAN_ADRESI, json=govde, timeout=60.0)
    except httpx.HTTPError as hata:
        log.error("Planlama servisine ulasilamadi: %s", type(hata).__name__)
        raise AltServisHatasi("planlama") from hata
    veri = yanit.json() if yanit.headers.get("content-type", "").startswith("application/json") else {}
    if yanit.status_code != 200 or veri.get("code", 0) != 0:
        log.error("Planlama hatasi %s: %s", yanit.status_code, str(veri.get("error") or yanit.text)[:300])
        if veri.get("code") == 2:  # gecersiz girdi
            raise ValueError("Plan girdisi gecersiz (kapasite, beceri ve zaman araliklarini kontrol edin).")
        raise AltServisHatasi("planlama")

    def konum_ver(adim: dict) -> dict:
        n = konumlar[adim["location_index"]]
        return {"lat": n.lat, "lon": n.lon}

    rotalar = []
    for r in veri.get("routes", []):
        duraklar = []
        for adim in r.get("steps", []):
            tur = {"start": "baslangic", "end": "bitis", "job": "gorev", "pickup": "alim", "delivery": "teslim", "break": "mola"}[adim["type"]]
            d = {"tur": tur, "konum": konum_ver(adim) if "location_index" in adim else None, "varis_sn": adim.get("arrival"),
                 "bekleme_sn": adim.get("waiting_time", 0), "hizmet_sn": adim.get("service", 0), "mesafe_m": adim.get("distance"),
                 "yuk": adim.get("load")}
            if tur == "gorev":
                d["gorev_id"] = gorev_kimlik[adim["id"]]
            elif tur in ("alim", "teslim"):
                d["gonderi_id"] = gonderi_kimlik[adim["id"]]
            duraklar.append(d)
        rotalar.append({"arac_id": arac_kimlik[r["vehicle"]], "duraklar": duraklar, "sure_sn": r.get("duration"),
                        "mesafe_m": r.get("distance"), "bekleme_sn": r.get("waiting_time"), "hizmet_sn": r.get("service")})
    if istek.geometri:
        await _geometriler(rotalar, maliyet)
    ozet = veri.get("summary", {})
    atanamayan = []
    for u in veri.get("unassigned", []):
        if u.get("type") == "job":
            atanamayan.append({"gorev_id": gorev_kimlik[u["id"]]})
        else:
            atanamayan.append({"gonderi_id": gonderi_kimlik[u["id"]]})
    # Ayni gonderinin alim ve teslimi iki kez listelenir
    atanamayan = [dict(t) for t in {tuple(a.items()) for a in atanamayan}]
    return {"rotalar": rotalar, "atanamayan": atanamayan,
            "ozet": {"sure_sn": ozet.get("duration"), "mesafe_m": ozet.get("distance"), "arac_sayisi": len(rotalar),
                     "atanamayan_sayisi": len(atanamayan)}}


async def _geometriler(rotalar: list[dict], maliyet: str) -> None:
    """Her araç rotasinin cizgisini (GeoJSON LineString) Valhalla'dan ekler; alinamazsa None."""
    kilit = asyncio.Semaphore(4)

    async def tek(r: dict) -> None:
        noktalar = [Nokta(**d["konum"]) for d in r["duraklar"] if d["konum"]]
        tekil = [n for i, n in enumerate(noktalar) if i == 0 or _anahtar(n) != _anahtar(noktalar[i - 1])]
        if len(tekil) < 2:
            r["geometri"] = None
            return
        try:
            async with kilit:
                veri = await valhalla.rota(tekil[: ayarlar.ROTA_MAKS_NOKTA], maliyet, "polyline6")
            r["geometri"] = valhalla.geojson_geometri(veri["routes"][0])
        except (AltServisHatasi, AltServisYok):
            log.warning("Plan rotasi cizgisi alinamadi (arac %s)", r["arac_id"])
            r["geometri"] = None

    await asyncio.gather(*(tek(r) for r in rotalar))
