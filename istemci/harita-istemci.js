/**
 * HARITA istemcisi: herhangi bir web projesinin harita servisini tek dosyayla kullanmasini saglar.
 *
 * Kullanim (derleyicisiz, tarayicida dogrudan):
 *   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.css">
 *   <script type="module">
 *     import { haritaOlustur, rotaIste, ara } from './harita-istemci.js';
 *     const harita = await haritaOlustur({ kap: 'harita', apiAdresi: 'https://harita-api.ornek.com', anahtar: 'hk_...' });
 *   </script>
 *
 * Not: anahtar tarayicida gorunur. Tarayici anahtarlarini projede yalniz kendi alan adiniza kisitlayin
 * (yonetim: PATCH /yonetim/projeler/{id} kaynaklar); sunucu tarafi anahtarlari ayri tutun.
 */
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/+esm';
import { layers, namedFlavor } from 'https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/+esm';

const BASLIK = 'X-Harita-Anahtar';

async function istek(apiAdresi, anahtar, yol, secenekler = {}) {
  const yanit = await fetch(`${apiAdresi.replace(/\/$/, '')}${yol}`, {
    ...secenekler,
    headers: { [BASLIK]: anahtar, 'Content-Type': 'application/json', ...(secenekler.headers || {}) },
  });
  if (!yanit.ok) {
    const hata = new Error(`Harita servisi hatasi (${yanit.status})`);
    hata.durum = yanit.status;
    throw hata;
  }
  return yanit.json();
}

/** Servisten karo / yazi tipi / simge adreslerini alir. */
export function yapilandirmaAl(apiAdresi, anahtar) {
  return istek(apiAdresi, anahtar, '/v1/yapilandirma');
}

/**
 * MapLibre haritasi olusturur.
 * @param {{kap: string|HTMLElement, apiAdresi: string, anahtar: string, tema?: string, merkez?: [number, number], yakinlik?: number, dil?: string}} secenek
 * tema: light | dark | white | grayscale | black (Protomaps temalari)
 */
export async function haritaOlustur({ kap, apiAdresi, anahtar, tema = 'light', merkez, yakinlik = 6, dil = 'tr' }) {
  const yap = await yapilandirmaAl(apiAdresi, anahtar);
  const stil = {
    version: 8,
    glyphs: yap.yaziTipleri,
    sprite: `${yap.simgeler}/${tema}`,
    sources: {
      harita: { type: 'vector', tiles: [yap.karo.adres], maxzoom: yap.karo.maksYakinlastirma, attribution: yap.atif },
    },
    layers: layers('harita', namedFlavor(tema), { lang: dil }),
  };
  return new maplibregl.Map({
    container: kap,
    style: stil,
    center: merkez || yap.merkez,
    zoom: yakinlik,
    maxBounds: [[yap.sinirlar[0] - 3, yap.sinirlar[1] - 3], [yap.sinirlar[2] + 3, yap.sinirlar[3] + 3]],
  });
}

/**
 * Noktalar arasi rota. noktalar: [{lat, lon}, ...]; profil: auto | motosiklet | bisiklet | yaya.
 * Donus: {sure_sn, mesafe_m, geometri(GeoJSON LineString)}
 */
export function rotaIste(apiAdresi, anahtar, noktalar, profil = 'auto', geometri = true) {
  return istek(apiAdresi, anahtar, '/v1/rota', { method: 'POST', body: JSON.stringify({ noktalar, profil, geometri }) });
}

/** Sure / mesafe matrisi. Donus: {sure_sn: [[...]], mesafe_m: [[...]]} */
export function matrisIste(apiAdresi, anahtar, kaynaklar, hedefler, profil = 'auto') {
  return istek(apiAdresi, anahtar, '/v1/matris', { method: 'POST', body: JSON.stringify({ kaynaklar, hedefler, profil }) });
}

/** Adres / yer arama (GeoJSON). Konum verilirse o civar one cikar. */
export function ara(apiAdresi, anahtar, metin, { lat, lon, limit = 7, dil = 'tr' } = {}) {
  const p = new URLSearchParams({ q: metin, limit: String(limit), dil });
  if (lat !== undefined && lon !== undefined) {
    p.set('lat', String(lat));
    p.set('lon', String(lon));
  }
  return istek(apiAdresi, anahtar, `/v1/arama?${p}`);
}

/** Koordinattan adres (GeoJSON). */
export function tersAra(apiAdresi, anahtar, lat, lon, dil = 'tr') {
  return istek(apiAdresi, anahtar, `/v1/ters-arama?lat=${lat}&lon=${lon}&dil=${dil}`);
}

/** Rota cizgisini haritaya ekler (varsa gunceller). */
export function rotaCiz(harita, geometri, renk = '#1d6fe8') {
  const veri = { type: 'Feature', geometry: geometri, properties: {} };
  if (harita.getSource('rota')) {
    harita.getSource('rota').setData(veri);
    return;
  }
  harita.addSource('rota', { type: 'geojson', data: veri });
  harita.addLayer({
    id: 'rota',
    type: 'line',
    source: 'rota',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': renk, 'line-width': 5 },
  });
}
