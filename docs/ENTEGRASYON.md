# Entegrasyon rehberi

## Tek komutla baglama

```bash
HARITA_YONETIM_ANAHTARI=... python scripts/proje-bagla.py siparis       # SIPARIS / Lezzet Sepeti (hazir ayar)
HARITA_YONETIM_ANAHTARI=... python scripts/proje-bagla.py motoconvoy    # MotoConvoy (hazir ayar)
HARITA_YONETIM_ANAHTARI=... python scripts/proje-bagla.py yeniproje --web https://yeniproje.com [--mobil]
```

Betik her proje icin iki kayit acar ve canli servise karsi dogrular:

| Kayit | Nerede kullanilir | Kaynak kisiti | Kota |
|---|---|---|---|
| `<ad>-sunucu` | Arka uc (FastAPI, Coolify ortam degiskeni). Tarayiciya hic gitmez | Yok (sunucudan sunucuya) | 3.000 / dk |
| `<ad>-web` | Tarayici ve mobil uygulama (Vite derleme degiskeni) | Yalniz projenin alan adlari ve mobil kabuk kokenleri | 1.200 / dk |

Anahtarlar git disi `baglantilar/<ad>.env` dosyasina projenin kullanacagi adlarla yazilir:

| Degisken | Nereye |
|---|---|
| `HARITA_API_ADRESI`, `HARITA_SUNUCU_ANAHTARI` | Projenin backend'i (Coolify ortam degiskeni) |
| `OSRM_ADRESI` | OSRM bekleyen kod (SIPARIS `yol_agi.py`): yalniz adres degisir |
| `VITE_HARITA_API_ADRESI`, `VITE_HARITA_KARO_ADRESI`, `VITE_HARITA_ANAHTARI` | Frontend derlemesi (Cloudflare Pages ortam degiskeni) |

Betik tekrar calistirilinca anahtar uretmez, yalniz alan adlarini ve kotayi esitler; anahtar kaybolursa `--yeni-anahtar`.
Hazir ayarlarin alan adlari `scripts/proje-bagla.py` icindeki `HAZIR_AYARLAR`'dadir; yeni alan adi eklenince betik yeniden calistirilir.
Projeyi gercekten baglamak, yukaridaki degiskenleri o projenin ortamina girip kodunu asagidaki uclara cevirmektir (proje bazinda ayri is).

### Istemci kutuphaneleri

- **Arka uc (Python):** `istemci/harita_istemci.py` dosyasini projeye kopyalayin (gereksinim `httpx==0.28.1`).

```python
from harita_istemci import HaritaIstemcisi, HaritaHatasi
harita = HaritaIstemcisi()                     # HARITA_API_ADRESI, HARITA_SUNUCU_ANAHTARI ortamdan
rota = await harita.rota([(40.99, 29.02), (40.98, 29.03)], profil="motosiklet")
adres = await harita.adres_nokta(40.99, 29.02)    # pin -> adres
talimat = await harita.adim_adim_rota([(40.99, 29.02), (40.98, 29.03)])   # Turkce navigasyon talimatlari
```

- **Tarayici (JS, derleyicisiz):** `istemci/harita-istemci.js` (3D bina icin ayrica `istemci/harita-3d.js`: `harita.addControl(new UcBoyutKontrolu({ tema: 'dark' }))`)

```js
import { HaritaIstemcisi } from './harita-istemci.js';
const h = new HaritaIstemcisi(import.meta.env.VITE_HARITA_API_ADRESI, import.meta.env.VITE_HARITA_ANAHTARI);
const harita = await h.harita({ kap: 'harita', tema: 'light' });
const rota = await h.rota([{ lat: 40.99, lon: 29.02 }, { lat: 40.98, lon: 29.03 }], 'motosiklet');
```

- **Hazir ekranlar:** `deneme/index.html` (harita, arama, rota, katmanlar) ve `deneme/navigasyon.html` (sesli adim adim navigasyon)
  kopyalanip uyarlanabilir ornekler olarak durur.

## Ortak kurallar
- Her istek `X-Harita-Anahtar: hk_...` basligi tasir. Basligi ayarlayamayan istemciler icin yolda anahtar: `/k/<anahtar>/osrm/...`.
- Tarayici anahtarlari projede `kaynaklar` ile kendi alan adiniza kisitlanir; sunucudan sunucuya cagrilar (Origin yok) kisitlanmaz, bu yuzden sunucu anahtarini tarayiciya vermeyin.
- Karo sunucusu (anahtar istemez) yalniz `IZINLI_KOKEN_REGEX` kokenlerine CORS izni verir: `*.lezzetsepeti.net`, `*.motoconvoy.net`,
  `*.89.45.45.152.sslip.io`, `localhost` ve mobil kabuklar (`https://localhost`, `capacitor://localhost`). Yeni alan adi icin Coolify'da
  `harita` uygulamasinin bu degiskenine eklenir ve uygulama yeniden dagitilir.
- Mobil uygulama (Capacitor / WebView) web anahtarini kullanir; TWA gibi gercek alan adindan acilan kabuklar ek ayar istemez.
- Tum konumlar `lat`, `lon` (WGS84). Yanitlar JSON / GeoJSON.
- Kota proje basina dakika limitidir; asilinca `429` ve `Retry-After`.

## Uclarin tam listesi

| Alan | Uc | Not |
|---|---|---|
| Karo | `GET {karo}/tiles/turkiye/{z}/{x}/{y}.mvt`, TileJSON `{karo}/tiles/turkiye.json` | Anahtar istemez; `IZINLI_KOKEN_REGEX` ile kisitli. Yazi tipi ve simgeler `{karo}/assets/...` |
| Yapilandirma | `GET /v1/yapilandirma` | Karo, yazi tipi, simge adresleri |
| Rota | `POST /v1/rota` | Profil: auto, motosiklet, bisiklet, yaya; en fazla 50 nokta; GeoJSON cizgi |
| Navigasyon ekrani | `navigasyon.html?duraklar=lat,lon;lat,lon&adlar=A|B&profil=araba` (ya da `hedef=`, `baglanti=`) | Sesli Turkce adim adim, cok duraklı; Yandex / Google yonlendirmesi yerine baglanti olarak verilir (`navigasyon_baglantisi()` / `navigasyonBaglantisi()`) |
| Matris | `POST /v1/matris` | En fazla 50 x 50 |
| OSRM uyumlu | `GET /osrm/route/v1/{profil}/{lon,lat;lon,lat}` | Mevcut OSRM kodu yalniz adres degistirir |
| Valhalla tam API | `POST /valhalla/{route,optimized_route,isochrone,sources_to_targets,trace_route,trace_attributes,locate,expansion,status}` | Govde Valhalla'ya aynen gider: izokron, harita eslestirme, optimize rota vb. |
| Yerlesim | `GET /v1/yerlesim/ara`, `/nokta`, `/yakin`, `/{id}`, `/{id}/alt` | Il, ilce, mahalle / koy ve sehir-kasaba-koy-mezra-semt merkezleri |
| Adres ara | `GET /v1/adres/ara?q=` | Kapi numarasi (`namik kemal bulvari 12`), sokak, yer, yerlesim; `lat/lon` ile esit eslesmelerde yakin olan once, `yaricap_m` ile yaricap disi elenir, `tur`, `ust_id` filtre |
| Adres ayristirma | `POST /v1/adres/ayristir` `{metin \| metinler[], lat?, lon?, ilce_id?}` | Serbest adres (WhatsApp, telefon notu, form) -> il, ilce, mahalle / koy, sokak, kapi no, bina / site, blok, kat, daire, posta kodu, tarif; veritabaniyla dogrulama, yazim duzeltme, konum (kesinlik kapi > bina > sokak > mahalle > ilce > il), 0-100 puan, belirsizlikte aday listesi. Puan 85+ otomatik kabul, altinda kullaniciya onaylatin. Telefon numarasi ayiklanir. Olcum: gercek veriden 2.700 dagınık adreste kapiya kadar %99,5 dogru, 85+ puanda yanlis 0 |
| Toplu getir | `POST /v1/adres/toplu` `{ogeler: [{tur, id}]}` | En fazla 500 oge tek istekte: ad, adres, zincir kimlikleri (`ust`: mahalle_id, ilce_id, il_id), kaynak anahtari. Kayitli adreslerin adlari ve secim tutarliligi icin |
| Kaynak anahtari | `POST /v1/adres/kaynak` `{anahtarlar: [...]}` | OSM kimliginden (`osm:node:..`, `osm:way:..`, `osm:relation:..`) HARITA kaydi; tum kayitlar `kaynak` alanini tasir |
| En yakin kapi | `GET /v1/adres/sokak/{id}/en-yakin-kapi?lat&lon` | Pin icin kapi numarasi onerisi (secilen sokakta) |
| Ilceye bagli yollar | `GET /v1/adres/alt?ust=ilce:{id}&cocuk=sokak` | Hicbir mahalle / koy sinirina dusmeyen yollar (koy yollari, cevre yollari) |
| Yol bilgisi | `GET /v1/yol/nokta?lat&lon[&yon&profil]` | Yol sinifi, hiz siniri, tahmini hiz, serit, trafik isigi / dur levhasi (kavsakta) ve kavsaga kalan mesafe, tunel, kopru, gise, il / ilce. Surus analizi (ani durma vb.) icin, Overpass gerekmez |
| Baglanti cozme | `GET /v1/baglanti/coz?adres=` | Google / Yandex / Apple / Waze / OSM baglantisindaki noktalar (maps.app.goo.gl kisa baglantilari dahil) |
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
| Arama (GeoJSON) | `GET /v1/arama`, `/v1/ters-arama` | Photon bicimli GeoJSON; kendi adres indeksimizden |
| Yol uyarilari | `POST /v1/yol/uyarilar` `{polyline \| noktalar, tampon_m?, turler?}`, `GET /v1/yol/uyarilar?kutu=bati,guney,dogu,kuzey` | Rota boyunca hiz kamerasi ve hiz kesici (OSM), `rota_m` ile sirali; navigasyon 300-700 m once sesli uyarir. OSM'de Turkiye kamera kapsami sinirlidir |
| Rota boyunca hava | `POST /v1/yol/hava` `{polyline \| noktalar, sure_sn?, kalkis?}` | En fazla 25 ornek noktada varis saatindeki sicaklik, yagis, ruzgar, gorus; uyarilar firtina, kar, buzlanma, kuvvetli_yagis, kuvvetli_ruzgar, sis. Kaynak Open-Meteo (ucretsiz sunucu ticari olmayan kullanim icindir; ticari kullanimda `HAVA_ADRESI` + `HAVA_ANAHTARI`) |
| Cok kuryeli planlama | `POST /v1/planla` `{araclar, gorevler, gonderiler, profil, geometri}` | VROOM: hangi kurye hangi isi hangi sirayla; kapasite, beceri, zaman araligi, oncelik, alim-teslim cifti; en fazla 300 farkli konum (matris Valhalla'dan 50x50 bloklarla). Atanamayanlar `atanamayan` listesinde |
| En yakin kurye | `POST /v1/en-yakin` `{hedef, adaylar: [{id, konum}], profil, adet}` | Gercek yol suresine gore siralama (kus ucusu degil), en fazla 50 aday |
| Trafik profili | `POST /v1/trafik/iz` `{profil, noktalar: [{lat, lon, zaman}]}`, `POST /v1/trafik/sure` `{polyline \| noktalar, profil, zaman?}` | Projelerin GPS izlerinden yol + haftanin saati basina ortalama hiz (kimlik / iz saklanmaz) ve son 20 dk canli hiz; sure tahmini `tahmini_sure_sn` ve `kapsama` (verisi olan yol orani) doner. Veri biriktikce iyilesir |
| Ortak kapi havuzu | `POST /v1/adres/kapi-ogren` `{sokak_id, kapi_no, lat, lon, dogruluk_m?}`, `DELETE /v1/adres/kapi-ogren/{id}`, `GET /v1/adres/sokak/{id}/ogrenilen-kapilar` | OSM'de olmayan kapi numarasini teslimat konumundan ogrenir; konum gozlemlerin geometrik ortancasi, 2 gozlemde guvenilir. Ayristirma (`kaynak: havuz`, tek gozlemde puan en fazla 84) ve en yakin kapi kullanir |
| Paylasim kodu | `POST /v1/paylasim` `{duraklar, profil, ad?, sure_saat?}`, `GET` / `DELETE /v1/paylasim/{kod}` | 8 karakterlik kod (en fazla 30 gun); navigasyon `navigasyon.html?kod=<kod>` ile acar. Duraklar `ara` (GPX izi) noktalarini da tasir |
| GPX | `POST /v1/gpx/olustur` (GPX 1.1 dosyasi), `POST /v1/gpx/oku?iz_takip=true` (govde GPX metni, en fazla 5 MB) | Duraklar wpt + rte, cizgi trk; okumada `iz_takip` ile izden ara noktalar (rota izin yollarini izler). Google / Yandex GPX almaz: navigasyondaki "Google'da ac" / "Yandex'te ac" baglantilari kullanilir |
| Canli konum | WebSocket `/v1/canli/ws` (ilk mesaj `{tip: giris, anahtar, kanal, dinle}`), `POST /v1/canli/{kanal}/konum`, `GET /v1/canli/{kanal}/konumlar`, `GET` / `PUT /v1/canli/{kanal}/bolgeler` | Proje + kanal basina konum yayini ve bolge (daire / poligon) giris-cikis olaylari; kalp atisi 10 sn, 35 sn sessizlikte kapanir, istemci kendiliginden yeniden baglanir (`CanliBaglanti`). Saniyede en fazla 5 konum / baglanti |
| Cevrimdisi paketler | `GET /v1/cevrimdisi/paketler`, dosyalar `{karo}/paket/<il>.pmtiles`, `{karo}/paket/varlik.tar.gz` | 81 il icin PMTiles (z14), yazi tipi + simge arsivi; mobil uygulama indirip MapLibre'de `pmtiles://` ile yerelden acar |
| Yonetim | `/yonetim/*` | Proje, anahtar, izin, kaynak, kullanim |

## SIPARIS / Lezzet Sepeti

Hazir: `siparis-sunucu` ve `siparis-web` kayitlari (alan adlari: `isletme`, `musteri`, kok ve `www.lezzetsepeti.net`,
`siparis-isletme`, `siparis-musteri`, `siparis-admin` sslip adresleri, mobil kabuklar). Degerler `baglantilar/siparis.env`.

- **Rota (backend):** `OSRM_ADRESI` degiskeni (`https://HARITA-API/k/hk_.../osrm`). `yol_agi.py` degismez.
- **Harita (frontend):** Leaflet kalir; MapTiler karosu yerine `protomaps-leaflet@5.1.0` ile HARITA karosu:
  `leafletLayer({ url: '{karo}/tiles/turkiye/{z}/{x}/{y}.mvt', flavor: 'light', lang: 'tr' })`. Uydu / hibrit MapTiler'da kalir (ucretsiz kaynak yok).
- **Adres secimi (acilir listeler):** Ilce `GET /v1/yerlesim/ara?q=&tur=ilce` (il `ust_id`), mahalle / koy `GET /v1/yerlesim/{ilce}/alt?tur=mahalle_koy`,
  cadde / sokak `GET /v1/adres/mahalle/{mahalle}/sokaklar`, kapi `GET /v1/adres/sokak/{sokak}/kapilar`.
- **Pin -> adres:** `GET /v1/adres/nokta`. **Metin -> pin:** `GET /v1/adres/ara`.
- **Haritadaki renkli yer noktalari:** `GET /v1/adres/yerler` (z14+).
- **SIPARIS'te kalanlar:** teslimat bolgeleri, musteri adresleri, musteriden ogrenilen kapi numaralari (is mantigi).
- **Mevcut adreslerin eslenmesi (gecis):** Her HARITA kaydi `kaynak` alanini tasir.
  - Kapi numarasi, yer isareti, il / ilce / mahalle: SIPARIS ile ayni OSM bicimi (`osm:node:123`, `osm:way:456`, `osm:relation:789`);
    `POST /v1/adres/kaynak` ile toplu eslenir.
  - Sokak: HARITA ayni mahalledeki ayni adli parcalari tek sokakta birlestirir (`sokak:<mahalle_id>:<ad>`, mahallesizse
    `sokak:i<ilce_id>:<ad>`), bu yuzden SIPARIS'in yol kayitlari kimlikle degil ad + konumla eslenir:
    `GET /v1/adres/ara?q=<yol adi>&tur=sokak&lat=<yolun merkezi>&lon=...&yaricap_m=500` ilk sonucu.
  - Eslenen kimlikler bir kez SIPARIS tablosuna yazilir; sonraki gosterim ve dogrulama `POST /v1/adres/toplu` ile tek istekte yapilir.
- **Acilir listelerde mahalle disi yollar:** SIPARIS'in "dahil_ilce" karsiligi `GET /v1/adres/alt?ust=ilce:{id}&cocuk=sokak`.
- **Kurye yonlendirmesi:** Yandex / Google / Waze baglantilarina ek olarak HARITA navigasyonu: `navigasyon_baglantisi(duraklar, adlar)`
  (cok duraklı, sesli Turkce).
- **Kurye atama:** tek siparis icin `en_yakin()` (gercek yol suresi), toplu dagitim icin `planla()` (VROOM; restorandan al -> musteriye
  birak ciftleri `gonderiler`). Kurye konumlari `CanliBaglanti` (WebSocket) ya da `canli_konum()` ile; teslimat bolgesine giris /
  cikis olaylari `canli_bolgeler()` ile tanimlanir.
- **Kapi numarasi ogrenme:** teslim edildi aninda `kapi_ogren(sokak_id, kapi_no, lat, lon)`; ortak havuz tum projelere yarar.
- **Trafik:** kurye izleri `trafik_izi()` ile gonderilirse varis suresi `trafik_suresi()` ile ogrenilmis hizlardan hesaplanir.
- **Gecis:** Adim adim, her adim ayri dagitimla; once rota, sonra karo, sonra adres. Eski uclar o zamana kadar calismaya devam eder.

## MotoConvoy

Hazir: `motoconvoy-sunucu` ve `motoconvoy-web` kayitlari (alan adlari: `motoconvoy.net`, `www`, `app`,
`motokonus.89.45.45.152.sslip.io`, mobil kabuklar). Degerler `baglantilar/motoconvoy.env`. Backend `requests` kullaniyor;
Python istemcisi icin `httpx==0.28.1` requirements.txt'e eklenir.

- **Navigasyon:** `deneme/navigasyon.html` sesli Turkce adim adim navigasyonun calisan ornegidir (Valhalla `route`, `tr-TR`).
- **Harita:** `tile.openstreetmap.org` yerine HARITA karosu (MapLibre onerilir: `istemci/harita-istemci.js`; Leaflet ise `protomaps-leaflet`).
- **Rota ve varis hedefi:** `POST /v1/rota` (`"profil": "motosiklet"`), hedef arama `GET /v1/adres/ara`. OpenRouteService gunluk 2.000 istek siniri kalkar.
- **Kalan mesafe:** Telefon rotayi bir kez ister ve kendi hesaplar (plandaki mantik degismez); sunucu yalniz rota cizgisini verir.
- **Ek imkanlar:** `/valhalla/trace_attributes` (GPS izini yola oturtma), `/valhalla/isochrone` (erisim alani), `/valhalla/optimized_route` (durak sirasi), `/v1/adres/nokta` (hangi yol / mahalle).
- **Rota secenekleri:** `/valhalla/route` ile `costing_options.motorcycle`: `exclude_tolls` (gisesiz), `exclude_highways` (otoyolsuz),
  `exclude_unpaved` (topraksiz), `shortest` (en kisa), `use_highways` / `use_tolls` (0-1 tercih). 50 duraga kadar tur.
- **Grup ETA:** `/valhalla/sources_to_targets` (uyeler -> hedef).
- **Ani durma ortami:** `GET /v1/yol/nokta?lat&lon&yon` (yol sinifi, trafik isigi / dur levhasi ve kavsaga kalan mesafe, tunel, gise, il / ilce);
  OSM hiz siniri cogu yolda bostur (`hiz_siniri_kmh` null), `tahmini_hiz_kmh` yol sinifindan gelir.
- **Rota aktarma:** `GET /v1/baglanti/coz?adres=<Google Maps / Yandex baglantisi>` (kisa baglantilar dahil).
- **Tur paylasimi:** `gpx_oku(iz_takip=True)` ile disaridan gelen tur (Komoot, Garmin, OsmAnd), `paylasim_olustur()` ile kisa kod;
  katilimcilar `navigasyon.html?kod=` ile ayni rotayi acar, Google / Yandex kullananlara "Google'da ac" / "Yandex'te ac" baglantisi.
- **Yolculuk oncesi:** `yol_uyarilari()` (kamera, kasis) ve `rota_havasi()` (yol boyunca hava, buzlanma / ruzgar uyarisi).
- **Konvoy:** uye konumlari `CanliBaglanti` (kanal = konvoy kimligi); mola / bulusma noktasi bolge olarak tanimlanir, giris olayi gelir.
- **Cevrimdisi:** `cevrimdisi_paketler()` ile il paketleri; sinyal olmayan bolgelerde harita telefondan acilir.
- **Bilinen sinir:** Yukseklik (rakim) verisi kurulmadi; `/valhalla/height` bos doner (bkz. YAYIN.md).

## Yeni proje

1. `python scripts/proje-bagla.py <ad> --web https://<alan-adi> [--mobil]` (elle: `POST /yonetim/projeler`; varsayilan tum servisler acik,
   `servisler` ile daraltilir).
2. Alan adi `IZINLI_KOKEN_REGEX` kapsaminda degilse Coolify'da eklenir (karo icin).
3. Backend: `istemci/harita_istemci.py`; web: `istemci/harita-istemci.js` veya yukaridaki REST uclari.

## Sinirlar

Rota en fazla 50 nokta (duraklar + GPX ara noktalari), matris en fazla 50 x 50, planlama en fazla 300 konum, Valhalla govdesi en fazla 2 MB, adres aramasi en fazla 50 sonuc, toplu getirme 500 oge.
Veri OpenStreetMap'e dayanir; kapi numarasi ve ad kapsami bolgeye gore degisir. Atif: (c) OpenStreetMap katkicilari.
