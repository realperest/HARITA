/**
 * HARITA deneme sayfasi: harita, metinle arama, pin, yerlesim, rota ve matris.
 * Iki harita motoru ayni arayuzle calisir (MapLibre ve Leaflet); ustteki "Motor" seciciyle degistirilir.
 * Anahtarlar tarayicida (localStorage) tutulur, koda ve depoya yazilmaz.
 */
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/+esm';
import { layers, namedFlavor } from 'https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/+esm';

const VARSAYILAN_API = 'https://harita-api.89.45.45.152.sslip.io';
const VARSAYILAN_KARO = 'https://harita-karo.89.45.45.152.sslip.io';
const DEPO_ANAHTARI = 'harita_deneme_v1';
const MT_ATIF = '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">&copy; MapTiler</a> '
  + '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap katkıcıları</a>';

const TUR_ETIKET = {
  il: 'İl', ilce: 'İlçe', mahalle_koy: 'Mahalle / Köy', sehir: 'Şehir merkezi', kasaba: 'Kasaba',
  koy: 'Köy merkezi', mezra: 'Mezra', semt: 'Semt', sokak: 'Sokak', kapi: 'Kapı no', yer: 'Yer',
};

/** Secilebilir katmanlar. tur: vektor (kendi karolarimiz), mt (MapTiler raster), karma (uydu + kendi yol ve etiketlerimiz) */
const KATMANLAR = [
  { kod: 'v-dark', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - koyu', tur: 'vektor', tema: 'dark' },
  { kod: 'v-light', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - açık', tur: 'vektor', tema: 'light' },
  { kod: 'v-white', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - beyaz', tur: 'vektor', tema: 'white' },
  { kod: 'v-grayscale', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - gri', tur: 'vektor', tema: 'grayscale' },
  { kod: 'v-black', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - siyah', tur: 'vektor', tema: 'black' },
  { kod: 'mt-hybrid', grup: 'MapTiler (SIPARIS ile aynı)', ad: 'Hibrit', tur: 'mt', harita: 'hybrid-v4', uzanti: 'jpg' },
  { kod: 'mt-satellite', grup: 'MapTiler (SIPARIS ile aynı)', ad: 'Uydu', tur: 'mt', harita: 'satellite', uzanti: 'jpg' },
  { kod: 'mt-streets', grup: 'MapTiler (SIPARIS ile aynı)', ad: 'Sokak', tur: 'mt', harita: 'streets-v2', uzanti: 'png' },
  { kod: 'mt-osm', grup: 'MapTiler (SIPARIS ile aynı)', ad: 'Ayrıntılı', tur: 'mt', harita: 'openstreetmap', uzanti: 'png' },
  { kod: 'karma', grup: 'Karma', ad: 'Uydu + kendi yol ve etiketlerimiz (yalnız MapLibre)', tur: 'karma', harita: 'satellite', uzanti: 'jpg' },
];

/** Her rota icin sirayla farkli renk. */
const ROTA_RENKLERI = ['#3FB950', '#58A6FF', '#D29922', '#F85149', '#BC8CFF', '#39C5CF', '#FF7B72', '#E3B341'];
const IZOKRON_RENKLERI = ['#3FB950', '#D29922', '#F85149', '#BC8CFF', '#58A6FF'];
const YER_RENKLERI = {
  eczane: '#F85149', saglik: '#F85149', egitim: '#BC8CFF', ibadet: '#39C5CF', kamu: '#58A6FF', banka: '#D29922',
  akaryakit: '#8B949E', yeme_icme: '#FF7B72', market: '#3FB950', firin: '#E3B341', otel: '#58A6FF', dukkan: '#8B949E',
};

const durum = {
  api: VARSAYILAN_API,
  anahtar: '',
  mtAnahtar: '',
  yap: null,
  katmanKod: 'v-dark',
  motorAd: 'maplibre',
  sekme: 'baglanti',
  goruntu: { lat: 39.0, lon: 35.0, zoom: 5.5 },
  veri: { pin: null, duraklar: [], sinir: null, rotalar: [], yakin: [], yerler: null, izokron: null },
};
let motor = null;

/* ---------- Yardimcilar ---------- */

const $ = (id) => document.getElementById(id);

function el(etiket, ozellikler = {}, ...cocuklar) {
  const dugum = document.createElement(etiket);
  for (const [k, v] of Object.entries(ozellikler)) {
    if (k === 'sinif') dugum.className = v;
    else if (k === 'metin') dugum.textContent = v;
    else dugum.setAttribute(k, v);
  }
  for (const c of cocuklar) dugum.append(c);
  return dugum;
}

function sayi(n, basamak = 0) {
  return Number(n).toLocaleString('tr-TR', { minimumFractionDigits: basamak, maximumFractionDigits: basamak });
}

function sureYaz(sn) {
  const dk = Math.round(sn / 60);
  if (dk < 60) return `${sayi(dk)} dk`;
  return `${sayi(Math.floor(dk / 60))} sa ${sayi(dk % 60)} dk`;
}

function mesafeYaz(m) {
  return m >= 1000 ? `${sayi(m / 1000, 1)} km` : `${sayi(m)} m`;
}

function mesaj(id, metin, tur = '') {
  const kutu = $(id);
  kutu.textContent = metin;
  kutu.className = `mesaj ${tur}`.trim();
}

function depoOku() {
  try {
    return JSON.parse(localStorage.getItem(DEPO_ANAHTARI) || '{}');
  } catch (hata) {
    console.warn('Kayıtlı ayarlar okunamadı', hata);
    return {};
  }
}

function depoYaz(veri) {
  try {
    localStorage.setItem(DEPO_ANAHTARI, JSON.stringify({ ...depoOku(), ...veri }));
  } catch (hata) {
    console.warn('Ayarlar kaydedilemedi', hata);
  }
}

class HataMesaji extends Error {}

const HATA_METNI = {
  401: 'Harita anahtarı geçersiz veya eksik.',
  403: 'Bu servis için izniniz yok.',
  404: 'Sonuç bulunamadı.',
  422: 'Girilen değer geçersiz.',
  429: 'İstek sınırı aşıldı, biraz bekleyin.',
  502: 'Servis şu an yanıt vermiyor (henüz hazır olmayabilir).',
  503: 'Servis hazır değil.',
};

/** HARITA API cagrisi; teknik ayrinti konsola, kullaniciya yalniz sade mesaj gider. */
async function api(yol, secenek = {}) {
  if (!durum.anahtar) throw new HataMesaji('Önce Bağlantı sekmesinden harita anahtarını girin.');
  let yanit;
  try {
    yanit = await fetch(`${durum.api.replace(/\/$/, '')}${yol}`, {
      ...secenek,
      headers: { 'X-Harita-Anahtar': durum.anahtar, 'Content-Type': 'application/json' },
    });
  } catch (hata) {
    console.error('API isteği başarısız', yol, hata);
    throw new HataMesaji('Harita servisine ulaşılamadı.');
  }
  if (!yanit.ok) {
    console.warn('API hata kodu', yanit.status, yol);
    throw new HataMesaji(HATA_METNI[yanit.status] || 'Beklenmeyen bir hata oluştu.');
  }
  return yanit.json();
}

function gecikmeli(islev, ms) {
  let zamanlayici;
  return (...args) => {
    clearTimeout(zamanlayici);
    zamanlayici = setTimeout(() => islev(...args), ms);
  };
}

function geometriKutusu(geometri) {
  let [bati, guney, dogu, kuzey] = [180, 90, -180, -90];
  const gez = (d) => {
    if (typeof d[0] === 'number') {
      bati = Math.min(bati, d[0]); dogu = Math.max(dogu, d[0]);
      guney = Math.min(guney, d[1]); kuzey = Math.max(kuzey, d[1]);
    } else d.forEach(gez);
  };
  gez(geometri.coordinates);
  return [bati, guney, dogu, kuzey];
}

/* ---------- Yapilandirma ve katman secimi ---------- */

function varsayilanYapilandirma() {
  return {
    karo: { adres: `${VARSAYILAN_KARO}/tiles/turkiye/{z}/{x}/{y}.mvt`, maksYakinlastirma: 15 },
    yaziTipleri: `${VARSAYILAN_KARO}/assets/fonts/{fontstack}/{range}.pbf`,
    simgeler: `${VARSAYILAN_KARO}/assets/sprites/v4`,
    merkez: [35.0, 39.0],
    atif: '© OpenStreetMap katkıcıları, Protomaps',
  };
}

function aktifKatman() {
  let k = KATMANLAR.find((x) => x.kod === durum.katmanKod) || KATMANLAR[0];
  if (k.tur !== 'vektor' && !durum.mtAnahtar) k = KATMANLAR[0];
  return k;
}

function mtAdres(k) {
  return `https://api.maptiler.com/maps/${k.harita}/{z}/{x}/{y}.${k.uzanti}?key=${encodeURIComponent(durum.mtAnahtar)}`;
}

function katmanSecimiDoldur() {
  const sec = $('katman');
  sec.replaceChildren();
  const gruplar = new Map();
  for (const k of KATMANLAR) {
    if (!gruplar.has(k.grup)) gruplar.set(k.grup, el('optgroup', { label: k.grup }));
    const gerekli = k.tur !== 'vektor' && !durum.mtAnahtar;
    const secenek = el('option', { value: k.kod, metin: gerekli ? `${k.ad} (MapTiler anahtarı gerekli)` : k.ad });
    if (gerekli) secenek.disabled = true;
    if (k.tur === 'karma' && durum.motorAd === 'leaflet') secenek.disabled = true;
    gruplar.get(k.grup).append(secenek);
  }
  gruplar.forEach((g) => sec.append(g));
  sec.value = aktifKatman().kod;
}

/* ---------- MapLibre motoru ---------- */

const BOS_KOLEKSIYON = { type: 'FeatureCollection', features: [] };

function ozellik(geometri) {
  return geometri ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geometri, properties: {} }] } : BOS_KOLEKSIYON;
}

/** Karma katman: uydu uzerinde okunur olsun diye yollar acik renk, yazilar beyaz ve koyu konturlu. */
function karmaKatmanlari() {
  const tum = layers('harita', namedFlavor('dark'), { lang: 'tr' });
  const cizgiler = tum
    .filter((l) => l.type === 'line' && ['roads', 'boundaries'].includes(l['source-layer']) && !/casing|tunnel_|bridges_/.test(l.id))
    .map((l) => ({
      ...l,
      paint: { ...l.paint, 'line-color': l['source-layer'] === 'boundaries' ? '#FFD166' : '#FFFFFF', 'line-opacity': 0.75 },
    }));
  const yazilar = tum.filter((l) => l.type === 'symbol').map((l) => ({
    ...l,
    paint: { ...l.paint, 'text-color': '#FFFFFF', 'text-halo-color': 'rgba(0,0,0,0.85)', 'text-halo-width': 1.6, 'text-halo-blur': 0.5 },
  }));
  return [...cizgiler, ...yazilar];
}

function stilKur(k) {
  const yap = durum.yap;
  const kaynaklar = {
    harita: { type: 'vector', tiles: [yap.karo.adres], maxzoom: yap.karo.maksYakinlastirma, attribution: yap.atif },
  };
  let katmanlar = [];
  let sprite = 'dark';
  if (k.tur === 'vektor') {
    sprite = k.tema;
    katmanlar = layers('harita', namedFlavor(k.tema), { lang: 'tr' });
  } else {
    kaynaklar.zemin = { type: 'raster', tiles: [mtAdres(k)], tileSize: 512, maxzoom: 20, attribution: MT_ATIF };
    katmanlar = [{ id: 'zemin', type: 'raster', source: 'zemin' }];
    if (k.tur === 'karma') {
      katmanlar.push(...karmaKatmanlari());
    }
  }
  return { version: 8, glyphs: yap.yaziTipleri, sprite: `${yap.simgeler}/${sprite}`, sources: kaynaklar, layers: katmanlar };
}

class MapLibreMotoru {
  constructor(kap, katman, goruntu, veri, cb) {
    Object.assign(this, { kap, katman, veri, cb, isaretler: [], pinIsareti: null });
    this.h = new maplibregl.Map({
      container: kap,
      style: stilKur(katman),
      center: [goruntu.lon, goruntu.lat],
      zoom: goruntu.zoom,
    });
    this.h.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-left');
    this.h.on('style.load', () => this.kaplamaKur());
    this.h.on('click', (e) => cb.tikla({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
    this.h.on('mousemove', (e) => cb.imlec({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
    this.h.on('move', () => cb.goruntu(this.goruntu()));
    this.pin(veri.pin);
    this.duraklar(veri.duraklar);
  }

  kaplamaKur() {
    const h = this.h;
    for (const id of ['sinir', 'rotalar', 'yakin', 'izokron', 'yerler']) {
      if (!h.getSource(id)) h.addSource(id, { type: 'geojson', data: BOS_KOLEKSIYON });
    }
    h.addLayer({ id: 'izokron-dolgu', type: 'fill', source: 'izokron', paint: { 'fill-color': ['get', 'renk'], 'fill-opacity': 0.16 } });
    h.addLayer({ id: 'izokron-cizgi', type: 'line', source: 'izokron', paint: { 'line-color': ['get', 'renk'], 'line-width': 2 } });
    h.addLayer({ id: 'sinir-dolgu', type: 'fill', source: 'sinir', paint: { 'fill-color': '#58A6FF', 'fill-opacity': 0.15 } });
    h.addLayer({ id: 'sinir-cizgi', type: 'line', source: 'sinir', paint: { 'line-color': '#58A6FF', 'line-width': 2 } });
    h.addLayer({
      id: 'rota-cizgi', type: 'line', source: 'rotalar',
      layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': ['get', 'renk'], 'line-width': 5 },
    });
    h.addLayer({
      id: 'yerler-nokta', type: 'circle', source: 'yerler',
      paint: { 'circle-radius': 4, 'circle-color': ['get', 'renk'], 'circle-stroke-color': '#0E1116', 'circle-stroke-width': 1 },
    });
    h.addLayer({
      id: 'yerler-ad', type: 'symbol', source: 'yerler', minzoom: 16,
      layout: { 'text-field': ['get', 'ad'], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 0.9], 'text-anchor': 'top' },
      paint: { 'text-color': '#E6EDF3', 'text-halo-color': '#0E1116', 'text-halo-width': 1.2 },
    });
    h.addLayer({
      id: 'yakin-nokta', type: 'circle', source: 'yakin',
      paint: { 'circle-radius': 5, 'circle-color': '#D29922', 'circle-stroke-color': '#0E1116', 'circle-stroke-width': 1 },
    });
    h.addLayer({
      id: 'yakin-ad', type: 'symbol', source: 'yakin',
      layout: { 'text-field': ['get', 'ad'], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 1.1], 'text-anchor': 'top' },
      paint: { 'text-color': '#D29922', 'text-halo-color': '#0E1116', 'text-halo-width': 1.2 },
    });
    this.sinir(this.veri.sinir);
    this.rotalar(this.veri.rotalar);
    this.yakin(this.veri.yakin);
    this.yerler(this.veri.yerler);
    this.izokron(this.veri.izokron);
  }

  katmanDegistir(k) {
    this.katman = k;
    this.h.setStyle(stilKur(k));
  }

  pin(ll) {
    this.veri.pin = ll;
    this.pinIsareti?.remove();
    this.pinIsareti = null;
    if (ll) this.pinIsareti = new maplibregl.Marker({ element: el('div', { sinif: 'pin-isaret' }) }).setLngLat([ll.lng, ll.lat]).addTo(this.h);
  }

  duraklar(liste) {
    this.veri.duraklar = liste;
    this.isaretler.forEach((m) => m.remove());
    this.isaretler = liste.map((d, i) => new maplibregl.Marker({
      element: el('div', { sinif: 'durak-isaret', metin: harf(i) }),
    }).setLngLat([d.lng, d.lat]).addTo(this.h));
  }

  veriYaz(kaynak, fc) {
    this.h.getSource(kaynak)?.setData(fc);
  }

  sinir(geometri) { this.veri.sinir = geometri; this.veriYaz('sinir', ozellik(geometri)); }
  rotalar(liste) {
    this.veri.rotalar = liste;
    this.veriYaz('rotalar', {
      type: 'FeatureCollection',
      features: liste.filter((r) => r.geometri).map((r) => ({ type: 'Feature', geometry: r.geometri, properties: { renk: r.renk } })),
    });
  }

  yerler(fc) { this.veri.yerler = fc; this.veriYaz('yerler', fc || BOS_KOLEKSIYON); }
  izokron(fc) { this.veri.izokron = fc; this.veriYaz('izokron', fc || BOS_KOLEKSIYON); }

  yakin(liste) {
    this.veri.yakin = liste;
    this.veriYaz('yakin', {
      type: 'FeatureCollection',
      features: liste.map((y) => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: [y.merkez.lon, y.merkez.lat] }, properties: { ad: y.ad },
      })),
    });
  }

  sigdir(kutu) { this.h.fitBounds([[kutu[0], kutu[1]], [kutu[2], kutu[3]]], { padding: 40, maxZoom: 15 }); }
  uc(lat, lon, zoom) { this.h.flyTo({ center: [lon, lat], zoom }); }
  kutu() { const b = this.h.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; }

  goruntu() {
    const c = this.h.getCenter();
    return { lat: c.lat, lon: c.lng, zoom: this.h.getZoom() };
  }

  yoket() { this.h.remove(); }
}

/* ---------- Leaflet motoru ---------- */

class LeafletMotoru {
  constructor(kap, katman, goruntu, veri, cb) {
    const L = window.L;
    Object.assign(this, { kap, katman, veri, cb, taban: null, ikame: false });
    // MapLibre zoom'u 512 px karoya gore; Leaflet 256 px karoya gore bir fazladir
    this.h = L.map(kap, { center: [goruntu.lat, goruntu.lon], zoom: goruntu.zoom + 1, zoomSnap: 0.25, worldCopyJump: false });
    this.sinirKatman = L.layerGroup().addTo(this.h);
    this.izokronKatman = L.layerGroup().addTo(this.h);
    this.rotaKatman = L.layerGroup().addTo(this.h);
    this.yerKatman = L.layerGroup().addTo(this.h);
    this.yakinKatman = L.layerGroup().addTo(this.h);
    this.isaretKatman = L.layerGroup().addTo(this.h);
    this.katmanDegistir(katman);
    this.h.on('click', (e) => cb.tikla({ lat: e.latlng.lat, lng: e.latlng.lng }));
    this.h.on('mousemove', (e) => cb.imlec({ lat: e.latlng.lat, lng: e.latlng.lng }));
    this.h.on('move', () => cb.goruntu(this.goruntu()));
    this.pin(veri.pin);
    this.duraklar(veri.duraklar);
    this.sinir(veri.sinir);
    this.rotalar(veri.rotalar);
    this.yakin(veri.yakin);
    this.yerler(veri.yerler);
    this.izokron(veri.izokron);
  }

  katmanDegistir(k) {
    const L = window.L;
    this.katman = k;
    if (this.taban) this.h.removeLayer(this.taban);
    // Karma katman yalniz MapLibre'de var; Leaflet'te hibrit rastere dusulur
    const kullanilan = k.tur === 'karma' ? KATMANLAR.find((x) => x.kod === 'mt-hybrid') : k;
    this.ikame = kullanilan !== k;
    if (kullanilan.tur === 'vektor') {
      this.taban = window.protomapsL.leafletLayer({
        url: durum.yap.karo.adres, flavor: kullanilan.tema, lang: 'tr',
        maxDataZoom: durum.yap.karo.maksYakinlastirma, attribution: durum.yap.atif,
      });
    } else {
      this.taban = L.tileLayer(mtAdres(kullanilan), {
        tileSize: 512, zoomOffset: -1, minZoom: 1, maxZoom: 20, crossOrigin: true, attribution: MT_ATIF,
      });
    }
    this.taban.addTo(this.h);
    this.taban.bringToBack?.();
  }

  ikon(sinif, metin = '') {
    return window.L.divIcon({ className: '', html: el('div', { sinif, metin }), iconSize: [22, 22], iconAnchor: [11, 11] });
  }

  pin(ll) {
    this.veri.pin = ll;
    this.pinMarker?.remove();
    this.pinMarker = null;
    if (ll) this.pinMarker = window.L.marker([ll.lat, ll.lng], { icon: this.ikon('pin-isaret') }).addTo(this.h);
  }

  duraklar(liste) {
    this.veri.duraklar = liste;
    this.isaretKatman.clearLayers();
    liste.forEach((d, i) => window.L.marker([d.lat, d.lng], { icon: this.ikon('durak-isaret', harf(i)) }).addTo(this.isaretKatman));
  }

  sinir(geometri) {
    this.veri.sinir = geometri;
    this.sinirKatman.clearLayers();
    if (geometri) {
      window.L.geoJSON({ type: 'Feature', geometry: geometri, properties: {} },
        { style: { color: '#58A6FF', weight: 2, fillColor: '#58A6FF', fillOpacity: 0.15 }, interactive: false }).addTo(this.sinirKatman);
    }
  }

  rotalar(liste) {
    this.veri.rotalar = liste;
    this.rotaKatman.clearLayers();
    liste.filter((r) => r.geometri).forEach((r) => window.L.geoJSON({ type: 'Feature', geometry: r.geometri, properties: {} },
      { style: { color: r.renk, weight: 5 }, interactive: false }).addTo(this.rotaKatman));
  }

  yerler(fc) {
    this.veri.yerler = fc;
    this.yerKatman.clearLayers();
    (fc ? fc.features : []).forEach((f) => window.L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius: 4, color: '#0E1116', weight: 1, fillColor: f.properties.renk, fillOpacity: 1,
    }).bindTooltip(f.properties.ad).addTo(this.yerKatman));
  }

  izokron(fc) {
    this.veri.izokron = fc;
    this.izokronKatman.clearLayers();
    if (fc) {
      window.L.geoJSON(fc, { style: (f) => ({ color: f.properties.renk, weight: 2, fillColor: f.properties.renk, fillOpacity: 0.16 }),
        interactive: false }).addTo(this.izokronKatman);
    }
  }

  yakin(liste) {
    this.veri.yakin = liste;
    this.yakinKatman.clearLayers();
    liste.forEach((y) => window.L.circleMarker([y.merkez.lat, y.merkez.lon], {
      radius: 5, color: '#0E1116', weight: 1, fillColor: '#D29922', fillOpacity: 1,
    }).bindTooltip(y.ad).addTo(this.yakinKatman));
  }

  sigdir(kutu) { this.h.fitBounds([[kutu[1], kutu[0]], [kutu[3], kutu[2]]], { padding: [40, 40], maxZoom: 16 }); }
  uc(lat, lon, zoom) { this.h.flyTo([lat, lon], zoom + 1); }
  kutu() { const b = this.h.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; }

  goruntu() {
    const c = this.h.getCenter();
    return { lat: c.lat, lon: c.lng, zoom: this.h.getZoom() - 1 };
  }

  yoket() { this.h.remove(); }
}

function harf(i) {
  return String.fromCharCode(65 + (i % 26));
}

/* ---------- Motor yonetimi ---------- */

function motorKur() {
  if (motor) {
    durum.goruntu = motor.goruntu();
    motor.yoket();
    motor = null;
  }
  const kap = $('harita');
  kap.replaceChildren();
  const Sinif = durum.motorAd === 'leaflet' ? LeafletMotoru : MapLibreMotoru;
  const cb = {
    tikla: haritaTikla,
    imlec: (ll) => { $('okuma-imlec').textContent = `${sayi(ll.lat, 5)} ${sayi(ll.lng, 5)}`; },
    goruntu: (g) => { $('okuma-zoom').textContent = sayi(g.zoom, 1); if ($('yer-katmani').checked) yerKatmaniGecikmeli(); },
  };
  motor = new Sinif(kap, aktifKatman(), durum.goruntu, durum.veri, cb);
  $('mt-logo').hidden = aktifKatman().tur === 'vektor';
  katmanNotu();
}

function katmanNotu() {
  const k = aktifKatman();
  if (durum.motorAd === 'leaflet' && k.tur === 'karma') mesaj('baglanti-mesaj', 'Karma katman yalnız MapLibre\'de var; Leaflet\'te hibrit gösterilir.', 'uyari');
}

function katmanDegistir(kod) {
  durum.katmanKod = kod;
  depoYaz({ katmanKod: kod });
  const k = aktifKatman();
  motor.katmanDegistir(k);
  $('mt-logo').hidden = k.tur === 'vektor';
  katmanNotu();
}

/* ---------- Baglanti ve durum ---------- */

async function baglan() {
  durum.api = $('api-adres').value.trim() || VARSAYILAN_API;
  durum.anahtar = $('api-anahtar').value.trim();
  durum.mtAnahtar = $('mt-anahtar').value.trim();
  depoYaz({ api: durum.api, anahtar: durum.anahtar, mtAnahtar: durum.mtAnahtar });
  try {
    const yap = await api('/v1/yapilandirma');
    durum.yap = { ...varsayilanYapilandirma(), ...yap, yaziTipleri: yap.yaziTipleri, simgeler: yap.simgeler };
    mesaj('baglanti-mesaj', `Bağlandı. Proje: ${yap.proje}`, 'basari');
  } catch (hata) {
    durum.yap = varsayilanYapilandirma();
    mesaj('baglanti-mesaj', hata instanceof HataMesaji ? hata.message : 'Bağlanılamadı.', 'hata');
  }
  katmanSecimiDoldur();
  motorKur();
  durumYenile();
}

async function durumYenile() {
  const liste = $('durum-liste');
  liste.replaceChildren();
  let veri = null;
  try {
    const yanit = await fetch(`${durum.api.replace(/\/$/, '')}/saglik/hazir`);
    veri = await yanit.json();
  } catch (hata) {
    console.error('Durum okunamadı', hata);
  }
  const etiketler = { veritabani: 'Veritabanı', redis: 'Redis', rota: 'Rota ve matris', arama: 'Adres arama' };
  for (const [anahtar, ad] of Object.entries(etiketler)) {
    const acik = veri ? Boolean(veri[anahtar]) : false;
    liste.append(el('li', {}, el('span', { sinif: `nokta ${veri ? (acik ? 'acik' : 'kapali') : ''}` }), el('span', { metin: `${ad}: ${veri ? (acik ? 'hazır' : 'hazır değil') : 'bilinmiyor'}` })));
  }
}

/* ---------- Sekmeler ---------- */

function sekmeAc(ad) {
  durum.sekme = ad;
  document.querySelectorAll('.sekme-dugme').forEach((d) => d.classList.toggle('aktif', d.dataset.sekme === ad));
  document.querySelectorAll('.sekme').forEach((s) => s.classList.toggle('aktif', s.id === `sekme-${ad}`));
}

function haritaTikla(ll) {
  if (durum.sekme === 'pin') pinKoy(ll);
  else if (durum.sekme === 'rota') durakEkle(ll);
}

/* ---------- Ara (metin -> konum) ---------- */

function adresMetni(p) {
  const sokak = [p.street, p.housenumber].filter(Boolean).join(' ');
  return [p.name, sokak, p.district, p.city, p.state, p.postcode].filter(Boolean).join(', ');
}

async function ara() {
  const metin = $('ara-girdi').value.trim();
  const liste = $('ara-liste');
  liste.replaceChildren();
  $('ara-ham').hidden = true;
  if (metin.length < 3) { mesaj('ara-mesaj', 'En az 3 karakter yazın.'); return; }
  mesaj('ara-mesaj', 'Aranıyor...');
  try {
    const g = motor.goruntu();
    const veri = await api(`/v1/adres/ara?q=${encodeURIComponent(metin)}&limit=15&lat=${g.lat}&lon=${g.lon}`);
    mesaj('ara-mesaj', veri.length ? `${sayi(veri.length)} sonuç` : 'Sonuç bulunamadı.');
    for (const r of veri) {
      const dugme = el('button', { type: 'button' }, el('div', { sinif: 'ad', metin: r.ad }),
        el('div', { sinif: 'alt', metin: `${TUR_ETIKET[r.tur] || r.tur} · ${r.adres}${r.mesafe_m !== null ? ` · ${mesafeYaz(r.mesafe_m)}` : ''}` }));
      dugme.addEventListener('click', () => adresSec(r));
      liste.append(el('li', {}, dugme));
    }
  } catch (hata) {
    mesaj('ara-mesaj', hata instanceof HataMesaji ? hata.message : 'Arama yapılamadı.', 'hata');
  }
}

async function adresSec(r) {
  motor.pin({ lat: r.merkez.lat, lng: r.merkez.lon });
  motor.uc(r.merkez.lat, r.merkez.lon, r.tur === 'kapi' ? 18 : r.tur === 'sokak' ? 16 : 15);
  const ham = $('ara-ham');
  ham.hidden = false;
  ham.textContent = `${sayi(r.merkez.lat, 6)} ; ${sayi(r.merkez.lon, 6)}\n${JSON.stringify(r, null, 2)}`;
  motor.sinir(null);
  if (r.tur === 'sokak') {
    try {
      const detay = await api(`/v1/adres/sokak/${r.id}?cizgi=true`);
      motor.sinir(detay.cizgi);
    } catch (hata) {
      console.warn('Sokak çizgisi alınamadı', hata);
    }
  }
}

/* ---------- Pin (konum -> adres) ---------- */

function kart(baslik, ...icerik) {
  return el('div', { sinif: 'kart' }, el('h3', { metin: baslik }), ...icerik);
}

function satirMetin(metin, sinif = '') {
  return el('div', { sinif, metin });
}

async function pinKoy(ll) {
  motor.pin(ll);
  const sonuc = $('pin-sonuc');
  sonuc.replaceChildren();
  mesaj('pin-mesaj', 'Sorgulanıyor...');
  const q = `lat=${ll.lat}&lon=${ll.lng}`;
  const [adres, yakin] = await Promise.allSettled([api(`/v1/adres/nokta?${q}&yaricap_m=150&limit=6`), api(`/v1/yerlesim/yakin?${q}&yaricap_m=5000&limit=15`)]);
  mesaj('pin-mesaj', '');
  sonuc.append(kart('Konum', satirMetin(`${sayi(ll.lat, 6)} ; ${sayi(ll.lng, 6)}`, 'sayi')));
  const hataKart = (baslik, neden) => kart(baslik, satirMetin(neden.reason instanceof HataMesaji ? neden.reason.message : 'Alınamadı.', 'soluk'));
  const listeKart = (baslik, ogeler, alt) => {
    const liste = el('ul', { sinif: 'liste' });
    ogeler.forEach((o) => liste.append(el('li', {}, el('div', { sinif: 'ad', metin: o.ad }), el('div', { sinif: 'alt', metin: alt(o) }))));
    return kart(baslik, liste);
  };
  if (adres.status === 'fulfilled') {
    const v = adres.value;
    sonuc.append(kart('Adres', satirMetin(v.adres || 'Adres bilgisi yok', 'zincir'),
      satirMetin([v.il, v.ilce, v.mahalle].filter(Boolean).join(' › '), 'soluk'),
      v.idari.en_yakin_merkez ? satirMetin(`En yakın merkez: ${TUR_ETIKET[v.idari.en_yakin_merkez.tur] || ''} ${v.idari.en_yakin_merkez.ad} (${mesafeYaz(v.idari.en_yakin_merkez.mesafe_m)})`) : satirMetin('')));
    if (v.kapilar.length) sonuc.append(listeKart('Kapı numaraları', v.kapilar, (o) => `${mesafeYaz(o.mesafe_m)}`));
    if (v.sokaklar.length) sonuc.append(listeKart('En yakın sokaklar', v.sokaklar, (o) => `${o.ek.sinif} · ${mesafeYaz(o.mesafe_m)}`));
    if (v.yerler.length) sonuc.append(listeKart('Yakındaki yerler', v.yerler, (o) => `${o.ek.yer_turu} · ${mesafeYaz(o.mesafe_m)}`));
  } else sonuc.append(hataKart('Adres', adres));
  if (yakin.status === 'fulfilled') {
    motor.yakin(yakin.value);
    sonuc.append(listeKart('Yakın merkezler (5 km)', yakin.value, (o) => `${TUR_ETIKET[o.tur] || o.tur} · ${mesafeYaz(o.mesafe_m)}`));
  } else {
    motor.yakin([]);
    sonuc.append(hataKart('Yakın merkezler', yakin));
  }
}

/* ---------- Yerlesim ---------- */

async function yerAra() {
  const metin = $('yer-girdi').value.trim();
  const liste = $('yer-liste');
  liste.replaceChildren();
  if (metin.length < 2) { mesaj('yer-mesaj', 'En az 2 karakter yazın.'); return; }
  mesaj('yer-mesaj', 'Aranıyor...');
  try {
    const tur = $('yer-tur').value;
    const veri = await api(`/v1/yerlesim/ara?q=${encodeURIComponent(metin)}&limit=30${tur ? `&tur=${tur}` : ''}`);
    mesaj('yer-mesaj', veri.length ? `${sayi(veri.length)} sonuç` : 'Sonuç bulunamadı.');
    veri.forEach((y) => liste.append(yerSatiri(y)));
  } catch (hata) {
    mesaj('yer-mesaj', hata instanceof HataMesaji ? hata.message : 'Arama yapılamadı.', 'hata');
  }
}

function yerSatiri(y) {
  const ust = y.ust ? ` · ${y.ust.ad}` : '';
  const dugme = el('button', { type: 'button' }, el('div', { sinif: 'ad', metin: y.ad }),
    el('div', { sinif: 'alt', metin: `${TUR_ETIKET[y.tur] || y.tur}${ust}` }));
  dugme.addEventListener('click', () => yerSec(y.id));
  return el('li', {}, dugme);
}

async function yerSec(id) {
  const detay = $('yer-detay');
  detay.replaceChildren();
  try {
    const y = await api(`/v1/yerlesim/${id}?sinir=true`);
    motor.sinir(y.sinir || null);
    if (y.sinir) motor.sigdir(geometriKutusu(y.sinir));
    else motor.uc(y.merkez.lat, y.merkez.lon, 14);
    motor.pin({ lat: y.merkez.lat, lng: y.merkez.lon });
    const zincir = [...y.zincir.map((z) => z.ad), y.ad].join(' › ');
    detay.append(kart(TUR_ETIKET[y.tur] || y.tur, satirMetin(zincir, 'zincir'),
      satirMetin(`Merkez: ${sayi(y.merkez.lat, 6)} ; ${sayi(y.merkez.lon, 6)}`, 'sayi'),
      y.nufus ? satirMetin(`Nüfus: ${sayi(y.nufus)}`, 'sayi') : satirMetin('')));
    const alt = await api(`/v1/yerlesim/${id}/alt?limit=200`);
    if (alt.length) {
      const liste = el('ul', { sinif: 'liste' });
      alt.forEach((a) => liste.append(yerSatiri(a)));
      detay.append(kart(`Alt öğeler (${sayi(alt.length)})`, liste));
    }
  } catch (hata) {
    detay.append(kart('Hata', satirMetin(hata instanceof HataMesaji ? hata.message : 'Alınamadı.', 'soluk')));
  }
}

/* ---------- Rota ve matris ---------- */

function durakEkle(ll) {
  if (durum.veri.duraklar.length >= 20) { mesaj('rota-mesaj', 'En fazla 20 durak eklenebilir.', 'uyari'); return; }
  durum.veri.duraklar = [...durum.veri.duraklar, ll];
  durakYenile();
}

function durakYenile() {
  motor.duraklar(durum.veri.duraklar);
  const liste = $('durak-liste');
  liste.replaceChildren();
  durum.veri.duraklar.forEach((d, i) => {
    const sil = el('button', { type: 'button', metin: 'Sil' });
    sil.addEventListener('click', () => { durum.veri.duraklar = durum.veri.duraklar.filter((_, j) => j !== i); durakYenile(); });
    liste.append(el('li', {}, el('span', { sinif: 'etiket', metin: harf(i) }), el('span', { sinif: 'koordinat', metin: `${sayi(d.lat, 5)} ; ${sayi(d.lng, 5)}` }), sil));
  });
}

function noktalar() {
  return durum.veri.duraklar.map((d) => ({ lat: d.lat, lon: d.lng }));
}

function rotaEkle(rota) {
  durum.rotaSayac = (durum.rotaSayac || 0) + 1;
  durum.veri.rotalar = [...durum.veri.rotalar, { ...rota, renk: ROTA_RENKLERI[(durum.rotaSayac - 1) % ROTA_RENKLERI.length], no: durum.rotaSayac }];
  motor.rotalar(durum.veri.rotalar);
  rotaListesiYaz();
}

function rotaListesiYaz() {
  const sonuc = $('rota-sonuc');
  sonuc.replaceChildren();
  durum.veri.rotalar.forEach((r) => {
    const sil = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'Sil' });
    sil.addEventListener('click', () => {
      durum.veri.rotalar = durum.veri.rotalar.filter((x) => x.no !== r.no);
      motor.rotalar(durum.veri.rotalar);
      rotaListesiYaz();
    });
    const rozet = el('span', { sinif: 'renk-nokta' });
    rozet.style.setProperty('--renk', r.renk);
    sonuc.append(el('div', { sinif: 'kart' }, el('h3', {}, rozet, ` Rota ${r.no} · ${r.baslik}`),
      satirMetin(`Mesafe: ${mesafeYaz(r.mesafe_m)}`, 'sayi'), satirMetin(`Süre: ${sureYaz(r.sure_sn)}`, 'sayi'),
      r.not ? satirMetin(r.not, 'soluk') : satirMetin(''), sil));
  });
}

async function rotaCiz() {
  if (durum.veri.duraklar.length < 2) { mesaj('rota-mesaj', 'En az 2 durak gerekli.', 'uyari'); return; }
  mesaj('rota-mesaj', 'Hesaplanıyor...');
  try {
    const profil = $('rota-profil').value;
    const v = await api('/v1/rota', { method: 'POST', body: JSON.stringify({ noktalar: noktalar(), profil, geometri: true }) });
    mesaj('rota-mesaj', '');
    rotaEkle({ geometri: v.geometri, mesafe_m: v.mesafe_m, sure_sn: v.sure_sn, baslik: $('rota-profil').selectedOptions[0].textContent });
    if (v.geometri) motor.sigdir(geometriKutusu(v.geometri));
  } catch (hata) {
    mesaj('rota-mesaj', hata instanceof HataMesaji ? hata.message : 'Rota hesaplanamadı.', 'hata');
  }
}

/** Kodlanmis polyline'i [boylam, enlem] listesine cevirir (Valhalla: hassasiyet 6). */
function polylineCoz(metin, hassasiyet = 6) {
  const carpan = 10 ** hassasiyet;
  let indeks = 0; let enlem = 0; let boylam = 0;
  const sonuc = [];
  while (indeks < metin.length) {
    for (const hedef of ['enlem', 'boylam']) {
      let kaydirma = 0; let deger = 0; let bayt;
      do {
        bayt = metin.charCodeAt(indeks++) - 63;
        deger |= (bayt & 0x1f) << kaydirma;
        kaydirma += 5;
      } while (bayt >= 0x20);
      const fark = deger & 1 ? ~(deger >> 1) : deger >> 1;
      if (hedef === 'enlem') enlem += fark; else boylam += fark;
    }
    sonuc.push([boylam / carpan, enlem / carpan]);
  }
  return sonuc;
}

const COSTING = { auto: 'auto', motosiklet: 'motorcycle', bisiklet: 'bicycle', yaya: 'pedestrian' };

/** Duraklari en kisa sureyle gezen sirayi bulur (Valhalla optimized_route). */
async function optimizeRota() {
  if (durum.veri.duraklar.length < 3) { mesaj('rota-mesaj', 'Optimizasyon için en az 3 durak gerekli.', 'uyari'); return; }
  mesaj('rota-mesaj', 'Optimize ediliyor...');
  try {
    const v = await api('/valhalla/optimized_route', { method: 'POST', body: JSON.stringify({
      locations: noktalar(), costing: COSTING[$('rota-profil').value], directions_options: { units: 'kilometers' } }) });
    const koordinatlar = v.trip.legs.flatMap((b) => polylineCoz(b.shape, 6));
    const sira = (v.trip.locations || []).map((k) => harf(k.original_index)).join(' → ');
    mesaj('rota-mesaj', '');
    rotaEkle({ geometri: { type: 'LineString', coordinates: koordinatlar }, mesafe_m: v.trip.summary.length * 1000, sure_sn: v.trip.summary.time,
      baslik: 'Optimize', not: `Sıra: ${sira}` });
    motor.sigdir(geometriKutusu({ coordinates: koordinatlar }));
  } catch (hata) {
    mesaj('rota-mesaj', hata instanceof HataMesaji ? hata.message : 'Optimize edilemedi.', 'hata');
  }
}

/** Ilk duraktan (yoksa pinden) verilen dakikalarda ulasilabilen alanlari cizer (Valhalla isochrone). */
async function izokronHesapla() {
  const kaynak = durum.veri.duraklar[0] || durum.veri.pin;
  if (!kaynak) { mesaj('rota-mesaj', 'Önce bir durak ekleyin veya pin koyun.', 'uyari'); return; }
  const dakikalar = $('izokron-sure').value.split(',').map((x) => Number(x.trim())).filter((x) => x > 0 && x <= 60).sort((a, b) => a - b).slice(0, 5);
  if (!dakikalar.length) { mesaj('rota-mesaj', 'Dakikaları 5,10,15 gibi yazın.', 'uyari'); return; }
  mesaj('rota-mesaj', 'Hesaplanıyor...');
  try {
    const v = await api('/valhalla/isochrone', { method: 'POST', body: JSON.stringify({
      locations: [{ lat: kaynak.lat, lon: kaynak.lng }], costing: COSTING[$('rota-profil').value],
      contours: dakikalar.map((time) => ({ time })), polygons: true, denoise: 0.5, generalize: 50 }) });
    mesaj('rota-mesaj', `${dakikalar.join(', ')} dakikalık erişim alanı çizildi.`, 'basari');
    v.features.forEach((f) => {
      const sira = dakikalar.indexOf(f.properties.contour);
      f.properties.renk = IZOKRON_RENKLERI[Math.max(sira, 0) % IZOKRON_RENKLERI.length];
    });
    motor.izokron(v);
    const buyuk = v.features[v.features.length - 1];
    if (buyuk) motor.sigdir(geometriKutusu(buyuk.geometry));
  } catch (hata) {
    mesaj('rota-mesaj', hata instanceof HataMesaji ? hata.message : 'Erişim alanı hesaplanamadı.', 'hata');
  }
}

/** Gorunen harita kutusundaki yer isaretlerini cizer (yakinlastirma >= 14). */
async function yerKatmaniYukle() {
  if (!$('yer-katmani').checked) { motor.yerler(null); return; }
  if (motor.goruntu().zoom < 14) { motor.yerler(null); mesaj('baglanti-mesaj', 'Yerleri görmek için haritayı yakınlaştırın (z14+).', 'uyari'); return; }
  try {
    const [b, g, d, k] = motor.kutu();
    const fc = await api(`/v1/adres/yerler?bati=${b}&guney=${g}&dogu=${d}&kuzey=${k}&limit=1500`);
    fc.features.forEach((f) => { f.properties.renk = YER_RENKLERI[f.properties.tur] || '#8B949E'; });
    motor.yerler(fc);
    mesaj('baglanti-mesaj', `${sayi(fc.features.length)} yer gösteriliyor.`);
  } catch (hata) {
    mesaj('baglanti-mesaj', hata instanceof HataMesaji ? hata.message : 'Yerler alınamadı.', 'hata');
  }
}
const yerKatmaniGecikmeli = gecikmeli(yerKatmaniYukle, 700);

async function matrisHesapla() {
  const sonuc = $('matris-sonuc');
  sonuc.replaceChildren();
  if (durum.veri.duraklar.length < 2) { mesaj('rota-mesaj', 'En az 2 durak gerekli.', 'uyari'); return; }
  mesaj('rota-mesaj', 'Hesaplanıyor...');
  try {
    const p = noktalar();
    const v = await api('/v1/matris', { method: 'POST', body: JSON.stringify({ kaynaklar: p, hedefler: p, profil: $('rota-profil').value }) });
    mesaj('rota-mesaj', '');
    const tablo = el('table', { sinif: 'tablo' });
    tablo.append(el('thead', {}, el('tr', {}, el('th', { metin: '' }), ...p.map((_, i) => el('th', { metin: harf(i) })))));
    const govde = el('tbody');
    v.sure_sn.forEach((satir, i) => govde.append(el('tr', {}, el('th', { metin: harf(i) }),
      ...satir.map((s, j) => el('td', { metin: s === null ? '-' : `${sureYaz(s)} · ${mesafeYaz(v.mesafe_m[i][j])}` })))));
    tablo.append(govde);
    sonuc.append(kart('Süre ve mesafe matrisi (satır: kaynak, sütun: hedef)', tablo));
  } catch (hata) {
    mesaj('rota-mesaj', hata instanceof HataMesaji ? hata.message : 'Matris hesaplanamadı.', 'hata');
  }
}

function rotaTemizle() {
  durum.veri.duraklar = [];
  durum.veri.rotalar = [];
  motor.rotalar([]);
  motor.izokron(null);
  durakYenile();
  rotaListesiYaz();
  $('matris-sonuc').replaceChildren();
  mesaj('rota-mesaj', '');
}

/* ---------- Surum bilgisi ---------- */

async function surumGoster() {
  const kutu = $('surum');
  try {
    const liste = (await (await fetch('surum.json', { cache: 'no-store' })).json()).slice(0, 3);
    const gorulen = depoOku().gorulenSurum;
    liste.forEach((s, i) => kutu.append(el('div', { sinif: i === 0 && gorulen !== s.surum ? 'yeni' : '', metin: `${s.surum} ${s.not}` })));
    if (liste.length) setTimeout(() => depoYaz({ gorulenSurum: liste[0].surum }), 5000);
  } catch (hata) {
    console.warn('Sürüm bilgisi okunamadı', hata);
  }
}

/* ---------- Baslangic ---------- */

function hashOku() {
  const p = new URLSearchParams(location.hash.slice(1));
  const sonuc = { anahtar: p.get('anahtar'), mtAnahtar: p.get('mt') };
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  return sonuc;
}

/** Sunucunun (Coolify ortam degiskenleri) verdigi yapilandirma; yoksa bos doner. */
async function sunucuYapilandirmasi() {
  try {
    const yanit = await fetch('yapilandirma.json', { cache: 'no-store' });
    return yanit.ok ? await yanit.json() : {};
  } catch (hata) {
    console.warn('Sunucu yapılandırması okunamadı', hata);
    return {};
  }
}

async function baslat() {
  const kayit = depoOku();
  const hash = hashOku();
  const sunucu = await sunucuYapilandirmasi();
  durum.api = kayit.api || VARSAYILAN_API;
  durum.anahtar = hash.anahtar || kayit.anahtar || sunucu.anahtar || '';
  durum.mtAnahtar = (hash.mtAnahtar || kayit.mtAnahtar || sunucu.mtAnahtar || '').replace(/['"\s]/g, '');
  durum.katmanKod = kayit.katmanKod || 'v-dark';
  durum.motorAd = kayit.motorAd || 'maplibre';
  durum.yap = varsayilanYapilandirma();
  if (kayit.tema) document.documentElement.dataset.theme = kayit.tema;

  $('api-adres').value = durum.api;
  $('api-anahtar').value = durum.anahtar;
  $('mt-anahtar').value = durum.mtAnahtar;
  $('motor').value = durum.motorAd;

  document.querySelectorAll('.sekme-dugme').forEach((d) => d.addEventListener('click', () => sekmeAc(d.dataset.sekme)));
  $('baglan').addEventListener('click', baglan);
  $('durum-yenile').addEventListener('click', durumYenile);
  $('katman').addEventListener('change', (e) => katmanDegistir(e.target.value));
  $('motor').addEventListener('change', (e) => {
    durum.motorAd = e.target.value;
    depoYaz({ motorAd: durum.motorAd });
    if (durum.motorAd === 'leaflet' && aktifKatman().tur === 'karma') durum.katmanKod = 'v-dark';
    katmanSecimiDoldur();
    motorKur();
  });
  $('tema').addEventListener('click', () => {
    const yeni = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = yeni;
    depoYaz({ tema: yeni });
  });
  $('panel-ac').addEventListener('click', () => $('panel').classList.toggle('kapali'));
  const araGecikmeli = gecikmeli(ara, 400);
  $('ara-girdi').addEventListener('input', araGecikmeli);
  $('ara-girdi').addEventListener('keydown', (e) => { if (e.key === 'Enter') ara(); });
  const yerGecikmeli = gecikmeli(yerAra, 350);
  $('yer-girdi').addEventListener('input', yerGecikmeli);
  $('yer-tur').addEventListener('change', yerAra);
  $('rota-ciz').addEventListener('click', rotaCiz);
  $('matris-hesapla').addEventListener('click', matrisHesapla);
  $('rota-temizle').addEventListener('click', rotaTemizle);
  $('rota-optimize').addEventListener('click', optimizeRota);
  $('izokron-hesapla').addEventListener('click', izokronHesapla);
  $('yer-katmani').addEventListener('change', yerKatmaniYukle);
  document.addEventListener('keydown', (e) => {
    const yazan = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName);
    if (e.key === '/' && !yazan) {
      e.preventDefault();
      if (durum.sekme !== 'ara' && durum.sekme !== 'yerlesim') sekmeAc('ara');
      $(durum.sekme === 'yerlesim' ? 'yer-girdi' : 'ara-girdi').focus();
    }
  });

  katmanSecimiDoldur();
  motorKur();
  surumGoster();
  if (durum.anahtar) baglan();
  else durumYenile();
}

baslat();
