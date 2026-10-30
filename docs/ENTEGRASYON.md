# Entegrasyon rehberi

Ortak: her istek `X-Harita-Anahtar: hk_...` basligi tasir. Tarayicidan kullanilan anahtarlar projede `kaynaklar` ile kendi
alan adiniza kisitlanir; sunucudan sunucuya (Origin basligi olmayan) cagrilar kisitlanmaz, bu yuzden sunucu anahtarini tarayiciya vermeyin.

## SIPARIS

Rota (backend): `backend/app/services/yol_agi.py` OSRM'in `/route/v1/driving/...` ucunu cagirir. Kod degismeden:

- Coolify'da `OSRM_ADRESI=https://HARITA-API/k/hk_.../osrm` yapilir (anahtar yolda; baslik gerekmez).
  Ayni Coolify aginda ise gateway'in ic adresi kullanilir (`http://<gateway-konteyner>:8000/k/hk_.../osrm`).
- Eski `siparis-rota` (OSRM) uygulamasi, yeni rota dogrulandiktan sonra durdurulur.

Harita (frontend): `packages/shared/src/config.js` icindeki MapTiler karo adresi yerine HARITA karolari kullanilir.
SIPARIS Leaflet kullandigi icin `protomaps-leaflet` ile:

```js
import { leafletLayer } from 'protomaps-leaflet'; // protomaps-leaflet@5.1.0
leafletLayer({ url: 'https://HARITA-KARO/tiles/turkiye/{z}/{x}/{y}.mvt', flavor: 'light', lang: 'tr' }).addTo(harita);
```

Onemli yer / adres verisi SIPARIS'in kendi PostGIS tablolarinda kalir (is mantigina bagli); yalnizca karo ve rota ortaklasir.

## MotoConvoy

`frontend/js/harita.js` dogrudan `tile.openstreetmap.org` kullaniyor (uretim icin uygun degil). Leaflet kalacaksa yukaridaki
`protomaps-leaflet` satiri `L.tileLayer(...)` yerine gecer. Varis hedefi rota hesabi icin OpenRouteService yerine
`POST /v1/rota` (`"profil": "motosiklet"`) kullanilir; gunluk 2.000 istek siniri kalkar. Hedef arama kutusu `GET /v1/arama`.

## Yeni proje

1. `POST /yonetim/projeler` ile proje + anahtar.
2. Web: `istemci/harita-istemci.js` (`haritaOlustur`, `rotaIste`, `ara`). Baska dil / platform: dogrudan REST ucu.
3. Mobil / sunucu: anahtar sunucuda saklanir, istekler sunucudan atilir.

## Sinirlar

Rota en fazla 20 nokta, matris en fazla 50x50. Kota proje basina dakika limitidir (`dakika_limiti`), asilinca `429` ve `Retry-After`.
