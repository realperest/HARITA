# Entegrasyon rehberi

Ortak kurallar:
- Her istek `X-Harita-Anahtar: hk_...` basligi tasir. Basligi ayarlayamayan istemciler icin yolda anahtar: `/k/<anahtar>/osrm/...`.
- Tarayici anahtarlari projede `kaynaklar` ile kendi alan adiniza kisitlanir; sunucudan sunucuya cagrilar (Origin yok) kisitlanmaz, bu yuzden sunucu anahtarini tarayiciya vermeyin.
- Tum konumlar `lat`, `lon` (WGS84). Yanitlar JSON / GeoJSON.
- Kota proje basina dakika limitidir; asilinca `429` ve `Retry-After`.

## Uclarin tam listesi

| Alan | Uc | Not |
|---|---|---|
| Karo | `GET {karo}/tiles/turkiye/{z}/{x}/{y}.mvt`, TileJSON `{karo}/tiles/turkiye.json` | Anahtar istemez; `IZINLI_KOKEN_REGEX` ile kisitli. Yazi tipi ve simgeler `{karo}/assets/...` |
| Yapilandirma | `GET /v1/yapilandirma` | Karo, yazi tipi, simge adresleri |
| Rota | `POST /v1/rota` | Profil: auto, motosiklet, bisiklet, yaya; GeoJSON cizgi |
| Matris | `POST /v1/matris` | En fazla 50 x 50 |
| OSRM uyumlu | `GET /osrm/route/v1/{profil}/{lon,lat;lon,lat}` | Mevcut OSRM kodu yalniz adres degistirir |
| Valhalla tam API | `POST /valhalla/{route,optimized_route,isochrone,sources_to_targets,trace_route,trace_attributes,locate,expansion,status}` | Govde Valhalla'ya aynen gider: izokron, harita eslestirme, optimize rota vb. |
| Yerlesim | `GET /v1/yerlesim/ara`, `/nokta`, `/yakin`, `/{id}`, `/{id}/alt` | Il, ilce, mahalle / koy ve sehir-kasaba-koy-mezra-semt merkezleri |
| Adres ara | `GET /v1/adres/ara?q=` | Kapi numarasi (`namik kemal bulvari 12`), sokak, yer, yerlesim; `lat/lon` ile yakinlik, `tur`, `ust_id` filtre |
| Ters arama | `GET /v1/adres/nokta?lat=&lon=` | Adres metni, il / ilce / mahalle, en yakin sokak, kapi, yerler |
| Yer katmani | `GET /v1/adres/yerler?bati&guney&dogu&kuzey&tur=` | Haritada nokta olarak cizmek icin GeoJSON |
| Sokak / kapi | `GET /v1/adres/mahalle/{id}/sokaklar`, `/v1/adres/sokak/{id}?cizgi=true`, `/v1/adres/sokak/{id}/kapilar` | Acilir liste (ilce > mahalle > sokak > kapi) |
| Adres agaci | `GET /v1/adres/alt?ust=il:34` (ilce:, mahalle_koy:, sokak: ; `cocuk=bina|kapi`) | Acilir listeler tek uctan: il > ilce > mahalle/koy > sokak > site-bina / kapi |
| Sekil | `GET /v1/adres/sekil?tur=&id=` | Herhangi bir ogenin GeoJSON'u (sinir, sokak cizgisi, bina poligonu) |
| Site / bina | `GET /v1/adres/mahalle/{id}/binalar`, `/v1/adres/sokak/{id}/binalar`, `/v1/adres/bina/{id}` | Binanin sokagi `ek.sokak` icinde |
| Yer katmani (karo) | `GET /v1/adres/yerler/karo?x=&y=&z=15` | Karo bazli onbellekleme icin |
| Yakin yerler | `GET /v1/adres/yakin?lat&lon&yaricap_m&tur=akaryakit` | En yakin benzin, mola, otel vb. |
| Rota boyunca | `POST /v1/adres/rota-boyunca` `{koordinatlar, tur, tampon_m}` | Rota cizgisi boyunca yerler, rota sirasina gore |
| Nominatim uyumlu | `GET /nominatim/search?q=`, `/nominatim/reverse?lat=&lon=` | Nominatim bekleyen istemciler |
| Photon uyumlu | `GET /photon/api?q=`, `/photon/reverse` | Photon bekleyen istemciler (kendi indeksimizden) |
| Photon (ham) | `GET /v1/arama`, `/v1/ters-arama` | Gezegen Photon indeksi; kendi adres indeksimiz hazir oldugu icin ikincil |
| Yonetim | `/yonetim/*` | Proje, anahtar, izin, kaynak, kullanim |

## SIPARIS

- **Rota (backend):** `OSRM_ADRESI=https://HARITA-API/k/hk_.../osrm` (ic ag: gateway ic adresi). `yol_agi.py` degismez.
- **Harita (frontend):** Leaflet kalir; MapTiler karosu yerine `protomaps-leaflet@5.1.0` ile HARITA karosu:
  `leafletLayer({ url: '{karo}/tiles/turkiye/{z}/{x}/{y}.mvt', flavor: 'light', lang: 'tr' })`. Uydu / hibrit MapTiler'da kalir (ucretsiz kaynak yok).
- **Adres secimi (acilir listeler):** Ilce `GET /v1/yerlesim/ara?q=&tur=ilce` (il `ust_id`), mahalle / koy `GET /v1/yerlesim/{ilce}/alt?tur=mahalle_koy`,
  cadde / sokak `GET /v1/adres/mahalle/{mahalle}/sokaklar`, kapi `GET /v1/adres/sokak/{sokak}/kapilar`.
- **Pin -> adres:** `GET /v1/adres/nokta`. **Metin -> pin:** `GET /v1/adres/ara`.
- **Haritadaki renkli yer noktalari:** `GET /v1/adres/yerler` (z14+).
- **SIPARIS'te kalanlar:** teslimat bolgeleri, musteri adresleri, musteriden ogrenilen kapi numaralari (is mantigi). Veri kimligi eslemesi icin
  HARITA kayitlari `kaynak_anahtari` (osm:node:123 / osm:way:456 / sokak:...) tasir; SIPARIS'in OSM kaynakli satirlariyla ayni anahtarlar eslesir.
- **Gecis:** Adim adim, her adim ayri dagitimla; once rota, sonra karo, sonra adres. Eski uclar o zamana kadar calismaya devam eder.

## MotoConvoy

- **Harita:** `tile.openstreetmap.org` yerine HARITA karosu (MapLibre onerilir: `istemci/harita-istemci.js`; Leaflet ise `protomaps-leaflet`).
- **Rota ve varis hedefi:** `POST /v1/rota` (`"profil": "motosiklet"`), hedef arama `GET /v1/adres/ara`. OpenRouteService gunluk 2.000 istek siniri kalkar.
- **Kalan mesafe:** Telefon rotayi bir kez ister ve kendi hesaplar (plandaki mantik degismez); sunucu yalniz rota cizgisini verir.
- **Ek imkanlar:** `/valhalla/trace_attributes` (GPS izini yola oturtma), `/valhalla/isochrone` (erisim alani), `/valhalla/optimized_route` (durak sirasi), `/v1/adres/nokta` (hangi yol / mahalle).

## Yeni proje

1. `POST /yonetim/projeler` ile proje + anahtar (varsayilan tum servisler acik; `servisler` ile daraltilir).
2. Web: `istemci/harita-istemci.js` veya yukaridaki REST uclari. Mobil / sunucu: anahtar sunucuda, istekler sunucudan.

## Sinirlar

Rota en fazla 20 nokta, matris en fazla 50 x 50, Valhalla govdesi en fazla 2 MB, adres aramasi en fazla 50 sonuc.
Veri OpenStreetMap'e dayanir; kapi numarasi ve ad kapsami bolgeye gore degisir. Atif: (c) OpenStreetMap katkicilari.
