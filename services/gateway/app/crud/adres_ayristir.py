"""Adres ayristirma: ayristiricinin parcalarini adres veritabaniyla dogrular, eksikleri tamamlar, konum ve guven puani verir.

Sira: il / ilce (metindeki adlar, yoksa baglam) -> mahalle / koy (ilce icinde) -> sokak (mahalle, ilce, yakin cevre sirasiyla)
-> kapi numarasi (sokakta; ayni adli birden cok sokak varsa kapi numarasi ayirt eder) -> bina / site.
Adlar karsilastirilirken iki taraftan da tur kelimeleri atilir ("Cumhuriyet Mah." ile "Cumhuriyet Mahallesi" ayni cekirdek).
Her parca icin durum: dogrulandi (kesin), benzer (yazim farki; duzeltildi), bulunamadi, girilmedi.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from app.crud.adres import SOKAK_ZINCIR_JOIN, adres_metni
from app.crud import yerlesim as yerlesim_crud
from app.db import havuz
from app.metin import ad_katla
from app.services.ayristirici import Ayrisim, ayristir, katla, kelime_gruplari

log = logging.getLogger(__name__)

DOGRU_ESIK = 0.85
BENZER_ESIK = 0.55
TUR_SONEKLERI = re.compile(
    r"\s+(mahallesi|mahalle|mah\.?|mh\.?|koyu|koy|caddesi|cadde|cad\.?|cd\.?|sokagi|sokak|sok\.?|sk\.?|bulvari|bulvar|blv\.?|"
    r"yolu|yol|cikmazi|meydani|apartmani|apartman|apt\.?|sitesi|site|konutlari|evleri|is merkezi|plaza|rezidans|residence)$")
YOL_TUR_KELIMESI = {"cadde": ["caddesi", "cadde"], "sokak": ["sokak", "sokagi"], "bulvar": ["bulvari"], "yol": ["yolu"],
                    "cikmaz": ["cikmazi", "sokak"], "meydan": ["meydani"], "kume_evler": ["kume evler"]}
YOL_TUR_ADI = {"cadde": "Cad.", "sokak": "Sk.", "bulvar": "Blv.", "yol": "Yolu", "cikmaz": "Çıkmazı", "meydan": "Meydanı"}


def cekirdek(metin: str | None) -> str:
    """Katlanmis ad ve sondaki tur kelimeleri atilmis cekirdek ("Cumhuriyet Mahallesi" -> "cumhuriyet")."""
    if not metin:
        return ""
    k = ad_katla(metin).replace("'", " ")
    for _ in range(2):
        k = TUR_SONEKLERI.sub("", k).strip()
    return k.rstrip(".")


def _trigram(metin: str) -> set[str]:
    kume: set[str] = set()
    for kelime in metin.split():
        k = f"  {kelime} "
        kume.update(k[i:i + 3] for i in range(len(k) - 2))
    return kume


def benzerlik(a: str, b: str) -> float:
    """Ad benzerligi (0-1): trigram ile duzenleme (harf eksik / fazla / yer degismis) benzerliginin en iyisi.
    Bosluksuz bicim de denenir ("hamdibey" ile "hamdi bey")."""
    if not a or not b:
        return 0.0
    if a == b or a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    ta, tb = _trigram(a), _trigram(b)
    # Trigram kumesi tekrarlanan kelimeyi gormez ("lalezar lalezar" ile "lalezar" ayni kume); uzunluk oraniyla duzeltilir
    uzunluk = min(len(a), len(b)) / max(len(a), len(b))
    trigram = (len(ta & tb) / len(ta | tb) if ta and tb else 0.0) * (uzunluk ** 0.5)
    duzenleme = max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio())
    # Kisa adlarda tek harf farki orani cok dusurur / yukseltir; 4 harften kisa adlarda yalniz tam esleme
    if min(len(a), len(b)) < 4:
        return trigram
    return max(trigram, duzenleme * 0.97)


def _durum(puan: float) -> str:
    return "dogrulandi" if puan >= DOGRU_ESIK else "benzer"


async def _il_ilce(baglanti, a: Ayrisim, metin_gruplari: list[str], baglam: dict) -> tuple[dict | None, dict | None, set[str]]:
    """Il ve ilceyi metindeki adlardan bulur; belirsizlikte il / baglam konumu ayirt eder. Kullanilan kelime gruplarini dondurur."""
    adaylar = list(dict.fromkeys([ad_katla(x) for x in a.il_aday + a.ilce_aday] + metin_gruplari))
    if not adaylar:
        return None, None, set()
    satirlar = await baglanti.fetch(
        """SELECT y.id, y.ad, y.ad_arama, t.kod, y.ust_id, ST_Y(y.merkez::geometry) AS lat, ST_X(y.merkez::geometry) AS lon
             FROM yerlesim y JOIN tnm_yerlesim_turu t ON t.id = y.tur_id
            WHERE y.aktif_mi AND t.kod IN ('il', 'ilce') AND y.ad_arama = ANY($1::text[])""", adaylar)
    iller = [s for s in satirlar if s["kod"] == "il"]
    ilceler = [s for s in satirlar if s["kod"] == "ilce"]
    il = next((s for s in iller if s["ad_arama"] in [ad_katla(x) for x in a.il_aday]), None) or (iller[0] if len(iller) == 1 else None)
    if il is None and len(iller) > 1:
        # Birden cok il adi gectiyse (or. "Istanbul caddesi, Ankara") ilceyle uyumlu olan secilir
        il = next((s for s in iller if any(c["ust_id"] == s["id"] for c in ilceler)), iller[-1])
    if il is not None:
        ilceler_ilde = [c for c in ilceler if c["ust_id"] == il["id"]]
        # "merkez" ilce yazildiysa ilin merkez ilcesi (adi ille ayni)
        if not ilceler_ilde and "merkez" in adaylar:
            merkez = await baglanti.fetchrow(
                "SELECT y.id, y.ad, y.ad_arama, 'ilce' AS kod, y.ust_id FROM yerlesim y WHERE y.aktif_mi AND y.tur_id = 2 AND y.ust_id = $1 "
                "AND y.ad_arama = $2", il["id"], il["ad_arama"])
            ilceler_ilde = [merkez] if merkez else []
        # Il adi ile ayni adli ilce (merkez) yalniz baska ilce yoksa secilir
        ilceler = sorted(ilceler_ilde, key=lambda c: c["ad_arama"] == il["ad_arama"])
    ilce = None
    if len(ilceler) == 1 or (ilceler and il is not None):
        ilce = ilceler[0]
    elif len(ilceler) > 1 and baglam.get("lat") is not None:
        ilce = min(ilceler, key=lambda c: (c["lat"] - baglam["lat"]) ** 2 + (c["lon"] - baglam["lon"]) ** 2)
    if ilce is not None and il is None:
        il = await baglanti.fetchrow("SELECT id, ad, ad_arama, 'il' AS kod, ust_id FROM yerlesim WHERE id = $1", ilce["ust_id"])
    kullanilan = {s["ad_arama"] for s in (il, ilce) if s}
    return (dict(il) if il else None), (dict(ilce) if ilce else None), kullanilan


async def _mahalle(baglanti, ad: str | None, ilce: dict | None, il: dict | None, baglam: dict) -> tuple[dict | None, float, list[dict]]:
    """Mahalle / koyu ilce icinde (yoksa ilde, yoksa baglam cevresinde) en benzer cekirdekle bulur."""
    if not ad:
        return None, 0.0, []
    hedef = cekirdek(ad)
    if ilce:
        satirlar = await baglanti.fetch(
            "SELECT id, ad, ad_arama, ust_id FROM yerlesim WHERE aktif_mi AND tur_id = 3 AND ust_id = $1", ilce["id"])
    else:
        satirlar = await baglanti.fetch(
            """SELECT y.id, y.ad, y.ad_arama, y.ust_id FROM yerlesim y
                WHERE y.aktif_mi AND y.tur_id = 3 AND y.ad_arama % $1
                  AND ($2::bigint IS NULL OR y.ust_id IN (SELECT id FROM yerlesim WHERE ust_id = $2))
                  AND ($3::float8 IS NULL OR ST_DWithin(y.merkez, ST_SetSRID(ST_MakePoint($4, $3), 4326)::geography, 60000))
                ORDER BY similarity(y.ad_arama, $1) DESC LIMIT 20""",
            ad_katla(ad) + " mahallesi", il["id"] if il else None, baglam.get("lat"), baglam.get("lon"))
    puanli = sorted(((benzerlik(cekirdek(s["ad"]), hedef), dict(s)) for s in satirlar), key=lambda x: -x[0])
    if not puanli or puanli[0][0] < BENZER_ESIK:
        return None, 0.0, [s for _, s in puanli[:3]]
    return puanli[0][1], puanli[0][0], [s for p, s in puanli[1:3] if p >= BENZER_ESIK]


async def _sokak_adaylari(baglanti, ad: str, tur: str | None, mahalle: dict | None, ilce: dict | None, baglam: dict) -> list[tuple[float, dict]]:
    """Sokak adaylari: mahallede, yoksa ilcede (mahallesiz yollar dahil), yoksa baglam cevresinde (30 km)."""
    numarali = re.fullmatch(r"\d+", ad.strip())
    hedef = ad.strip() if numarali else cekirdek(ad)
    tur_kelimeleri = YOL_TUR_KELIMESI.get(tur or "", ["caddesi", "sokak", "sokagi", "bulvari", "yolu"])
    sorgu_metinleri = [f"{hedef}. {k}" if numarali else f"{hedef} {k}" for k in tur_kelimeleri] + [hedef]
    # Mahalle / ilce biliniyorsa oradaki tum sokaklar puanlanir (yazim hatali adlar on elemede kaybolmasin);
    # yalniz baglam konumu varsa cevredeki benzer adlar on elemeyle alinir
    kapsamlar = []
    if mahalle:
        kapsamlar.append(("x.mahalle_id = $2", mahalle["id"], False))
    if ilce:
        kapsamlar.append(("(m.ust_id = $2 OR (x.mahalle_id IS NULL AND x.ilce_id = $2))", ilce["id"], False))
    if baglam.get("lat") is not None:
        kapsamlar.append(("ST_DWithin(x.merkez, ST_SetSRID(ST_MakePoint($4, $3), 4326)::geography, 30000)", None, True))
    for kosul, deger, on_eleme in kapsamlar:
        satirlar = await baglanti.fetch(
            f"""SELECT x.id, x.ad, x.ad_arama, x.mahalle_id, m.ad AS mahalle, i.id AS ilce_id, i.ad AS ilce, l.id AS il_id, l.ad AS il,
                       ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon, c.kod AS sinif
                  FROM sokak x JOIN tnm_yol_sinifi c ON c.id = x.sinif_id {SOKAK_ZINCIR_JOIN}
                 WHERE x.aktif_mi AND {kosul}
                   -- her kapsam tum parametreleri kullanmaz; turleri burada sabitlenir
                   AND ($2::bigint IS NULL OR $2::bigint IS NOT NULL) AND ($3::float8 IS NULL OR $4::float8 IS NULL OR TRUE)
                   AND (NOT $6::bool OR x.ad_arama = ANY($1::text[]) OR x.ad_arama LIKE $5 || '%' OR similarity(x.ad_arama, $1[1]) > 0.25)
                 ORDER BY similarity(x.ad_arama, $1[1]) DESC LIMIT 6000""",
            sorgu_metinleri, deger, baglam.get("lat"), baglam.get("lon"), hedef, on_eleme)
        puanli = []
        for s in satirlar:
            db = s["ad_arama"]
            db_cekirdek = re.sub(r"\.$", "", db.split()[0]) if numarali and db.split() else cekirdek(db)
            p = 1.0 if numarali and db_cekirdek == hedef else benzerlik(db_cekirdek, hedef)
            # Tur uyumu: "Ataturk Cad." yazildiysa "Ataturk Sokak" daha dusuk puan alir
            if tur and not any(db.endswith(k) for k in tur_kelimeleri):
                p *= 0.85
            puanli.append((p, dict(s)))
        puanli = [x for x in sorted(puanli, key=lambda x: -x[0]) if x[0] >= BENZER_ESIK]
        if puanli:
            return puanli
    return []


async def _kapilar(baglanti, sokak_idleri: list[int], kapi_no: str) -> list[dict]:
    """Aday sokaklarda bu numarali kapilar (aday sirasiyla); ayni adli sokaklar arasinda ayirt etmek icin."""
    satirlar = await baglanti.fetch(
        """SELECT x.id, x.kapi_no, x.sokak_id, ST_Y(x.konum::geometry) AS lat, ST_X(x.konum::geometry) AS lon
             FROM kapi_numarasi x WHERE x.aktif_mi AND x.sokak_id = ANY($1::bigint[]) AND x.kapi_no_arama = $2
            ORDER BY array_position($1::bigint[], x.sokak_id)""", sokak_idleri, kapi_no.lower())
    return [dict(s) for s in satirlar]


def _uzak_mi(a: dict, b: dict, metre: float = 150) -> bool:
    """Iki nokta verilen mesafeden uzak mi (yaklasik)."""
    return ((a["lat"] - b["lat"]) * 110540) ** 2 + ((a["lon"] - b["lon"]) * 85000) ** 2 > metre ** 2


async def _bina(baglanti, ad: str, mahalle: dict | None, sokak: dict | None, merkez: dict | None) -> tuple[dict | None, float]:
    """Bina / siteyi mahallede, sokakta ya da bilinen konumun 2 km cevresinde arar."""
    if not (mahalle or sokak or merkez):
        return None, 0.0
    hedef = cekirdek(ad)
    satirlar = await baglanti.fetch(
        """SELECT x.id, x.ad, x.sokak_id, ST_Y(x.merkez::geometry) AS lat, ST_X(x.merkez::geometry) AS lon
             FROM bina x WHERE x.aktif_mi AND similarity(x.ad_arama, $1) > 0.3
              AND (x.mahalle_id = $2 OR x.sokak_id = $3
                   OR ($4::float8 IS NOT NULL AND ST_DWithin(x.merkez, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography, 2000)))
            ORDER BY similarity(x.ad_arama, $1) DESC LIMIT 10""",
        ad_katla(ad), mahalle["id"] if mahalle else None, sokak["id"] if sokak else None,
        merkez["lat"] if merkez else None, merkez["lon"] if merkez else None)
    puanli = sorted(((benzerlik(cekirdek(s["ad"]), hedef), dict(s)) for s in satirlar), key=lambda x: -x[0])
    if puanli and puanli[0][0] >= BENZER_ESIK:
        return puanli[0][1], puanli[0][0]
    return None, 0.0


def _parca(ad, kimlik, durum, girilen=None, puan=None) -> dict:
    return {"ad": ad, "id": kimlik, "durum": durum, "girilen": girilen, "benzerlik": round(puan, 2) if puan is not None else None}


async def ayristir_ve_dogrula(metin: str, baglam: dict | None = None) -> dict:
    """Serbest adres metnini ayristirir ve dogrular. baglam: {lat, lon} (or. isletme konumu) ve / veya {ilce_id}."""
    baglam = baglam or {}
    a = ayristir(metin)
    oneriler: list[dict] = []
    # Ilce / il mahalleden once virgulsuz yazildiysa ("Kadikoy Caferaga mahallesi") mahalle adinin basina yapisir;
    # mahalle / koy / sokak adinin ilk bir-iki kelimesi de il / ilce adayi olarak denenir
    # (Sokak adinin basi denenmez: "Pazar Yolu", "Ankara Caddesi" gibi adlar ilce / il adiyla baslar.)
    on_ekler = []
    for ad in (a.mahalle, a.koy):
        kelimeler = (ad or "").split()
        on_ekler += [ad_katla(" ".join(kelimeler[:n])) for n in (1, 2) if len(kelimeler) > n]
    async with havuz().acquire() as b:
        il, ilce, kullanilan = await _il_ilce(b, a, kelime_gruplari(a.kalan or "") + on_ekler, baglam)
        # Yalniz mahalle on ekinden gelen ilce, baglam konumundan cok uzaksa (80 km) kabul edilmez
        if ilce and baglam.get("lat") is not None and ilce["ad_arama"] in on_ekler and ilce.get("lat") is not None \
                and ((ilce["lat"] - baglam["lat"]) ** 2 + (ilce["lon"] - baglam["lon"]) ** 2) ** 0.5 > 0.8:
            il = ilce = None
            kullanilan = set()
        for alan in ("mahalle", "koy"):
            deger = getattr(a, alan)
            for grup in sorted(kullanilan, key=len, reverse=True):
                if deger and ad_katla(deger).startswith(grup + " "):
                    deger = deger[len(grup) + 1:].strip()
            setattr(a, alan, deger)
        # Tarif metnindeki kelimeler ("pazar yeri yani", "cay ocagi karsisi") yanlis ilceye yol acmasin diye
        # yalniz il belli iken ve o ilin ilcesiyle eslesirse kullanilir
        if a.tarif and il is not None and ilce is None:
            _, tarif_ilce, tarif_kullanilan = await _il_ilce(b, Ayrisim(il_aday=[il["ad"]]), kelime_gruplari(a.tarif), baglam)
            if tarif_ilce and tarif_ilce.get("ust_id") == il["id"]:
                ilce, kullanilan = tarif_ilce, kullanilan | tarif_kullanilan
        il_kaynak = "metin" if il else None
        if ilce is None and baglam.get("ilce_id"):
            satir = await b.fetchrow("SELECT id, ad, ad_arama, 'ilce' AS kod, ust_id FROM yerlesim WHERE id = $1 AND tur_id = 2", baglam["ilce_id"])
            ilce = dict(satir) if satir else None
            if ilce and il is None:
                il = dict(await b.fetchrow("SELECT id, ad, ad_arama, 'il' AS kod FROM yerlesim WHERE id = $1", ilce["ust_id"]))
            il_kaynak = "baglam"
        mahalle_adi = a.mahalle or a.koy
        mahalle, mahalle_puan, mahalle_adaylari = await _mahalle(b, mahalle_adi, ilce, il, baglam)
        if mahalle and ilce is None:
            ilce = dict(await b.fetchrow("SELECT id, ad, ad_arama, 'ilce' AS kod, ust_id FROM yerlesim WHERE id = $1", mahalle["ust_id"]))
            if il is None:
                il = dict(await b.fetchrow("SELECT id, ad, ad_arama, 'il' AS kod FROM yerlesim WHERE id = $1", ilce["ust_id"]))
            il_kaynak = il_kaynak or "mahalle"
        if mahalle_adi and not mahalle and mahalle_adaylari:
            oneriler.append({"alan": "mahalle", "adaylar": [{"id": m["id"], "ad": m["ad"]} for m in mahalle_adaylari]})

        sokak = kapi = None
        sokak_puan = 0.0
        belirsiz = False
        if a.sokak:
            adaylar = await _sokak_adaylari(b, a.sokak, a.sokak_turu, mahalle, ilce, baglam)
            if adaylar:
                # Ayni puandaki adaylar arasinda (ayni adli sokak, farkli mahalle) kapi numarasi ayirt eder
                en_iyi = [s for p, s in adaylar if p >= adaylar[0][0] - 0.05]
                sokak_puan, sokak = adaylar[0]
                if a.kapi_no:
                    bulunan = await _kapilar(b, [s["id"] for s in en_iyi] + [s["id"] for _, s in adaylar[len(en_iyi):]], a.kapi_no)
                    if bulunan:
                        kapi = bulunan[0]
                        sokak_puan, sokak = next((p, s) for p, s in adaylar if s["id"] == kapi["sokak_id"])
                        # Esit derecede iyi adaylarin birden cogunda ayni numara, birbirinden uzak konumlarda: gercek belirsizlik
                        esdeger = [k for k in bulunan if k["sokak_id"] in {s["id"] for s in en_iyi}]
                        uzaklar = [k for k in esdeger if _uzak_mi(k, kapi)]
                        if uzaklar:
                            belirsiz = True
                            sokak_adi = {s["id"]: s for _, s in adaylar}
                            oneriler.append({"alan": "kapi", "adaylar": [
                                {"sokak_id": k["sokak_id"], "sokak": sokak_adi[k["sokak_id"]]["ad"], "mahalle": sokak_adi[k["sokak_id"]]["mahalle"],
                                 "kapi_id": k["id"], "konum": {"lat": k["lat"], "lon": k["lon"]}} for k in [kapi] + uzaklar[:4]]})
                if not kapi and len(en_iyi) > 1 and not mahalle:
                    belirsiz = True
                    oneriler.append({"alan": "sokak", "adaylar": [{"id": s["id"], "ad": s["ad"], "mahalle": s["mahalle"]} for s in en_iyi[:5]]})
                if sokak_puan < DOGRU_ESIK:
                    oneriler.append({"alan": "sokak_yazimi", "girilen": a.sokak, "oneri": sokak["ad"]})
                # Sokaktan mahalle / ilce / il tamamlanir
                if not mahalle and sokak.get("mahalle_id"):
                    mahalle = {"id": sokak["mahalle_id"], "ad": sokak["mahalle"]}
                    mahalle_puan = 1.0
                if not ilce and sokak.get("ilce_id"):
                    ilce = {"id": sokak["ilce_id"], "ad": sokak["ilce"]}
                if not il and sokak.get("il_id"):
                    il = {"id": sokak["il_id"], "ad": sokak["il"]}
                    il_kaynak = il_kaynak or "sokak"
        konum_ref = kapi or sokak or (await _yerlesim_merkezi(mahalle)) or None
        bina, bina_puan = (await _bina(b, a.bina, mahalle, sokak, konum_ref)) if a.bina else (None, 0.0)

    # Konum: kapi > bina > sokak > mahalle > ilce > il
    konum, kesinlik = None, None
    for aday, ad in ((kapi, "kapi"), (bina, "bina"), (sokak, "sokak")):
        if aday:
            konum, kesinlik = {"lat": aday["lat"], "lon": aday["lon"]}, ad
            break
    if konum is None:
        for aday, ad in ((mahalle, "mahalle_koy"), (ilce, "ilce"), (il, "il")):
            merkez = await _yerlesim_merkezi(aday)
            if merkez:
                konum, kesinlik = merkez, ad
                break

    parcalar = {
        "il": _parca(il["ad"], il["id"], "dogrulandi" if ad_katla(il["ad"]) in kullanilan else "tamamlandi") if il else _parca(None, None, "girilmedi"),
        "ilce": _parca(ilce["ad"], ilce["id"], "dogrulandi" if ilce and ad_katla(ilce["ad"]) in kullanilan else "tamamlandi") if ilce else _parca(None, None, "girilmedi"),
        "mahalle": (_parca(mahalle["ad"], mahalle["id"], _durum(mahalle_puan) if mahalle_adi else "tamamlandi", mahalle_adi, mahalle_puan if mahalle_adi else None)
                    if mahalle else _parca(None, None, "bulunamadi" if mahalle_adi else "girilmedi", mahalle_adi)),
        "sokak": (_parca(sokak["ad"], sokak["id"], _durum(sokak_puan), a.sokak, sokak_puan) if sokak
                  else _parca(None, None, "bulunamadi" if a.sokak else "girilmedi", a.sokak)),
        "kapi_no": {"deger": a.kapi_no, "id": kapi["id"] if kapi else None,
                    "durum": "dogrulandi" if kapi else ("bulunamadi" if a.kapi_no and sokak else ("girildi" if a.kapi_no else "girilmedi"))},
        "bina": (_parca(bina["ad"], bina["id"], _durum(bina_puan), a.bina, bina_puan) if bina
                 else _parca(a.bina, None, "girildi" if a.bina else "girilmedi", a.bina)),
        "bina_turu": a.bina_turu, "blok": a.blok, "kat": a.kat, "daire": a.daire, "posta_kodu": a.posta_kodu,
    }
    tarif = _tarif_temizle(a.tarif, kullanilan)
    kalan = _tarif_temizle(a.kalan, kullanilan)
    eksikler = [k for k in ("mahalle", "sokak", "kapi_no") if parcalar[k]["durum"] in ("girilmedi", "bulunamadi")]
    return {
        "girdi": metin,
        "duzgun": _duzgun_adres(parcalar, a, sokak, il, ilce, mahalle),
        "parcalar": parcalar,
        "tarif": tarif or None,
        "konum": {**konum, "kesinlik": kesinlik} if konum else None,
        "puan": min(_puan(parcalar, kesinlik), 70) if belirsiz else _puan(parcalar, kesinlik),
        "belirsiz": belirsiz,
        "eksikler": eksikler,
        "oneriler": oneriler,
        "kalan": kalan or None,
        "uyarilar": (["Metindeki telefon numarasi adresten ayiklandi."] if a.telefon_atildi else []),
    }


async def _yerlesim_merkezi(yer: dict | None) -> dict | None:
    if not yer or not yer.get("id"):
        return None
    if "lat" in yer and yer["lat"] is not None:
        return {"lat": yer["lat"], "lon": yer["lon"]}
    veri = await yerlesim_crud.getir(yer["id"], False)
    return veri["merkez"] if veri else None


def _tarif_temizle(metin: str | None, kullanilan: set[str]) -> str:
    """Tarif / kalan metinden il ve ilce olarak kullanilmis kelimeleri atar."""
    if not metin:
        return ""
    kelimeler = [k for k in re.split(r"[\s/]+", metin) if k]
    tek = {g for g in kullanilan if " " not in g}
    cok = [g.split() for g in kullanilan if " " in g]
    sonuc, i = [], 0
    while i < len(kelimeler):
        katli = [katla(k).strip(".,") for k in kelimeler]
        eslesen = next((len(g) for g in cok if katli[i:i + len(g)] == g), 0)
        if eslesen:
            i += eslesen
            continue
        if katli[i] and katli[i] not in tek:
            sonuc.append(kelimeler[i])
        i += 1
    return " ".join(sonuc).strip(" ,/-")


def _duzgun_adres(parcalar: dict, a: Ayrisim, sokak: dict | None, il: dict | None, ilce: dict | None, mahalle: dict | None) -> str:
    """Standart bicimli adres: 'Mahalle, Sokak No: 12, Bina A Blok Kat: 3 Daire: 5, 59500 Ilce/Il'."""
    parca = []
    if mahalle:
        parca.append(mahalle["ad"])
    yol = sokak["ad"] if sokak else (f"{a.sokak} {YOL_TUR_ADI.get(a.sokak_turu or '', '')}".strip() if a.sokak else None)
    if yol:
        parca.append(f"{yol} No: {a.kapi_no}" if a.kapi_no else yol)
    elif a.kapi_no:
        parca.append(f"No: {a.kapi_no}")
    ic = " ".join(filter(None, [
        parcalar["bina"]["ad"] or None,
        f"{a.blok} Blok" if a.blok else None,
        f"Kat: {a.kat}" if a.kat else None,
        f"Daire: {a.daire}" if a.daire else None,
    ]))
    if ic:
        parca.append(ic)
    yer = "/".join(filter(None, [ilce["ad"] if ilce else None, il["ad"] if il and (not ilce or il["ad"] != ilce["ad"]) else None]))
    if yer:
        parca.append(f"{a.posta_kodu} {yer}".strip() if a.posta_kodu else yer)
    return adres_metni([", ".join(parca)], None, None, None) if parca else ""


def _puan(parcalar: dict, kesinlik: str | None) -> int:
    """0-100 guven puani: konumun kesinligi ve girilen parcalarin dogrulanma durumu."""
    temel = {"kapi": 95, "bina": 85, "sokak": 75, "mahalle_koy": 50, "ilce": 30, "il": 15}.get(kesinlik or "", 0)
    for alan in ("mahalle", "sokak", "bina"):
        durum = parcalar[alan]["durum"]
        if durum == "benzer":
            # Yazim farkiyla bulunan sokak: dogru olma ihtimali yuksek ama kullanici onayi onerilir (puan 85'in altinda)
            temel -= 15 if alan == "sokak" else 5
        elif durum == "bulunamadi":
            temel -= 15
    if parcalar["kapi_no"]["durum"] == "bulunamadi":
        temel -= 5
    if kesinlik == "kapi" and parcalar["sokak"]["durum"] == "dogrulandi" and parcalar["mahalle"]["durum"] in ("dogrulandi", "tamamlandi", "girilmedi"):
        temel = 100
    return max(0, min(100, temel))
