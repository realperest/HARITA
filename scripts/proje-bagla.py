"""Bir projeyi HARITA servisine tek komutla baglamaya hazirlar.

Her proje icin iki kayit acilir:
    <ad>-sunucu  Arka uc (backend) anahtari: kaynak kisiti yok, yuksek kota. Yalniz sunucuda tutulur, tarayiciya verilmez.
    <ad>-web     Tarayici / mobil anahtari: yalniz izinli alan adlarindan (Origin) calisir, dusuk kota.
Anahtarlar yalniz bir kez gorunur; betik onlari git disi bir .env dosyasina yazar ve ekrana basmaz.

Kullanim:
    python scripts/proje-bagla.py siparis              Hazir ayarli proje (siparis, motoconvoy)
    python scripts/proje-bagla.py yeniproje --web https://yeniproje.com --web https://panel.yeniproje.com
    python scripts/proje-bagla.py siparis --kuru       Ne yapilacagini gosterir, hicbir sey degistirmez
    python scripts/proje-bagla.py siparis --yeni-anahtar   Var olan projelere yeni anahtar uretir (eski anahtarlar acik kalir)
    python scripts/proje-bagla.py --liste              Kayitli projeleri listeler

Ortam degiskenleri:
    HARITA_YONETIM_ANAHTARI  Zorunlu (Coolify'da harita uygulamasinin YONETIM_ANAHTARI degeri)
    HARITA_API               Varsayilan: https://harita-api.89.45.45.152.sslip.io
    HARITA_KARO              Varsayilan: https://harita-karo.89.45.45.152.sslip.io

Yalniz Python standart kutuphanesi kullanilir.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API = os.environ.get("HARITA_API", "https://harita-api.89.45.45.152.sslip.io").rstrip("/")
KARO = os.environ.get("HARITA_KARO", "https://harita-karo.89.45.45.152.sslip.io").rstrip("/")
YONETIM = os.environ.get("HARITA_YONETIM_ANAHTARI", "")
TUM_SERVISLER = ["rota", "matris", "arama", "yapilandirma", "yerlesim", "adres", "valhalla"]

# Mobil uygulama kabuklari (Capacitor / Ionic) bu kokenlerden istek atar
MOBIL_KOKENLER = ["https://localhost", "capacitor://localhost", "http://localhost"]

HAZIR_AYARLAR = {
    "siparis": {
        "aciklama": "SIPARIS / Lezzet Sepeti (isletme paneli, musteri sitesi, kurye, backend)",
        "web": [
            "https://isletme.lezzetsepeti.net", "https://musteri.lezzetsepeti.net", "https://lezzetsepeti.net",
            "https://www.lezzetsepeti.net", "https://siparis-isletme.89.45.45.152.sslip.io",
            "https://siparis-musteri.89.45.45.152.sslip.io", "https://siparis-admin.89.45.45.152.sslip.io",
        ],
        "mobil": True,
        "sunucu_limit": 3000,
        "web_limit": 1200,
    },
    "motoconvoy": {
        "aciklama": "MotoConvoy (canli konvoy, rota ve varis hedefi; web ve Android)",
        "web": ["https://motoconvoy.net", "https://www.motoconvoy.net", "https://app.motoconvoy.net",
                "https://motokonus.89.45.45.152.sslip.io"],
        "mobil": True,
        "sunucu_limit": 3000,
        "web_limit": 1200,
    },
}


def istek(yontem: str, yol: str, govde: dict | None = None) -> tuple[int, object]:
    """Yonetim anahtariyla istek atar; (durum, json) dondurur."""
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    r = urllib.request.Request(f"{API}{yol}", data=veri, method=yontem, headers={
        "X-Yonetim-Anahtari": YONETIM, "Content-Type": "application/json", "User-Agent": "harita-proje-bagla/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=30) as y:
            return y.status, json.loads(y.read() or b"null")
    except urllib.error.HTTPError as h:
        try:
            return h.code, json.loads(h.read() or b"null")
        except ValueError:
            return h.code, None


def anahtarla_dene(anahtar: str, koken: str | None = None) -> int:
    """Uretilen anahtarla /v1/yapilandirma cagirir; HTTP durumunu dondurur."""
    basliklar = {"X-Harita-Anahtar": anahtar, "User-Agent": "harita-proje-bagla/1.0"}
    if koken:
        basliklar["Origin"] = koken
    r = urllib.request.Request(f"{API}/v1/yapilandirma", headers=basliklar)
    try:
        with urllib.request.urlopen(r, timeout=30) as y:
            return y.status
    except urllib.error.HTTPError as h:
        return h.code


def projeleri_al() -> dict[str, dict]:
    """Kayitli projeler (ad -> kayit)."""
    durum, veri = istek("GET", "/yonetim/projeler")
    if durum != 200:
        raise SystemExit(f"Proje listesi alinamadi (HTTP {durum}). Yonetim anahtarini kontrol edin.")
    return {p["ad"]: p for p in veri}


def proje_saglama(ad: str, aciklama: str, limit: int, kaynaklar: list[str], mevcut: dict, kuru: bool, yeni_anahtar: bool) -> str | None:
    """Projeyi yoksa olusturur, varsa ayarlarini esitler. Yeni uretilen anahtari dondurur (uretilmediyse None)."""
    if ad not in mevcut:
        print(f"  + {ad}: olusturulacak (kota {limit}/dk, {len(kaynaklar) or 'kisitsiz'} kaynak)")
        if kuru:
            return None
        durum, veri = istek("POST", "/yonetim/projeler", {"ad": ad, "aciklama": aciklama, "dakika_limiti": limit,
                                                         "servisler": TUM_SERVISLER, "kaynaklar": kaynaklar})
        if durum != 201:
            raise SystemExit(f"{ad} olusturulamadi (HTTP {durum}): {veri}")
        return veri["anahtar"]
    kayit = mevcut[ad]
    print(f"  = {ad}: zaten var (id {kayit['id']}); kaynaklar ve kota esitleniyor")
    if not kuru:
        durum, veri = istek("PATCH", f"/yonetim/projeler/{kayit['id']}", {"aktif": True, "dakika_limiti": limit,
                                                                         "servisler": TUM_SERVISLER, "kaynaklar": kaynaklar})
        if durum != 200:
            raise SystemExit(f"{ad} guncellenemedi (HTTP {durum}): {veri}")
    if not yeni_anahtar:
        return None
    print(f"  + {ad}: yeni anahtar uretilecek")
    if kuru:
        return None
    durum, veri = istek("POST", f"/yonetim/projeler/{kayit['id']}/anahtarlar")
    if durum != 201:
        raise SystemExit(f"{ad} icin anahtar uretilemedi (HTTP {durum}): {veri}")
    return veri["anahtar"]


def env_yaz(dosya: Path, proje: str, sunucu: str | None, web: str | None, kaynaklar: list[str]) -> None:
    """Projenin kullanacagi ortam degiskenlerini git disi dosyaya yazar."""
    zaman = datetime.now().strftime("%d.%m.%Y %H:%M")
    satirlar = [
        f"# HARITA baglanti bilgileri: {proje} ({zaman})",
        "# GIZLI: bu dosyayi depoya koymayin. Degerleri projenin Coolify / Cloudflare ortam degiskenlerine girin.",
        "",
        "# --- Arka uc (backend, Coolify) ---",
        f"HARITA_API_ADRESI={API}",
        f"HARITA_KARO_ADRESI={KARO}",
    ]
    if sunucu:
        satirlar += [f"HARITA_SUNUCU_ANAHTARI={sunucu}",
                     "# OSRM kullanan kod icin (SIPARIS yol_agi.py): adres degisir, kod degismez",
                     f"OSRM_ADRESI={API}/k/{sunucu}/osrm"]
    else:
        satirlar.append("# HARITA_SUNUCU_ANAHTARI: bu calistirmada yeni anahtar uretilmedi (onceki dosyadaki deger gecerli)")
    satirlar += ["", "# --- Tarayici / mobil (Vite: derleme zamaninda, Cloudflare Pages ortam degiskeni) ---",
                 f"VITE_HARITA_API_ADRESI={API}", f"VITE_HARITA_KARO_ADRESI={KARO}"]
    if web:
        satirlar.append(f"VITE_HARITA_ANAHTARI={web}")
    else:
        satirlar.append("# VITE_HARITA_ANAHTARI: bu calistirmada yeni anahtar uretilmedi (onceki dosyadaki deger gecerli)")
    satirlar += ["", "# Tarayici anahtarinin calistigi kokenler:"] + [f"#   {k}" for k in kaynaklar] + [""]
    dosya.parent.mkdir(parents=True, exist_ok=True)
    if dosya.exists():
        yedek = dosya.with_name(f"{dosya.stem}_{datetime.now():%y%m%d_%H%M%S}.env")
        dosya.replace(yedek)
        print(f"  Onceki dosya saklandi: {yedek}")
    dosya.write_text("\n".join(satirlar), encoding="utf-8")


def main() -> int:
    """Komut satirini isler."""
    ap = argparse.ArgumentParser(description="Projeyi HARITA servisine baglamaya hazirlar.")
    ap.add_argument("ad", nargs="?", help="Proje adi (or. siparis, motoconvoy, yeniproje)")
    ap.add_argument("--web", action="append", default=[], help="Tarayici anahtarinin calisacagi alan adi (birden cok verilebilir)")
    ap.add_argument("--mobil", action="store_true", help="Mobil uygulama kokenlerini de izinli yap (Capacitor)")
    ap.add_argument("--sunucu-limit", type=int, help="Arka uc anahtari dakika limiti")
    ap.add_argument("--web-limit", type=int, help="Tarayici anahtari dakika limiti")
    ap.add_argument("--yeni-anahtar", action="store_true", help="Var olan projelere yeni anahtar uret")
    ap.add_argument("--kuru", action="store_true", help="Yalniz goster, degistirme")
    ap.add_argument("--cikti", default=str(Path(__file__).resolve().parent.parent / "baglantilar"),
                    help="Anahtar dosyalarinin klasoru (git disi)")
    ap.add_argument("--liste", action="store_true", help="Kayitli projeleri listele")
    a = ap.parse_args()

    if not YONETIM:
        print("HARITA_YONETIM_ANAHTARI ortam degiskeni gerekli.", file=sys.stderr)
        return 2
    mevcut = projeleri_al()
    if a.liste:
        for p in mevcut.values():
            print(f"{p['id']:>3}  {p['ad']:<28} {'aktif' if p['aktif'] else 'kapali':<7} {p['dakika_limiti']:>6}/dk  "
                  f"{len([k for k in p['anahtarlar'] if k['aktif']])} anahtar  {', '.join(p['kaynaklar']) or 'kaynak kisitsiz'}")
        return 0
    if not a.ad:
        ap.error("proje adi gerekli")

    ad = a.ad.strip().lower()
    hazir = HAZIR_AYARLAR.get(ad, {})
    web_kokenleri = list(dict.fromkeys([k.rstrip("/") for k in (hazir.get("web", []) + a.web)]))
    if hazir.get("mobil") or a.mobil:
        web_kokenleri += [k for k in MOBIL_KOKENLER if k not in web_kokenleri]
    if not web_kokenleri:
        ap.error("izinli alan adi yok: --web https://... verin (hazir ayarlar: " + ", ".join(HAZIR_AYARLAR) + ")")
    aciklama = hazir.get("aciklama", ad)
    sunucu_limit = a.sunucu_limit or hazir.get("sunucu_limit", 3000)
    web_limit = a.web_limit or hazir.get("web_limit", 1200)

    print(f"{ad}: HARITA baglantisi hazirlaniyor{' (KURU CALISMA)' if a.kuru else ''}")
    sunucu = proje_saglama(f"{ad}-sunucu", f"{aciklama} - arka uc", sunucu_limit, [], mevcut, a.kuru, a.yeni_anahtar)
    web = proje_saglama(f"{ad}-web", f"{aciklama} - tarayici / mobil", web_limit, web_kokenleri, mevcut, a.kuru, a.yeni_anahtar)
    if a.kuru:
        print("Kuru calisma: hicbir sey degistirilmedi.")
        return 0

    dosya = Path(a.cikti) / f"{ad}.env"
    if sunucu or web:
        env_yaz(dosya, ad, sunucu, web, web_kokenleri)
        print(f"  Anahtarlar yazildi: {dosya}")
    else:
        print("  Yeni anahtar uretilmedi (projeler zaten vardi). Anahtar kaybolduysa --yeni-anahtar ile yenisini uretin.")

    # Uretilen anahtarlari dogrula: sunucu anahtari kokensiz, web anahtari izinli kokenle calismali, yabanci kokenle reddedilmeli
    hata = 0
    if sunucu:
        d = anahtarla_dene(sunucu)
        print(f"  Kontrol: sunucu anahtari -> HTTP {d}")
        hata += d != 200
    if web:
        d1 = anahtarla_dene(web, web_kokenleri[0])
        d2 = anahtarla_dene(web, "https://yabanci-site.example")
        print(f"  Kontrol: web anahtari izinli kokenden -> HTTP {d1}, yabanci kokenden -> HTTP {d2} (403 beklenir)")
        hata += d1 != 200 or d2 != 403
    print("Hazir." if not hata else "Kontrollerden biri basarisiz; ayrinti yukarida.")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
