# Coolify yayini

## Kaynaklar

1. Coolify: Yeni kaynak -> Public/Private Repository -> `realperest/HARITA` -> Build Pack: **Docker Compose**, dosya `docker-compose.yaml`.
2. Ortam degiskenleri (`.env.example` ornek): `DB_SIFRE`, `REDIS_SIFRE`, `DB_ADRESI`, `REDIS_ADRESI`, `YONETIM_ANAHTARI`
   (uzun rastgele), `KARO_GENEL_ADRESI`, `IZINLI_KOKEN_REGEX`. Istege bagli: `HAVA_ADRESI` / `HAVA_ANAHTARI` (ticari Open-Meteo),
   `CEVRIMDISI_PAKET` (varsayilan True; il paketleri ~1-2 GB ek disk), `PAKET_MAKS_YAKINLASTIRMA` (varsayilan 14).
3. Veritabani ve Redis ayri Coolify kaynaklaridir (`harita-db` PostGIS 17, `harita-redis` Redis 7); compose uygulamasi
   Coolify ortak agina baglanir ("Predefined network").
4. Alan adlari: `tiles` servisine karo alan adi (port 8080), `gateway` servisine API alan adi (port 8000).
   Diger servisler alan adi almaz.
5. Cloudflare: karo alan adini turuncu bulutla onbellege alin (karolar `Cache-Control: public` doner, yuk Cloudflare'de kalir).
   Ayni sunucudaki diger projeler icin disk ve RAM payini kontrol edin (rota en fazla 6 GB, veri 2 GB, karo 1 GB, gateway 512 MB,
   plan 512 MB).
6. Deneme sayfasi ayri Coolify uygulamasidir (`harita-deneme`, Dockerfile `deneme/`): `MAPTILER_ANAHTAR` ve `HARITA_ANAHTAR`
   (kisitli demo anahtari) ortam degiskenleri.

Gonderim (push) dagitimi kendiliginden baslatmaz: degisiklikten sonra Coolify'da ilgili kaynak yeniden dagitilir
(`coolify deploy uuid <uuid>`; harita `cnsevlzx5utkbmcwhhsmadop`, harita-deneme `rdq3cvvcycbow0ckjl1xxnud`).

## Ilk acilis (siralama)

| Servis | Ne olur | Sure |
|---|---|---|
| tiles | Protomaps gunluk yapisindan Turkiye kesiti indirilir | dakikalar - bir saat, birkac GB |
| rota | Geofabrik Turkiye verisinden Valhalla cizgesi uretilir | ~20-60 dk, uretim sirasinda yuksek RAM |
| veri | Turkiye PBF'inden il / ilce / mahalle sinirlari, sokaklar, kapi numaralari, yerler ve binalar PostGIS'e yuklenir | ~1 saat |

Hazirlik: `GET https://HARITA-API/saglik/hazir` hepsi (`veritabani`, `redis`, `rota`, `adres`) `true` olunca 200 doner.
Her servis kalici hacim kullanir; yeniden dagitimda veri silinmez. Yayindan sonra: `python scripts/canli-test.py`.

## Veri guncelleme (otomatik, aylik)

Her ayin 1'i 05:00 Turkiye saatinde (02:00 UTC) uc servis kendi verisini yeniler; yenileme sirasinda canli veri degismez, yeni veri
once yan tarafta hazirlanir ve dogrulanir, gecerse degistirilir. Insan onayi gerekmez. Kapatmak icin `AYLIK_YENILEME=False`.
Servis o anda kapaliysa acilista telafi eder; basarisiz olursa 3 saat arayla en cok 4 kez dener, canli veri bozulmaz.

| Servis | Ne yapar | Dogrulama | Yedek (bir sonraki yenilemeye kadar durur) |
|---|---|---|---|
| `tiles` | En yeni Protomaps yapisindan Turkiye kesitini `turkiye.pmtiles.yeni` olarak indirir, degistirir, il paketlerini yeniden uretir | Boyut oraninin %80-%250 olmasi, `pmtiles verify`, ornek karolarin (Istanbul, Ankara z10) okunmasi; degisimden sonra acilis kontrolu, sorunda otomatik geri alma | `turkiye.pmtiles.yedek`, `paket.yedek/` (`harita_karo` hacminde) |
| `rota` | Yeni Geofabrik PBF'ini indirir, `custom_files/yeni_kurulum` altinda yeni Valhalla grafini kurar, degistirir, yalniz Valhalla'yi yeniden baslatir | PBF boyutu / bicimi, gecici servis (port 8012) ile ornek rotalar (Istanbul-Ankara auto / motosiklet, kisa yaya) uzunluk araligi ve canli servisle %10 karsilastirma; degisimden sonra canli servisle tekrar, sorunda otomatik geri alma | `valhalla_tiles.yedek`, `valhalla_tiles.tar.yedek`, `admins.sqlite.yedek`, `*.pbf.yedek` (`harita_rota2` hacminde) |
| `veri` | Yerlesim, adres (sokak / yer / kapi), bina ve yol uyarisi verisini PostGIS'e yukler | Yeni yukleme onceki aktif kayit sayisinin en az %90'ini uretmeli (`VERI_EN_AZ_ORAN`), degilse eski kayitlar pasiflestirilmez ve yukleme hata sayilir | Eski kayitlar `aktif_mi = FALSE` olarak veritabaninda kalir |

Ilk dagitimda bulunulan ay "yapildi" sayilir (damga dosyalari `.karo_son_ay`, `.rota_son_ay`); ilk otomatik yenileme bir sonraki ayin 1'idir.
Elle tetiklemek icin ilgili konteynerde `YENILEME_ZORLA=1 YENILEME_TEK_SEFER=1 /yenile.sh` (tiles) ya da `/rota-yenile.sh` (rota); veri icin
`ZORLA=1` ortam degiskeni. Yenileme gunlukleri konteyner loglarinda `[karo ...]` ve `[rota-yenile ...]` onekleriyle gorunur.
Rakim (yukseklik) acik kuruluysa (`ROTA_YUKSEKLIK=True`) yan graf da yukseklikle kurulur. Yedekler disk kaplar (karo + paketler + rota grafi);
bir sonraki yenileme onceki yedegi siler.

## Yukseklik (rakim) verisi

Kapali kuruludur (disk ve yeniden kurulum suresi icin). Gerekirse: Coolify'da `harita` uygulamasina `ROTA_YUKSEKLIK=True` ve
`ROTA_YENIDEN_KUR=True` eklenip yeniden dagitilir; rota servisi Turkiye icin yukseklik karolarini indirip cizgeyi yeniden kurar
(~1 saat, bu surede rota servisi yanit vermez, ek disk ~2-4 GB). Kurulum bitince `ROTA_YENIDEN_KUR=False` yapilip tekrar dagitilir
(aksi halde her yeniden baslatmada kurulum tekrarlanir). Sonra `/valhalla/height` ve rotalardaki egim bilgisi dolar.

## Projeleri baglamak

`python scripts/proje-bagla.py <ad>` (ayrinti: [ENTEGRASYON.md](ENTEGRASYON.md)).

## Veritabani yonetimi (Adminer)

Coolify'da `harita-adminer` uygulamasi (`adminer:5-standalone`): https://harita-adminer.89.45.45.152.sslip.io
Giris: sistem PostgreSQL, sunucu `mjvz7cconglhimakyiainj6q` (harita-db, ic ag; hazir dolu gelir), kullanici `harita`, veritabani `harita`,
sifre Coolify'da `harita` uygulamasinin `DB_SIFRE` degiskeni. Veritabani (`harita-db`) ve Redis (`harita-redis`) ayri Coolify kaynaklaridir;
`harita` compose uygulamasi Coolify ortak agina baglanir ("Predefined network" ayari).
