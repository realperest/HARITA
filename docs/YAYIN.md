# Coolify yayini

## Kaynaklar

1. Coolify: Yeni kaynak -> Public/Private Repository -> `realperest/HARITA` -> Build Pack: **Docker Compose**, dosya `docker-compose.yml`.
2. Ortam degiskenleri (`.env.example` ornek): `DB_SIFRE`, `YONETIM_ANAHTARI` (uzun rastgele), `KARO_GENEL_ADRESI`, `IZINLI_KOKEN_REGEX`.
3. Alan adlari: `tiles` servisine karo alan adi (port 8080), `gateway` servisine API alan adi (port 8000).
   Diger servisler alan adi almaz.
4. Cloudflare: karo alan adini turuncu bulutla onbellege alin (karolar `Cache-Control: public` doner, yuk Cloudflare'de kalir).
   SIPARIS ile ayni sunucudaysa disk (~25 GB) ve RAM (rota ~3-4 GB, arama 2-3 GB) payini once kontrol edin.

## Ilk acilis (siralama)

| Servis | Ne olur | Sure |
|---|---|---|
| tiles | Protomaps gunluk yapisindan Turkiye kesiti indirilir | dakikalar - bir saat, birkac GB |
| rota | Geofabrik Turkiye verisinden Valhalla cizgesi uretilir | ~20-60 dk, uretim sirasinda yuksek RAM |
| arama | Gezegen dokumunden TR indeksi uretilir | saatler (bir kereye mahsus) |

Hazirlik: `GET https://HARITA-API/saglik/hazir` hepsi `true` olunca 200 doner. Her servis kalici hacim kullanir; yeniden dagitimda veri silinmez.

## Veri guncelleme

Aylik: `harita_karo` hacmindeki `turkiye.pmtiles` dosyasini silip tiles servisini yeniden baslatin (yeni kesit iner); rota icin
`force_rebuild=True` ile tek seferlik yeniden baslatma; arama icin `/veri/.hazir` dosyasini silip yeniden baslatma.
Bunu ileride zamanlanmis isle otomatiklestirmek ayri bir gelistirmedir.

## Ilk proje

```bash
curl -X POST https://HARITA-API/yonetim/projeler -H "X-Yonetim-Anahtari: $YONETIM" -H "Content-Type: application/json" \
  -d '{"ad":"siparis","kaynaklar":["https://musteri.lezzetsepeti.net","https://isletme.lezzetsepeti.net"]}'
```
