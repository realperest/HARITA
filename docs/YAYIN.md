# Coolify yayini

## Kaynaklar

1. Coolify: Yeni kaynak -> Public/Private Repository -> `realperest/HARITA` -> Build Pack: **Docker Compose**, dosya `docker-compose.yaml`.
2. Ortam degiskenleri (`.env.example` ornek): `DB_SIFRE`, `REDIS_SIFRE`, `DB_ADRESI`, `REDIS_ADRESI`, `YONETIM_ANAHTARI`
   (uzun rastgele), `KARO_GENEL_ADRESI`, `IZINLI_KOKEN_REGEX`.
3. Veritabani ve Redis ayri Coolify kaynaklaridir (`harita-db` PostGIS 17, `harita-redis` Redis 7); compose uygulamasi
   Coolify ortak agina baglanir ("Predefined network").
4. Alan adlari: `tiles` servisine karo alan adi (port 8080), `gateway` servisine API alan adi (port 8000).
   Diger servisler alan adi almaz.
5. Cloudflare: karo alan adini turuncu bulutla onbellege alin (karolar `Cache-Control: public` doner, yuk Cloudflare'de kalir).
   Ayni sunucudaki diger projeler icin disk ve RAM payini kontrol edin (rota en fazla 6 GB, veri 2 GB, karo 1 GB, gateway 512 MB).
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

## Veri guncelleme

Aylik: `harita_karo` hacmindeki `turkiye.pmtiles` dosyasini silip tiles servisini yeniden baslatin (yeni kesit iner); rota icin
`force_rebuild=True` ile tek seferlik yeniden baslatma. Adres / yerlesim verisini `veri` servisi `GUNCELLEME_GUN` (30) gunde bir
kendisi tazeler. Karo ve rota tazelemesini zamanlanmis isle otomatiklestirmek ayri bir gelistirmedir.

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
