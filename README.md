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
| `db`, `redis` | PostGIS 17, Redis 7 | Proje / anahtar kayitlari, kota sayaclari ve yerlesim verisi | Hayir |

Neden bu secimler: karolar tek dosyadir (PMTiles), sunucu CPU'su yemez, Cloudflare onbellegine uygundur ve MapTiler gibi
ucretli/kotali dis servise ihtiyac birakmaz. Valhalla bellege eslemeli cizge kullandigi icin tum Turkiye'yi OSRM'den dusuk
bellekle tasir ve motosiklet profili vardir.

## Bir projeyi baglamak

1. Yonetici anahtariyla proje olusturun (anahtar yalniz bu yanitta gorunur):

```bash
curl -X POST https://HARITA-API/yonetim/projeler -H "X-Yonetim-Anahtari: ..." -H "Content-Type: application/json" \
  -d '{"ad":"siparis","kaynaklar":["https://musteri.lezzetsepeti.net"],"dakika_limiti":1200}'
```

2. Projede `X-Harita-Anahtar: hk_...` basligiyla cagirin. Ayrintilar: [docs/ENTEGRASYON.md](docs/ENTEGRASYON.md).
3. Izin verdiginiz baska kisiler icin de ayri proje + anahtar olusturun; anahtari istediginiz an kapatabilirsiniz
   (`DELETE /yonetim/projeler/{id}/anahtarlar/{on_ek}`), kullanimi `GET /yonetim/projeler/{id}/kullanim` ile izlersiniz.

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
| `GET /v1/adres/ara`, `/nokta`, `/yerler`, `/mahalle/{id}/sokaklar`, `/sokak/{id}` | Sokak, kapi numarasi, onemli yerler: arama, ters arama, harita katmani, acilir listeler |
| `GET /nominatim/*`, `/photon/*` | Nominatim ve Photon uyumlu uclar (kendi adres indeksimizden) |
| `POST /valhalla/{route,isochrone,optimized_route,trace_attributes,...}` | Valhalla'nin tum API'si (izokron, harita eslestirme, optimize rota) |
| `/yonetim/*` | Proje ve anahtar yonetimi |
| `GET /saglik`, `GET /saglik/hazir` | Canlilik / hazirlik |

## Yayin

Coolify'a Docker Compose kaynagi olarak yayinlanir: [docs/YAYIN.md](docs/YAYIN.md). Ilk acilista veri indirmesi ve indeks uretimi
yapilir (karo birkac GB, rota cizgesi ~20-60 dk, arama indeksi saatler); sonraki acilislar hazir veriyle baslar.

## Gelistirme

```bash
cd services/gateway
pip install -r requirements-dev.txt
pytest   # PostgreSQL (55432) ve Redis (56379) gerekir, bkz. tests/conftest.py
```

## Istemci

`istemci/harita-istemci.js`: MapLibre haritasi kurar, rota / matris / arama cagirir. Derleyici gerektirmez.
