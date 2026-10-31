"""Adres ayristirma kalite olcumu: gercek kayitlardan dagınık yazilmis adresler uretir, sonucu dogru kayitla karsilastirir.

Kullanim (gercek veri kesiti yuklu veritabaninda):
    DATABASE_URL=postgresql://.../harita_kesit python -m tests.ayristirma_olcum kesit.json [ornek_sayisi]
Cikti: bicim basina ve toplam dogruluk (ilce, mahalle, sokak, kapi). Basari olcutu: sokak ve kapi dogru.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from collections import defaultdict

TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
YOL_KISA = {"caddesi": ["cd.", "cad.", "cd", "caddesi", "cad"], "sokak": ["sk.", "sok.", "sk", "sokak", "sokağı"],
            "sokağı": ["sk.", "sok", "sokağı", "sokak"], "bulvarı": ["blv.", "bulvarı", "bulv."], "yolu": ["yolu", "yolu"]}
TARIFLER = ["market karşısı", "eczane yanı", "camii arkası", "okulun karşısı", "fırının yanı"]


def _kucuk(m: str) -> str:
    return m.replace("I", "ı").replace("İ", "i").lower()


def _buyuk(m: str) -> str:
    return m.replace("i", "İ").replace("ı", "I").upper()


def _yazim_hatasi(r: random.Random, kelime: str) -> str:
    """Tek harf eksilt / komsu harfleri degistir (uzun kelimelerde)."""
    if len(kelime) < 6:
        return kelime
    i = r.randrange(1, len(kelime) - 2)
    return kelime[:i] + kelime[i + 1:] if r.random() < 0.5 else kelime[:i] + kelime[i + 1] + kelime[i] + kelime[i + 2:]


def _sokak_parcala(ad: str) -> tuple[str, str]:
    """'Kumru Sokak' -> ('Kumru', 'sokak'); '194. Sokak' -> ('194.', 'sokak')."""
    parca = ad.split()
    tur = _kucuk(parca[-1]) if len(parca) > 1 else ""
    return (" ".join(parca[:-1]), tur) if tur in YOL_KISA else (ad, "")


def ornekler_uret(kesit: dict, adet: int, tohum: int = 7) -> list[dict]:
    """Gercek kapi kayitlarindan 8 farkli yazim bicimiyle ornek adresler."""
    r = random.Random(tohum)
    yerlesim = {y["id"]: y for y in kesit["yerlesim"]}
    sokaklar = {s["id"]: s for s in kesit["sokak"]}
    uygun = [k for k in kesit["kapi"] if k["sokak_id"] in sokaklar and k["mahalle_id"] in yerlesim
             and _sokak_parcala(sokaklar[k["sokak_id"]]["ad"])[1] and k["kapi_no"].isalnum()]
    # Ayni sokakta ayni numara birden cok kez varsa (veri tekrari) dogru kayit belirsiz; atlanir
    sayac = defaultdict(int)
    for k in uygun:
        sayac[(k["sokak_id"], k["kapi_no_arama"])] += 1
    uygun = [k for k in uygun if sayac[(k["sokak_id"], k["kapi_no_arama"])] == 1]
    secilen = r.sample(uygun, min(adet, len(uygun)))
    ornekler = []
    for k in secilen:
        sokak = sokaklar[k["sokak_id"]]
        mahalle = yerlesim[k["mahalle_id"]]
        ilce = yerlesim[mahalle["ust_id"]]
        il = yerlesim[ilce["ust_id"]]
        cekirdek, tur = _sokak_parcala(sokak["ad"])
        mah = mahalle["ad"].replace(" Mahallesi", "").replace(" Mah.", "")
        no = k["kapi_no"]
        d, kat = r.randint(1, 12), r.randint(1, 6)
        kisa = r.choice(YOL_KISA[tur])
        dogru = {"sokak": sokak["id"], "kapi": k["id"], "mahalle": mahalle["id"], "ilce": ilce["id"]}
        bicimler = {
            "resmi": f"{mah} Mah. {cekirdek} {kisa.capitalize()} No:{no} Daire {d} {ilce['ad']}/{il['ad']}",
            "kucuk_kisa": _kucuk(f"{mah} mh {cekirdek} {kisa} no {no} d {d} {ilce['ad']}"),
            "mahallesiz": f"{cekirdek} {kisa} No: {no} Kat {kat} {ilce['ad']} {il['ad']}",
            "turkcesiz": _kucuk(f"{mah} mah {cekirdek} {kisa} no {no} {ilce['ad']}").translate(TR_ASCII),
            "hatali_tarifli": f"{mah} mahallesi {' '.join(_yazim_hatasi(r, w) for w in cekirdek.split())} {kisa} no:{no} "
                              f"{r.choice(TARIFLER)} {ilce['ad']} 0532 {r.randint(100, 999)} {r.randint(10, 99)} {r.randint(10, 99)}",
            "karisik_sira": f"{ilce['ad']} {mah} mahallesi {cekirdek} {tur} {no} numara kat {kat}",
            "buyuk_harf": _buyuk(f"{cekirdek} {tur} no {no}/{d} {mah} mahallesi {ilce['ad']}"),
            "baglamli": f"{cekirdek} {kisa} {no}",
        }
        for bicim, metin in bicimler.items():
            baglam = {"lat": ilce["lat"], "lon": ilce["lon"]} if bicim == "baglamli" else {}
            ornekler.append({"bicim": bicim, "metin": metin, "baglam": baglam, "dogru": dogru, "konum": {"lat": k["lat"], "lon": k["lon"]}})
        # Olumsuz ornek: ayni mahallede olmayan bir sokak adi; "dogrulandi" denmemeli (yanlis eslesme olcumu)
        sahte = f"{r.choice(SAHTE_ADLAR)} {r.choice(SAHTE_ADLAR)}"
        ornekler.append({"bicim": "olmayan_sokak", "metin": f"{mah} Mah. {sahte} Sk. No:{no} {ilce['ad']}/{il['ad']}", "baglam": {},
                         "dogru": {**dogru, "sokak": None, "kapi": None}})
    return ornekler


SAHTE_ADLAR = ["Lalezar", "Gülistan", "Zümrütova", "Mercanköşk", "Akçaağaç", "Sırmakeş", "Firuzbent", "Yakutlu", "Nilüferhan", "Kehribarlı"]


def _mesafe(a: dict, b: dict) -> float:
    """Kisa mesafeler icin yaklasik metre (esdikdortgen izdusum)."""
    import math
    kx = 111320 * math.cos(math.radians(a["lat"]))
    return math.hypot((a["lon"] - b["lon"]) * kx, (a["lat"] - b["lat"]) * 110540)


async def olc(ornekler: list[dict]) -> dict:
    from app import db
    from app.crud.adres_ayristir import ayristir_ve_dogrula
    await db.baslat()
    sonuc = defaultdict(lambda: defaultdict(int))
    guven = defaultdict(int)
    hatalar = []
    try:
        for o in ornekler:
            v = await ayristir_ve_dogrula(o["metin"], o["baglam"])
            p = v["parcalar"]
            dogru = o["dogru"]
            satir = sonuc[o["bicim"]]
            satir["adet"] += 1
            satir["ilce"] += p["ilce"]["id"] == dogru["ilce"]
            satir["mahalle"] += p["mahalle"]["id"] == dogru["mahalle"]
            if o["bicim"] == "olmayan_sokak":
                # Basari: sokak kesin eslesmis sayilmadi (bulunamadi ya da en fazla 'benzer' oneri)
                satir["sokak"] += p["sokak"]["durum"] != "dogrulandi"
                satir["kapi"] += p["kapi_no"]["id"] is None
            else:
                # OSM'de ayni kapi / sokak birden cok kayitla girilebiliyor (nokta + bina, parca parca sokak):
                # dogruluk kayit kimligiyle ya da ayni numaranin 60 m icinde bulunmasiyla olculur
                kapi_dogru = p["kapi_no"]["id"] == dogru["kapi"] or (
                    p["kapi_no"]["id"] is not None and v["konum"] and _mesafe(v["konum"], o["konum"]) < 60)
                satir["sokak"] += p["sokak"]["id"] == dogru["sokak"] or kapi_dogru
                satir["kapi"] += kapi_dogru
            # Puan kalibrasyonu: 85 ve ustu "otomatik kabul edilebilir" sayilir
            if v["puan"] >= 85:
                guven["yuksek"] += 1
                guven["yuksek_yanlis"] += (o["bicim"] == "olmayan_sokak") or not kapi_dogru
            else:
                guven["dusuk"] += 1
            if (o["bicim"] == "olmayan_sokak" and p["sokak"]["durum"] == "dogrulandi") or \
                    (o["bicim"] != "olmayan_sokak" and not kapi_dogru):
                hatalar.append({"bicim": o["bicim"], "metin": o["metin"], "sokak": p["sokak"], "mahalle": p["mahalle"]["ad"],
                                "ilce": p["ilce"]["ad"], "kapi": p["kapi_no"], "puan": v["puan"]})
    finally:
        await db.kapat()
    return {"sonuc": sonuc, "hatalar": hatalar, "guven": guven}


def main() -> None:
    kesit = json.load(open(sys.argv[1], encoding="utf-8"))
    adet = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    tohum = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    ornekler = ornekler_uret(kesit, adet, tohum)
    v = asyncio.run(olc(ornekler))
    toplam = defaultdict(int)
    print(f"{'bicim':16} {'adet':>5} {'ilce':>6} {'mahalle':>8} {'sokak':>6} {'kapi':>6}")
    for bicim, s in v["sonuc"].items():
        for k, d in s.items():
            toplam[k] += d
        print(f"{bicim:16} {s['adet']:5} " + " ".join(f"{100 * s[k] / s['adet']:{w}.0f}%" for k, w in (("ilce", 5), ("mahalle", 7), ("sokak", 5), ("kapi", 5))))
    print(f"{'TOPLAM':16} {toplam['adet']:5} " + " ".join(f"{100 * toplam[k] / toplam['adet']:{w}.1f}%" for k, w in (("ilce", 5), ("mahalle", 7), ("sokak", 5), ("kapi", 5))))
    g = v["guven"]
    print(f"Puan >= 85: {g['yuksek']} sonuc, yanlis olan {g['yuksek_yanlis']} "
          f"(kesinlik %{100 * (1 - g['yuksek_yanlis'] / max(g['yuksek'], 1)):.2f}); puan < 85 (onay onerilen): {g['dusuk']}")
    for h in v["hatalar"][:25]:
        print("HATA", json.dumps(h, ensure_ascii=False)[:330])


if __name__ == "__main__":
    main()
