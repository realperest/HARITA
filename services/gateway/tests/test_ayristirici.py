"""Adres ayristiricinin saf (veritabanisiz) kurallari: kisaltmalar, yazim bicimleri, sira, kapi / daire / kat / blok, tarif."""

import pytest

from app.crud.adres_ayristir import benzerlik, cekirdek
from app.services.ayristirici import ayristir

ORNEKLER = [
    ("Cumhuriyet Mah. Atatürk Cad. No:12/5 Gül Apt. A Blok Kat 3 Çerkezköy/Tekirdağ",
     {"mahalle": "Cumhuriyet", "sokak": "Atatürk", "sokak_turu": "cadde", "kapi_no": "12", "daire": "5", "kat": "3", "blok": "A",
      "bina": "Gül", "bina_turu": "apartman", "ilce_aday": ["Çerkezköy"], "il_aday": ["Tekirdağ"]}),
    ("cumhuriyet mh atatürk cd no 12 daire 5 kat 3", {"mahalle": "Cumhuriyet", "sokak": "Atatürk", "kapi_no": "12", "daire": "5", "kat": "3"}),
    ("Fevzi Paşa Mahallesi 194. Sokak No: 7 D: 3", {"mahalle": "Fevzi Paşa", "sokak": "194", "sokak_turu": "sokak", "kapi_no": "7", "daire": "3"}),
    ("Kumru Sk. No.15 K:2 D:4", {"sokak": "Kumru", "kapi_no": "15", "kat": "2", "daire": "4"}),
    ("atatürk bulvarı 45/3 kadıköy istanbul", {"sokak": "Atatürk", "sokak_turu": "bulvar", "kapi_no": "45", "daire": "3"}),
    ("Yeşil Vadi Sitesi B-2 Blok Daire 14, 59500 Çerkezköy / Tekirdağ",
     {"bina": "Yeşil Vadi", "bina_turu": "site", "blok": "B-2", "daire": "14", "posta_kodu": "59500", "il_aday": ["Tekirdağ"]}),
    ("Bağlık mahallesi Çavuş sokağı numara 3 zemin kat", {"mahalle": "Bağlık", "sokak": "Çavuş", "kapi_no": "3", "kat": "Zemin"}),
    ("Kemalpaşa köyü 12 nolu ev, merkez camii yanı", {"koy": "Kemalpaşa", "kapi_no": "12", "tarif": "merkez camii yanı"}),
    ("ÇAVUŞ SOKAĞI NO 21A KAT:1 DAİRE:2 FATİH MAHALLESİ", {"mahalle": "Fatih", "sokak": "Çavuş", "kapi_no": "21A", "kat": "1", "daire": "2"}),
    ("1234 sk no 5 d 2 bornova izmir 0532 123 45 67", {"sokak": "1234", "kapi_no": "5", "daire": "2", "telefon_atildi": True}),
    ("moda cd. 120 kadıköy", {"sokak": "Moda", "sokak_turu": "cadde", "kapi_no": "120"}),
    ("Barbaros Bulvarı Akmerkez İş Merkezi Kat 12 Beşiktaş/İstanbul",
     {"sokak": "Barbaros", "bina": "Akmerkez", "bina_turu": "is_merkezi", "kat": "12", "ilce_aday": ["Beşiktaş"]}),
    ("Bağdat Cad. No:J2", {"sokak": "Bağdat", "kapi_no": "J2"}),
    ("Plaj Yolu sokağı 8", {"sokak": "Plaj Yolu", "sokak_turu": "sokak", "kapi_no": "8"}),
    ("Sigorta Evleri Sk. No:5", {"sokak": "Sigorta Evleri", "sokak_turu": "sokak", "kapi_no": "5", "bina": None}),
    ("No 12 A Atatürk Cad.", {"kapi_no": "12A", "sokak": "Atatürk"}),
    ("3. kat 7 numara Lale sokak", {"kat": "3", "sokak": "Lale", "kapi_no": "7"}),
]


@pytest.mark.parametrize("metin,beklenen", ORNEKLER)
def test_ayristirma_kurallari(metin, beklenen):
    sonuc = ayristir(metin).sozluk()
    for alan, deger in beklenen.items():
        assert sonuc[alan] == deger, f"{alan}: {sonuc[alan]!r} != {deger!r} ({metin})"


def test_cekirdek_ve_benzerlik():
    assert cekirdek("Cumhuriyet Mahallesi") == cekirdek("cumhuriyet mah.") == "cumhuriyet"
    assert cekirdek("Plaj Yolu Sokağı") == "plaj"
    assert benzerlik("sogutlucesme", "souigtlucesme") > 0.8          # yazim hatasi
    assert benzerlik("hamdi bey", "hamdibey") == 1.0                 # bosluk farki
    assert benzerlik("lalezar", "lalezar lalezar") < 0.85            # tekrarlanan kelime tam eslesme sayilmaz
    assert benzerlik("aydin", "ayhan") < 0.85
