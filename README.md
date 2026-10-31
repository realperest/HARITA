# HARITA

Tum projelerin ortak harita servisi. Harita verisi hicbir projenin icine gomulmez; projeler HTTP ile bu servisi kullanir.
Tek anahtar (maymuncuk): SIPARIS, MotoConvoy ve ileride yapilacak her proje ayni servise kendi anahtariyla baglanir.

Kapsam: tum Turkiye. Veri: OpenStreetMap (c) OpenStreetMap katkicilari (ODbL).

## Servisler

| Servis | Teknoloji | Ne yapar | Dis erisim |
|---|---|---|---|
| `tiles` | Protomaps PMTiles + nginx | Vektor harita karolari, yazi tipleri, simgeler | Evet (alan adi, onbellekli) |
| `rota` | Valhalla | Rota, sure/mesafe matrisi (auto, motosiklet, bisiklet, yaya) | Hayir (ic ag) |
| `gateway` | FastAPI | Proje anahtari, izin, kaynak kisiti, kota, kullanim sayaci, OSRM uyumlu rota | Evet (alan adi) |
| `veri` | Python + osmium | Turkiye il / ilce / mahalle-koy sinirlarini, sokaklari, kapi numaralarini, yerleri ve adlandirilmis binalari OSM'den yukler, aylik tazeler. Adres aramasi bu veriden yapilir (dis servis yok) | Hayir |
| `harita-db`, `harita-redis` | PostGIS 17, Redis 7 (Coolify'in ayri kaynaklari, compose disinda) | Proje / anahtar kayitlari, adres ve yerlesim verisi, kota sayaclari | Hayir |
| `harita-deneme` | nginx (ayri Coolify uygulamasi, `deneme/`) | Deneme haritasi, veritabani araci, navigasyon denemesi | Evet |

Neden bu secimler: karolar tek dosyadir (PMTiles), sunucu CPU'su yemez, Cloudflare onbellegine uygundur ve MapTiler gibi
ucretli/kotali dis servise ihtiyac birakmaz. Valhalla bellege eslemeli cizge kullandigi icin tum Turkiye'yi OSRM'den dusuk
bellekle tasir ve motosiklet profili vardir.

## Bir projeyi baglamak (tek komut)

```bash
HARITA_YONETIM_ANAHTARI=... python scripts/proje-bagla.py siparis          # hazir ayarli: siparis, motoconvoy
HARITA_YONETIM_ANAHTARI=... python scripts/proje-bagla.py yeniproje --web https://yeniproje.com
```

Betik projeye iki anahtar acar (arka uc `<ad>-sunucu`, tarayici / mobil `<ad>-web`), anahtarlari git disi
`baglantilar/<ad>.env` dosyasina projenin kullanacagi ortam degiskeni adlariyla yazar ve ikisini canli servise karsi dogrular.
Projede yapilacaklar ve istemci kutuphaneleri: [docs/ENTEGRASYON.md](docs/ENTEGRASYON.md).
Anahtari istediginiz an kapatabilirsiniz (`DELETE /yonetim/projeler/{id}/anahtarlar/{on_ek}`), kullanimi
`GET /yonetim/projeler/{id}/kullanim` ile izlersiniz.

## Canli test

```bash
HARITA_ANAHTAR=... HARITA_YONETIM_ANAHTARI=... python scripts/canli-test.py
```

Karo, rota, Valhalla, arama, adres, yerlesim, uyumlu uclar, yonetim ve deneme sayfalarini uctan uca dener (60'a yakin kontrol).

## Uclar (gateway)

| Yol | Aciklama |
|---|---|
| `GET /v1/yapilandirma` | Karo, yazi tipi, simge adresleri |
| `POST /v1/rota` | Noktalar arasi rota (sure, mesafe, GeoJSON) |
| `POST /v1/matris` | Sure / mesafe matrisi |
| `GET /v1/arama`, `GET /v1/ters-arama` | Adres / yer arama |
| `GET /osrm/route/v1/{profil}/{koordinatlar}` | OSRM uyumlu rota (mevcut OSRM kullanan kodu degistirmeden baglar) |
| `GET /k/{anahtar}/osrm/route/v1/...` | Ayni uc, anahtar yolda (baslik ayarlanamayan istemciler icin) |
| `GET /v1/yerlesim/ara` | Il, ilce, mahalle-koy, sehir, kasaba, koy, mezra, semt arama (Turkce karakter duyarsiz) |
| `GET /v1/yerlesim/nokta` | Noktanin il / ilce / mahalle-koy bilgisi ve en yakin merkez |
| `GET /v1/yerlesim/yakin` | Yaricap icindeki merkezler |
| `GET /v1/yerlesim/{id}`, `/{id}/alt` | Ayrinti (zincir, GeoJSON sinir) ve alt ogeler (ilin ilceleri vb.) |
| `GET /v1/adres/ara`, `/nokta`, `/yerler`, `/alt`, `/mahalle/{id}/sokaklar`, `/sokak/{id}`, `/sokak/{id}/en-yakin-kapi` | Sokak, kapi numarasi, onemli yerler: arama (yakinlik, yaricap), ters arama, harita katmani, acilir listeler, kapi onerisi |
| `POST /v1/adres/toplu`, `POST /v1/adres/kaynak` | Toplu getirme (ad, zincir kimlikleri) ve OSM kaynak anahtariyla esleme |
| `GET /v1/yol/nokta` | Konumdaki yolun ozellikleri (sinif, hiz, trafik isigi, tunel, gise ...) |
| `GET /v1/baglanti/coz` | Google / Yandex / Apple / Waze baglantisindan noktalar |
| `GET /nominatim/*`, `/photon/*` | Nominatim ve Photon uyumlu uclar (kendi adres indeksimizden) |
| `POST /valhalla/{route,isochrone,optimized_route,trace_attributes,...}` | Valhalla'nin tum API'si (izokron, harita eslestirme, optimize rota) |
| `/yonetim/*` | Proje ve anahtar yonetimi |
| `GET /saglik`, `GET /saglik/hazir` | Canlilik / hazirlik |

## Yayin

Coolify'a Docker Compose kaynagi olarak yayinlanir: [docs/YAYIN.md](docs/YAYIN.md). Ilk acilista veri indirmesi ve indeks uretimi
yapilir (karo birkac GB, rota cizgesi ~20-60 dk, adres indeksi ~1 saat); sonraki acilislar hazir veriyle baslar.
Main'e gonderim dagitimi kendiliginden baslatmaz; Coolify'da yeniden dagitim gerekir.

## Gelistirme

```bash
cd services/gateway
pip install -r requirements-dev.txt
pytest   # PostgreSQL (55432) ve Redis (56379) gerekir, bkz. tests/conftest.py
```

## Istemci

- `istemci/harita-istemci.js` (tarayici): MapLibre haritasi kurar; rota, matris, arama, adres, yerlesim, Valhalla. Derleyici gerektirmez.
- `istemci/harita_istemci.py` (arka uc, httpx): ayni uclarin asenkron Python sarmalayicisi.
