"""Serbest yazilmis Turkce adresi parcalarina ayiran saf (veritabanisiz) cozumleyici.

Ornek: "cumhuriyet mh. atatürk cd. no:12/5 gül apt. a blok kat 3 çerkezköy/tekirdağ, migros karşısı"
  -> mahalle "Cumhuriyet", sokak "Atatürk" (cadde), kapi_no "12", daire "5", bina "Gül" (apartman), blok "A", kat "3",
     ilce_aday "Çerkezköy", il_aday "Tekirdağ", tarif "Migros karşısı".

Yaklasim: metin kelimelere bolunur; anahtar kelimeler (mah, cad, sok, no, kat, daire, blok, apt, site, koy ...) "capa" olarak
isaretlenir. Adli parcalarin adi, capanin hemen onundeki capa olmayan kelimelerdir (virgulu ve onceki capayi gecmez).
Konumlar katlanmis (ASCII, kucuk harf) metinde aranir; katlama karakter sayisini degistirmedigi icin ozgun metinden
ayni araliklar alinir (bulunan adlar kullanicinin yazdigi bicimde doner). Il / ilce adlari yalniz "aday" olarak cikar;
gercek olup olmadiklari dogrulama katmaninda (veritabani) belirlenir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_KATLAMA = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
                          "Ö": "o", "ö": "o", "Ş": "s", "ş": "s", "Ü": "u", "ü": "u", "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u"})


def katla(metin: str) -> str:
    """Uzunlugu degistirmeden kucuk harf + ASCII katlama (konumlar ozgun metinle ayni kalir)."""
    sonuc = metin.translate(_KATLAMA)
    # str.lower() bazi harflerde uzunluk degistirebilir; harf harf ve tek karakter garantisiyle indirilir
    return "".join(h.lower() if len(h.lower()) == 1 else h for h in sonuc)


# Yol turleri: katlanmis yazimlar -> standart tur
YOL_TURLERI = {
    "caddesi": "cadde", "cadde": "cadde", "cad": "cadde", "cd": "cadde", "cadd": "cadde", "caddes": "cadde",
    "sokagi": "sokak", "sokak": "sokak", "sok": "sokak", "sk": "sokak", "sokk": "sokak", "skk": "sokak",
    "bulvari": "bulvar", "bulvar": "bulvar", "blv": "bulvar", "bulv": "bulvar", "bl": "bulvar",
    "yolu": "yol", "yol": "yol",
    "cikmazi": "cikmaz", "cikmaz": "cikmaz", "cikm": "cikmaz",
    "meydani": "meydan", "meydan": "meydan",
    "kume": "kume_evler",  # "kume evler"
}
MAHALLE = {"mahallesi", "mahalle", "mah", "mh", "mhl", "mahal", "mahalesi", "mahallasi"}
KOY = {"koyu", "koy"}
BINA_TURLERI = {
    "apartmani": "apartman", "apartman": "apartman", "apt": "apartman", "ap": "apartman", "aprt": "apartman",
    "sitesi": "site", "site": "site", "sit": "site", "konutlari": "site", "evleri": "site", "rezidans": "site",
    "residence": "site", "residance": "site", "rezidansi": "site", "lojmanlari": "site", "kooperatifi": "site",
    "plaza": "is_merkezi", "plazasi": "is_merkezi", "hani": "is_merkezi", "pasaji": "is_merkezi", "carsisi": "is_merkezi",
    "towers": "site", "kuleleri": "site", "bloklari": "site",
}
# "is merkezi", "is hani" iki kelimelik
TARIF_KELIMELERI = ("yani", "karsisi", "arkasi", "onu", "ustu", "alti", "bitisigi", "yakini", "kosesi", "caprazi", "sirasi",
                    "ici", "arasi", "girisi", "yaninda", "karsisinda", "arkasinda", "onunde", "ustunde", "altinda",
                    "bitisiginde", "yakininda", "kosesinde", "icinde", "tarafi", "civari")
KAT_OZEL = {"zemin": "Zemin", "giris": "Giriş", "bodrum": "Bodrum", "cati": "Çatı", "asma": "Asma", "yuksek": "Yüksek giriş",
            "bahce": "Bahçe", "teras": "Teras"}

_KELIME = re.compile(r"[^\s,;]+")
_TELEFON = re.compile(r"(?:\+?90[\s-]*)?\(?0?5\d{2}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_POSTA = re.compile(r"(?<![\d/.:-])(0[1-9]|[1-7]\d|8[01])\d{3}(?![\d/])")
# Kapi numarasi: 12, 12a, 12/5, 12-5, harfle baslayan (J2, B12)
_NO_DEGERI = re.compile(r"^([a-z]?\d{1,5})\s*([a-z])?(?:\s*[/-]\s*(\d{1,4})([a-z])?)?$")


@dataclass
class Kelime:
    """Metindeki bir kelime: ozgun ve katlanmis bicim, konum, kullanildi mi."""

    ozgun: str
    kat: str
    bas: int
    son: int
    virgulden_sonra: bool = False
    kullanildi: bool = False

    @property
    def sade(self) -> str:
        """Noktalama atilmis katlanmis bicim ("cd." -> "cd", "no:12" korunur)."""
        return self.kat.strip(".:;!?()[]\"'")


@dataclass
class Ayrisim:
    """Ayristirma sonucu (dogrulanmamis parcalar)."""

    mahalle: str | None = None
    koy: str | None = None
    sokak: str | None = None
    sokak_turu: str | None = None
    kapi_no: str | None = None
    daire: str | None = None
    kat: str | None = None
    blok: str | None = None
    bina: str | None = None
    bina_turu: str | None = None
    posta_kodu: str | None = None
    ilce_aday: list[str] = field(default_factory=list)
    il_aday: list[str] = field(default_factory=list)
    tarif: str | None = None
    kalan: str = ""
    telefon_atildi: bool = False

    def sozluk(self) -> dict:
        """API icin sozluk."""
        return {k: v for k, v in self.__dict__.items()}


def _temizle(metin: str) -> str:
    """Unicode birlestirme, satir sonu ve noktali virgulu virgule cevirme, gereksiz bosluk."""
    metin = unicodedata.normalize("NFC", metin)
    metin = re.sub(r"[\r\n\t;|]+", ", ", metin)
    metin = re.sub(r"[“”\"]", " ", metin)
    return re.sub(r"[  ]+", " ", metin).strip(" ,")


def _kelimeler(metin: str, kat: str) -> list[Kelime]:
    sonuc = []
    for m in _KELIME.finditer(kat):
        onceki = kat[: m.start()].rstrip(" ")
        sonuc.append(Kelime(metin[m.start():m.end()], m.group(0), m.start(), m.end(), virgulden_sonra=onceki.endswith((",", ";"))))
    return sonuc


def _kucuk(metin: str) -> str:
    """Turkce kucuk harf (I -> ı, İ -> i)."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def _baslik(metin: str) -> str:
    """Turkce kurallarla her kelimenin bas harfi buyuk, kalani kucuk ("ATATÜRK" / "atatürk" -> "Atatürk", "ilk" -> "İlk")."""
    def kelime(k: str) -> str:
        k = _kucuk(k)
        return ({"i": "İ", "ı": "I"}.get(k[0], k[0].upper()) + k[1:]) if k else k
    return " ".join(kelime(k) for k in metin.split())


def _ad_oncesi(kelimeler: list[Kelime], capa: int, en_fazla: int = 5) -> tuple[str | None, list[int]]:
    """Capanin onundeki ad kelimeleri: kullanilmamis, virgul / onceki capa gecilmeden en fazla en_fazla kelime."""
    secilen: list[int] = []
    i = capa - 1
    while i >= 0 and len(secilen) < en_fazla:
        k = kelimeler[i]
        if k.kullanildi or _capa_mi(k):
            break
        secilen.insert(0, i)
        if k.virgulden_sonra:
            break
        i -= 1
    if not secilen:
        return None, []
    # Ad virgulle bitiyorsa son kelimedeki virgul atilir; "no" gibi kelimeler adin parcasi olamaz
    ad = " ".join(kelimeler[j].ozgun.strip(",.;:") for j in secilen).strip()
    return (ad or None), secilen


def _capa_mi(k: Kelime) -> bool:
    s = k.sade
    return (s in MAHALLE or s in YOL_TURLERI or s in BINA_TURLERI or s in KOY or s in ("no", "nu", "numara", "kat", "daire", "blok", "blk", "d", "k")
            or bool(re.match(r"^(no|kat|daire|d|k)[:.]", k.kat)))


def _isaretle(kelimeler: list[Kelime], idler) -> None:
    for i in idler:
        kelimeler[i].kullanildi = True


def ayristir(metin: str) -> Ayrisim:
    """Serbest adres metnini parcalarina ayirir (bkz. modul aciklamasi)."""
    sonuc = Ayrisim()
    metin = _temizle(metin)
    if _TELEFON.search(metin):
        metin = _TELEFON.sub(" ", metin)
        sonuc.telefon_atildi = True
        metin = re.sub(r"\s+", " ", metin).strip(" ,")
    kat = katla(metin)
    kelimeler = _kelimeler(metin, kat)
    n = len(kelimeler)

    # 1) Il / ilce: "Corlu/Tekirdag", "Kadikoy - Istanbul" (son kisim). Adaylar dogrulamada denetlenir
    m = re.search(r"([^\s,/\d.:]+(?:\s[^\s,/\d.:]+)?)\s*[/\\-]\s*([^\s,/\d.:]+)\s*$", kat)
    if m and katla(m.group(1).split()[-1]) not in ("blok", "kat", "daire", "no"):
        ilce, il = metin[m.start(1):m.end(1)], metin[m.start(2):m.end(2)]
        sonuc.ilce_aday.append(_baslik(ilce.split()[-1]) if len(ilce.split()) > 1 and katla(ilce.split()[0]) in YOL_TURLERI else _baslik(ilce))
        sonuc.il_aday.append(_baslik(il))
        for k in kelimeler:
            if k.bas >= m.start(1):
                k.kullanildi = True

    # 2) Tarif: "migros karsisi", "eczanenin yani" iceren parca (virgulle ayrilmis bolumun tamami)
    for bolum in re.finditer(r"[^,]+", kat):
        if any(re.search(rf"\b{t}\b", bolum.group(0)) for t in TARIF_KELIMELERI):
            parca_kelimeler = [i for i, k in enumerate(kelimeler) if bolum.start() <= k.bas < bolum.end() and not k.kullanildi]
            # Bolum ayni zamanda adres parcasi tasiyorsa (or. "no 5 eczane yani") yalniz tarif kelimesinin cevresi alinir
            if parca_kelimeler:
                # Tarif: tarif kelimesi ve onundeki en fazla 3 kelime ("merkez camii yani", "migros karsisi");
                # bolumun basindaki adres parcalari (capa, sayi) tarife girmez. Il / ilce adlari dogrulamada ayiklanir.
                anahtar = max(i for i in parca_kelimeler if any(re.search(rf"\b{t}\b", kelimeler[i].sade) for t in TARIF_KELIMELERI)) \
                    if any(any(re.search(rf"\b{t}\b", kelimeler[i].sade) for t in TARIF_KELIMELERI) for i in parca_kelimeler) else parca_kelimeler[-1]
                ilk = parca_kelimeler[0]
                for i in parca_kelimeler:
                    if i < anahtar and (_capa_mi(kelimeler[i]) or re.match(r"^\d", kelimeler[i].sade)):
                        ilk = i + 1
                ilk = max(ilk, anahtar - 3)
                tarif_idleri = [i for i in parca_kelimeler if ilk <= i <= anahtar]
                if tarif_idleri:
                    sonuc.tarif = " ".join(kelimeler[i].ozgun.strip(",") for i in tarif_idleri)
                    _isaretle(kelimeler, tarif_idleri)

    i = 0
    son_yol = -1  # son kullanilan yol turu kelimesinin sirasi (birlesik adlar icin)
    son_bina = -1  # son kullanilan bina / site turu kelimesinin sirasi
    while i < n:
        k = kelimeler[i]
        s = k.sade
        sonraki = kelimeler[i + 1] if i + 1 < n else None

        # 3) Mahalle
        if s in MAHALLE and not k.kullanildi:
            ad, idler = _ad_oncesi(kelimeler, i, 4)
            if ad and not sonuc.mahalle:
                sonuc.mahalle = _baslik(ad)
                _isaretle(kelimeler, idler + [i])

        # 4) Koy
        elif s in KOY and not k.kullanildi:
            ad, idler = _ad_oncesi(kelimeler, i, 3)
            if ad and not sonuc.koy:
                sonuc.koy = _baslik(ad)
                _isaretle(kelimeler, idler + [i])

        # 5) Cadde / sokak / bulvar (numarali sokaklar dahil: "1234. sokak", "1234 sk"); "kume evler"
        elif s in YOL_TURLERI and not k.kullanildi:
            tur = YOL_TURLERI[s]
            if tur == "kume_evler" and not (sonraki and sonraki.sade.startswith("evler")):
                i += 1
                continue
            ad, idler = _ad_oncesi(kelimeler, i, 4)
            birlesik = sonuc.sokak and son_yol == i - 1
            if not ad and not sonuc.sokak and son_bina == i - 1 and sonuc.bina:
                # "Sigorta Evleri Sk.", "Yesil Konutlari Sokak": site turu sanilan kelime sokak adinin parcasi
                sonuc.sokak = f"{sonuc.bina} {_baslik(kelimeler[i - 1].ozgun.strip(',.'))}"
                sonuc.sokak_turu = tur
                sonuc.bina = sonuc.bina_turu = None
                k.kullanildi = True
                son_yol = i
                birlesik = True
            elif birlesik:
                # "Plaj Yolu Sokagi", "Istasyon Caddesi Sokak": ilk tur kelimesi adin parcasidir
                sonuc.sokak = f"{sonuc.sokak} {_baslik(kelimeler[i - 1].ozgun.strip(',.'))}"
                sonuc.sokak_turu = tur
                k.kullanildi = True
                son_yol = i
            elif ad and not sonuc.sokak:
                sonuc.sokak = ad.rstrip(".") if re.fullmatch(r"\d+\.?", ad) else _baslik(ad)
                sonuc.sokak_turu = tur
                _isaretle(kelimeler, idler + [i])
                son_yol = i
            if birlesik or (ad and son_yol == i):
                if tur == "kume_evler" and sonraki:
                    sonraki.kullanildi = True
                # Yol adindan hemen sonra gelen yalin sayi kapi numarasidir ("Ataturk Cd 12")
                if sonraki and not sonraki.kullanildi and _NO_DEGERI.match(sonraki.sade) and not sonuc.kapi_no:
                    _kapi_yaz(sonuc, sonraki.sade)
                    sonraki.kullanildi = True

        # 6) Kapi no: "no 12", "no:12/5", "no.12a", "numara 12", "kapi no 12"
        elif not k.kullanildi and (s in ("no", "nu", "numara") or re.match(r"^no[:.]?[a-z]?\d", k.kat)):
            gomulu = re.match(r"^no[:.]?([a-z]?\d.*)$", k.kat)
            deger = gomulu.group(1).strip(":.,") if gomulu else ""
            idler = [i]
            if not deger and sonraki and not sonraki.kullanildi:
                deger = sonraki.sade
                idler.append(i + 1)
                # "No 12 A" bicimi: tek harf ek (ama "No 7 D 3" / "No: 7 D: 3" daire isaretidir)
                ek = kelimeler[i + 2] if i + 2 < n else None
                ardindaki = kelimeler[i + 3] if i + 3 < n else None
                if (ek and not ek.kullanildi and re.fullmatch(r"[a-z]", ek.kat)
                        and not (ek.kat == "d" and ardindaki and re.fullmatch(r"\d{1,4}", ardindaki.sade))):
                    deger += ek.sade
                    idler.append(i + 2)
            if deger and _NO_DEGERI.match(deger.replace(" ", "")) and not sonuc.kapi_no:
                _kapi_yaz(sonuc, deger.replace(" ", ""))
                _isaretle(kelimeler, idler)
                if i > 0 and kelimeler[i - 1].sade == "kapi":
                    kelimeler[i - 1].kullanildi = True

        # 7) Daire: "daire 5", "d:5", "d.5", "d5", "dr 5", "dair 5"
        elif not k.kullanildi and (s in ("daire", "dair", "dr", "d") or re.match(r"^(daire|d)[:.]?\d", k.kat)):
            deger = re.sub(r"^(daire|d)[:.]?", "", k.kat).strip(":.")
            idler = [i]
            if not deger and sonraki and re.fullmatch(r"\d{1,4}[a-z]?", sonraki.sade):
                deger = sonraki.sade
                idler.append(i + 1)
            if deger and re.fullmatch(r"\d{1,4}[a-z]?", deger):
                sonuc.daire = deger.upper()
                _isaretle(kelimeler, idler)

        # 8) Kat: "kat 3", "kat:3", "3. kat", "3.kat", "3 kat", "zemin kat", "k:3"
        elif not k.kullanildi and (s in ("kat", "kati") or re.match(r"^(kat|k)[:.]\d", k.kat) or re.fullmatch(r"\d{1,2}\.?kat", s)):
            gomulu = re.search(r"(-?\d{1,2})", k.kat)
            idler = [i]
            deger = None
            onceki_k = kelimeler[i - 1] if i > 0 and not kelimeler[i - 1].kullanildi else None
            if gomulu:
                deger = gomulu.group(1)
            elif onceki_k and re.fullmatch(r"-?\d{1,2}\.", onceki_k.kat.rstrip(",")):
                # "3. kat" (sira sayisi) "kat 7"den once gelir: "3. kat 7 numara" -> kat 3, kapi 7
                deger = onceki_k.sade.rstrip(".")
                idler.append(i - 1)
            elif sonraki and re.fullmatch(r"-?\d{1,2}", sonraki.sade):
                deger = sonraki.sade
                idler.append(i + 1)
            elif i > 0 and not kelimeler[i - 1].kullanildi and (re.fullmatch(r"-?\d{1,2}\.?", kelimeler[i - 1].sade) or kelimeler[i - 1].sade in KAT_OZEL):
                onceki = kelimeler[i - 1].sade.rstrip(".")
                deger = KAT_OZEL.get(onceki, onceki)
                idler.append(i - 1)
            if deger:
                sonuc.kat = deger
                _isaretle(kelimeler, idler)

        # 9) Blok: "a blok", "blok a", "a1 blok", "b-2 blok", "blk c"
        elif not k.kullanildi and s in ("blok", "blk", "blogu", "blok:"):
            if i > 0 and not kelimeler[i - 1].kullanildi and re.fullmatch(r"[a-z0-9]{1,3}(-?\d{1,2})?", kelimeler[i - 1].sade):
                sonuc.blok = kelimeler[i - 1].sade.upper()
                _isaretle(kelimeler, [i - 1, i])
            elif sonraki and re.fullmatch(r"[a-z0-9]{1,3}(-?\d{1,2})?", sonraki.sade):
                sonuc.blok = sonraki.sade.upper()
                _isaretle(kelimeler, [i, i + 1])

        # 10) Bina / site / apartman: "gul apt.", "yesil vadi sitesi", "x is merkezi"
        elif not k.kullanildi and (s in BINA_TURLERI or (s == "is" and sonraki and sonraki.sade in ("merkezi", "hani"))):
            tur = BINA_TURLERI.get(s, "is_merkezi")
            ad, idler = _ad_oncesi(kelimeler, i, 4)
            if ad and not sonuc.bina:
                sonuc.bina = _baslik(ad)
                sonuc.bina_turu = tur
                _isaretle(kelimeler, idler + [i] + ([i + 1] if s == "is" else []))
                son_bina = i + (1 if s == "is" else 0)
        i += 1

    # 11) Anahtar kelimesiz kapi: "12/5" (kapi + daire), "12 nolu", "12 numarali"
    if not sonuc.kapi_no:
        for j, k in enumerate(kelimeler):
            if k.kullanildi:
                continue
            arkasi = kelimeler[j + 1] if j + 1 < n else None
            if re.fullmatch(r"\d{1,5}[a-z]?/\d{1,4}[a-z]?", k.sade):
                _kapi_yaz(sonuc, k.sade)
                k.kullanildi = True
                break
            if re.fullmatch(r"\d{1,5}[a-z]?", k.sade) and arkasi and arkasi.sade in ("nolu", "numarali", "no'lu", "numara", "no"):
                _kapi_yaz(sonuc, k.sade)
                k.kullanildi = arkasi.kullanildi = True
                break

    # 12) Posta kodu (kullanilmamis 5 haneli)
    for k in kelimeler:
        if not k.kullanildi and _POSTA.fullmatch(k.sade):
            sonuc.posta_kodu = k.sade
            k.kullanildi = True
            break

    # 13) Kalan kelimeler: il / ilce adaylari (dogrulamada n-gram olarak denenir) ve kalan metin
    kalan = [k for k in kelimeler if not k.kullanildi]
    sonuc.kalan = " ".join(k.ozgun.strip(",") for k in kalan).strip()
    return sonuc


def _kapi_yaz(sonuc: Ayrisim, deger: str) -> None:
    """'12', '12a', '12/5' (kapi 12, daire 5), '12-5' -> kapi ve daire."""
    m = _NO_DEGERI.match(deger.replace(" ", ""))
    if not m:
        return
    sonuc.kapi_no = m.group(1).upper() + (m.group(2) or "").upper()
    if m.group(3) and not sonuc.daire:
        sonuc.daire = m.group(3) + (m.group(4) or "").upper()


def kelime_gruplari(metin: str, en_fazla: int = 3) -> list[str]:
    """Metindeki ardisik 1..en_fazla kelimelik katlanmis gruplar (il / ilce / mahalle adayi aramak icin)."""
    kelimeler = [katla(k).strip(".,:;()") for k in re.split(r"[\s,/\\-]+", metin) if k.strip(".,:;()")]
    gruplar = []
    for boy in range(en_fazla, 0, -1):
        for i in range(len(kelimeler) - boy + 1):
            g = " ".join(kelimeler[i:i + boy])
            if len(g) >= 3 and not g.isdigit():
                gruplar.append(g)
    return list(dict.fromkeys(gruplar))
