/**
 * HARITA istemcisi: herhangi bir web projesinin harita servisini tek dosyayla kullanmasini saglar.
 *
 * Kullanim (derleyicisiz, tarayicida dogrudan):
 *   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.css">
 *   <script type="module">
 *     import { HaritaIstemcisi } from './harita-istemci.js';
 *     const h = new HaritaIstemcisi('https://harita-api.89.45.45.152.sslip.io', 'hk_...');   // web anahtari
 *     const harita = await h.harita({ kap: 'harita', tema: 'light' });
 *     const rota = await h.rota([{ lat: 40.99, lon: 29.02 }, { lat: 40.98, lon: 29.03 }], 'motosiklet');
 *   </script>
 * Tek tek fonksiyonlar da disa aciktir (haritaOlustur, rotaIste, ara, adresAra, adresNokta, valhalla ...).
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

/** Bos (undefined / null) degerleri atarak sorgu metni uretir. */
function sorgu(parametreler) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(parametreler)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  return p.toString();
}

/**
 * Kapi no, sokak, bina, yer, yerlesim aramasi. tur: kapi | sokak | bina | yer | yerlesim.
 * lat / lon verilirse esit eslesmelerde yakin olan one gelir; yaricapM (lat / lon gerekir) bu yaricap disini eler.
 */
export function adresAra(apiAdresi, anahtar, metin, { tur, ustId, lat, lon, limit = 10, yaricapM } = {}) {
  return istek(apiAdresi, anahtar, `/v1/adres/ara?${sorgu({ q: metin, tur, ust_id: ustId, lat, lon, limit, yaricap_m: yaricapM })}`);
}

/**
 * Serbest yazilmis adresi ayristirir ve dogrular (parcalar, duzgun adres, konum, 0-100 puan, oneriler).
 * metin: tek metin ya da metin dizisi (en fazla 100). Puan 85 ve ustu otomatik kabul edilebilir; altinda kullaniciya onaylatin.
 * baglam: {lat, lon} isletme / kullanici konumu ya da {ilceId}.
 */
export function adresAyristir(apiAdresi, anahtar, metin, { lat, lon, ilceId } = {}) {
  const govde = Array.isArray(metin) ? { metinler: metin } : { metin };
  if (lat !== undefined && lon !== undefined) Object.assign(govde, { lat, lon });
  if (ilceId) govde.ilce_id = ilceId;
  return istek(apiAdresi, anahtar, '/v1/adres/ayristir', { method: 'POST', body: JSON.stringify(govde) });
}

/** (tur, id) ogeleri tek istekte: [{tur, id}, ...] (en fazla 500). Ad, adres, zincir kimlikleri (ust) ve kaynak anahtari doner. */
export function toplu(apiAdresi, anahtar, ogeler) {
  return istek(apiAdresi, anahtar, '/v1/adres/toplu', { method: 'POST', body: JSON.stringify({ ogeler }) });
}

/** OSM kaynak anahtarindan (osm:node:.. / osm:way:.. / osm:relation:..) HARITA kayitlari (en fazla 500). */
export function kaynaktan(apiAdresi, anahtar, anahtarlar) {
  return istek(apiAdresi, anahtar, '/v1/adres/kaynak', { method: 'POST', body: JSON.stringify({ anahtarlar }) });
}

/** Secilen sokaktaki en yakin kapi numarasi (pin icin oneri); yoksa null. */
export async function enYakinKapi(apiAdresi, anahtar, sokakId, lat, lon, yaricapM = 100) {
  try {
    return await istek(apiAdresi, anahtar, `/v1/adres/sokak/${sokakId}/en-yakin-kapi?${sorgu({ lat, lon, yaricap_m: yaricapM })}`);
  } catch (hata) {
    if (hata.durum === 404) return null;
    throw hata;
  }
}

/** Konumdaki yolun ozellikleri (sinif, hiz siniri, trafik isigi, dur levhasi, tunel, kopru, gise) ve il / ilce. */
export function yolBilgisi(apiAdresi, anahtar, lat, lon, { profil = 'auto', yon } = {}) {
  return istek(apiAdresi, anahtar, `/v1/yol/nokta?${sorgu({ lat, lon, profil, yon })}`);
}

/** Google / Yandex / Apple / Waze / OSM harita baglantisindaki noktalar [{lat, lon}] (kisa baglantilar dahil). */
export async function baglantiCoz(apiAdresi, anahtar, adres) {
  return (await istek(apiAdresi, anahtar, `/v1/baglanti/coz?${sorgu({ adres })}`)).noktalar;
}

/**
 * HARITA navigasyon ekranini duraklarla acan baglanti (Yandex / Google yonlendirmesi yerine).
 * duraklar: [{lat, lon}], adlar: ['Market', 'Musteri'], profil: araba | motosiklet | yaya.
 */
export function navigasyonBaglantisi(duraklar, { adlar, profil = 'araba', sayfa = 'https://harita-deneme.89.45.45.152.sslip.io/navigasyon.html' } = {}) {
  const p = new URLSearchParams({ duraklar: duraklar.map((d) => `${d.lat.toFixed(6)},${d.lon.toFixed(6)}`).join(';'), profil });
  if (adlar?.length) p.set('adlar', adlar.map((a) => String(a).replace(/\|/g, ' ')).join('|'));
  return `${sayfa}?${p}`;
}

/** Pin -> adres: adres metni, il / ilce / mahalle, en yakin sokak, kapi ve yerler. */
export function adresNokta(apiAdresi, anahtar, lat, lon, yaricapM = 150) {
  return istek(apiAdresi, anahtar, `/v1/adres/nokta?${sorgu({ lat, lon, yaricap_m: yaricapM })}`);
}

/** Acilir liste agaci: ust 'il:34', 'ilce:123', 'mahalle_koy:456', 'sokak:789'; cocuk: sokak | bina | kapi. */
export function adresAlt(apiAdresi, anahtar, ust, { cocuk, limit = 200, atla = 0 } = {}) {
  return istek(apiAdresi, anahtar, `/v1/adres/alt?${sorgu({ ust, cocuk, limit, atla })}`);
}

/** Il, ilce, mahalle_koy, sehir, kasaba, koy, mezra, semt aramasi. */
export function yerlesimAra(apiAdresi, anahtar, metin, { tur, ustId, limit = 10 } = {}) {
  return istek(apiAdresi, anahtar, `/v1/yerlesim/ara?${sorgu({ q: metin, tur, ust_id: ustId, limit })}`);
}

/** En yakin yerler (or. tur: 'akaryakit', 'eczane', 'otel'). */
export function yakinYerler(apiAdresi, anahtar, lat, lon, { tur, yaricapM = 5000, limit = 20 } = {}) {
  return istek(apiAdresi, anahtar, `/v1/adres/yakin?${sorgu({ lat, lon, tur, yaricap_m: yaricapM, limit })}`);
}

/** Ogenin sekli: {tur, id, ad, geometri (GeoJSON)}; il / ilce / mahalle siniri, sokak cizgisi, bina poligonu. */
export function sekil(apiAdresi, anahtar, tur, id) {
  return istek(apiAdresi, anahtar, `/v1/adres/sekil?${sorgu({ tur, id })}`);
}

/**
 * Valhalla'nin tam API'si: route, optimized_route, sources_to_targets, isochrone, trace_route,
 * trace_attributes, locate, expansion, centroid, height. Govde Valhalla bicimindedir.
 */
export function valhalla(apiAdresi, anahtar, uc, govde) {
  return istek(apiAdresi, anahtar, `/valhalla/${uc}`, { method: 'POST', body: JSON.stringify(govde) });
}

/** Turkce adim adim talimatli rota (navigasyon icin). noktalar: [{lat, lon}, ...]; costing: auto | motorcycle | bicycle | pedestrian. */
export function adimAdimRota(apiAdresi, anahtar, noktalar, costing = 'auto') {
  return valhalla(apiAdresi, anahtar, 'route', {
    locations: noktalar, costing, directions_options: { language: 'tr-TR', units: 'kilometers' },
  });
}

/**
 * Ayni adres ve anahtari tekrar yazmadan kullanmak icin sarmalayici:
 *   const h = new HaritaIstemcisi('https://harita-api...', 'hk_...');
 *   const harita = await h.harita({ kap: 'harita' }); const r = await h.rota([{lat, lon}, {lat, lon}]);
 */
export class HaritaIstemcisi {
  constructor(apiAdresi, anahtar) {
    this.apiAdresi = apiAdresi;
    this.anahtar = anahtar;
  }

  harita(secenek = {}) { return haritaOlustur({ ...secenek, apiAdresi: this.apiAdresi, anahtar: this.anahtar }); }
  yapilandirma() { return yapilandirmaAl(this.apiAdresi, this.anahtar); }
  rota(noktalar, profil, geometri) { return rotaIste(this.apiAdresi, this.anahtar, noktalar, profil, geometri); }
  matris(kaynaklar, hedefler, profil) { return matrisIste(this.apiAdresi, this.anahtar, kaynaklar, hedefler, profil); }
  ara(metin, secenek) { return ara(this.apiAdresi, this.anahtar, metin, secenek); }
  tersAra(lat, lon) { return tersAra(this.apiAdresi, this.anahtar, lat, lon); }
  adresAra(metin, secenek) { return adresAra(this.apiAdresi, this.anahtar, metin, secenek); }
  adresNokta(lat, lon, yaricapM) { return adresNokta(this.apiAdresi, this.anahtar, lat, lon, yaricapM); }
  adresAlt(ust, secenek) { return adresAlt(this.apiAdresi, this.anahtar, ust, secenek); }
  yerlesimAra(metin, secenek) { return yerlesimAra(this.apiAdresi, this.anahtar, metin, secenek); }
  yakinYerler(lat, lon, secenek) { return yakinYerler(this.apiAdresi, this.anahtar, lat, lon, secenek); }
  sekil(tur, id) { return sekil(this.apiAdresi, this.anahtar, tur, id); }
  valhalla(uc, govde) { return valhalla(this.apiAdresi, this.anahtar, uc, govde); }
  adimAdimRota(noktalar, costing) { return adimAdimRota(this.apiAdresi, this.anahtar, noktalar, costing); }
  adresAyristir(metin, baglam) { return adresAyristir(this.apiAdresi, this.anahtar, metin, baglam); }
  toplu(ogeler) { return toplu(this.apiAdresi, this.anahtar, ogeler); }
  kaynaktan(anahtarlar) { return kaynaktan(this.apiAdresi, this.anahtar, anahtarlar); }
  enYakinKapi(sokakId, lat, lon, yaricapM) { return enYakinKapi(this.apiAdresi, this.anahtar, sokakId, lat, lon, yaricapM); }
  yolBilgisi(lat, lon, secenek) { return yolBilgisi(this.apiAdresi, this.anahtar, lat, lon, secenek); }
  baglantiCoz(adres) { return baglantiCoz(this.apiAdresi, this.anahtar, adres); }
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
