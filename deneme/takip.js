/**
 * HARITA takip sayfasi: bir surucunun "Varisimi paylas" ile gonderdigi canli konumu ve varis bilgisini gosterir.
 * Baglanti: takip.html?k=<kanal>. Konum HARITA canli servisinden WebSocket ile gelir (10 sn kalp atisi, kopunca otomatik yeniden baglanma).
 * Harita anahtari navigasyon sayfalariyla ayni sunucu yapilandirmasindan (yapilandirma.json) gelir.
 */
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/+esm';
import { layers, namedFlavor } from 'https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/+esm';

const VARSAYILAN_API = 'https://harita-api.89.45.45.152.sslip.io';
const VARSAYILAN_KARO = 'https://harita-karo.89.45.45.152.sslip.io';
const DENEME_DEPO = 'harita_deneme_v1';
const SURUM_DEPO = 'harita_takip_surum_goruldu';
const ANAHTAR_EN_AZ = 16;
const KANAL_DESENI = /^[A-Za-z0-9_-]{8,64}$/;
const SESSIZLIK_SN = 35;
const YENIDEN_BAGLAN_MS = [2000, 4000, 8000, 15000];
const ESKI_KONUM_SN = 90;

const durum = {
  api: VARSAYILAN_API,
  anahtar: '',
  kanal: '',
  ws: null,
  denemeSayac: 0,
  sonMesaj: 0,
  son: null,
  bitti: false,
  takipEt: true,
  ilkKonum: true,
};
let harita = null;
let isaret = null;
let hedefIsareti = null;
let yenidenZamanlayici = null;
let isaretEkli = false;
let hedefEkli = false;

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

const saatYaz = (tarih) => tarih.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false });
const sayi = (n, basamak = 0) => Number(n).toLocaleString('tr-TR', { minimumFractionDigits: basamak, maximumFractionDigits: basamak });

function mesafeYaz(m) {
  if (m >= 10000) return `${sayi(m / 1000)} km`;
  if (m >= 1000) return `${sayi(m / 1000, 1)} km`;
  return `${sayi(Math.max(0, Math.round(m / 10) * 10))} m`;
}

function sureYaz(sn) {
  const dk = Math.max(0, Math.round(sn / 60));
  if (dk < 60) return `${sayi(dk)} dk`;
  return `${sayi(Math.floor(dk / 60))} sa ${sayi(dk % 60)} dk`;
}

const anahtarTemizle = (deger) => String(deger || '').replace(/['"\s]/g, '');
const ilkGecerliAnahtar = (...adaylar) => adaylar.map(anahtarTemizle).find((a) => a.length >= ANAHTAR_EN_AZ) || '';

function depoOku(ad) {
  try {
    return JSON.parse(localStorage.getItem(ad) || '{}');
  } catch (hata) {
    console.warn('Kayıtlı ayarlar okunamadı', ad, hata);
    return {};
  }
}

async function sunucuYapilandirmasi() {
  try {
    const yanit = await fetch('yapilandirma.json', { cache: 'no-store' });
    return yanit.ok ? await yanit.json() : {};
  } catch (hata) {
    console.warn('Sunucu yapılandırması okunamadı', hata);
    return {};
  }
}

/** Durum satirini ve noktasini gunceller. tur: canli | bekle | bitti */
function durumYaz(metin, tur = 'bekle') {
  $('durum-metin').textContent = metin;
  $('durum-nokta').className = `durum-nokta ${tur === 'bekle' ? '' : tur}`.trim();
}

/** Karti son konum bilgisiyle doldurur. */
function kartYaz() {
  const m = durum.son;
  if (!m) return;
  const v = m.veri || {};
  if (v.bitti) {
    $('varis').textContent = v.varildi ? 'Vardı' : 'Bitti';
    $('varis-etiket').textContent = '';
    $('kart-alt').textContent = v.varildi ? 'Sürücü hedefine ulaştı.' : 'Sürücü paylaşımı durdurdu.';
    return;
  }
  $('varis').textContent = v.varis ? saatYaz(new Date(v.varis)) : '-';
  $('varis-etiket').textContent = v.varis ? 'tahmini varış' : '';
  const parca = [];
  if (Number.isFinite(v.kalanSn)) parca.push(sureYaz(v.kalanSn));
  if (Number.isFinite(v.kalanM)) parca.push(mesafeYaz(v.kalanM));
  if (v.hedefAd) parca.push(v.hedefAd);
  $('kart-alt').textContent = parca.join(' · ') || 'Konum alındı.';
}

function isaretKur() {
  const kap = el('div', { sinif: 'konum-isaret', 'aria-hidden': 'true' });
  kap.innerHTML = '<svg viewBox="-17 -17 34 34"><circle class="yonsuz" r="7"></circle>'
    + '<path class="govde" d="M0 -14 L10 11 L0 5 L-10 11 Z" display="none"></path></svg>';
  isaret = new maplibregl.Marker({ element: kap, rotationAlignment: 'map', pitchAlignment: 'map' });
}

/** Gelen konumu haritaya ve karta isler. Yalniz ilk surucu izlenir (kanal tek kisilik paylasimdir). */
function konumIsle(m) {
  if (durum.bitti || !Number.isFinite(m.lat) || !Number.isFinite(m.lon)) return;
  if (durum.son && m.zaman && durum.son.zaman && m.zaman < durum.son.zaman) return;
  durum.son = m;
  const yonlu = Number.isFinite(m.yon);
  const kap = isaret.getElement();
  kap.querySelector('.govde').setAttribute('display', yonlu ? 'inline' : 'none');
  kap.querySelector('.yonsuz').setAttribute('display', yonlu ? 'none' : 'inline');
  isaret.setLngLat([m.lon, m.lat]).setRotation(yonlu ? m.yon : 0);
  if (!isaretEkli) {
    isaret.addTo(harita);
    isaretEkli = true;
  }

  const h = m.veri?.hedef;
  if (h && Number.isFinite(h.lat) && Number.isFinite(h.lon)) {
    if (!hedefIsareti) hedefIsareti = new maplibregl.Marker({ color: '#F85149' });
    hedefIsareti.setLngLat([h.lon, h.lat]);
    if (!hedefEkli) {
      hedefIsareti.addTo(harita);
      hedefEkli = true;
    }
  }
  kartYaz();
  if (m.veri?.bitti) {
    durum.bitti = true;
    durumYaz(m.veri.varildi ? 'Yolculuk tamamlandı' : 'Paylaşım bitti', 'bitti');
    durum.ws?.close();
    $('takip-et').hidden = true;
    return;
  }
  durumYaz('Canlı', 'canli');
  kamera(m, h);
}

/** Ilk konumda surucu ve hedefi birlikte gosterir; sonra surucuyu takip eder (kullanici kaydirirsa durur). */
function kamera(m, h) {
  if (durum.ilkKonum) {
    durum.ilkKonum = false;
    if (h && Number.isFinite(h.lat)) {
      harita.fitBounds([[Math.min(m.lon, h.lon), Math.min(m.lat, h.lat)], [Math.max(m.lon, h.lon), Math.max(m.lat, h.lat)]],
        { padding: { top: 150, bottom: 60, left: 40, right: 40 }, maxZoom: 16, duration: 800 });
    } else {
      harita.flyTo({ center: [m.lon, m.lat], zoom: 15, duration: 800 });
    }
    return;
  }
  if (durum.takipEt) harita.easeTo({ center: [m.lon, m.lat], duration: 900 });
}

/* ---------- WebSocket ---------- */

function sesiKapat() {
  clearTimeout(yenidenZamanlayici);
  if (durum.ws) {
    durum.ws.onclose = null;
    durum.ws.close();
    durum.ws = null;
  }
}

function yenidenBaglan() {
  if (durum.bitti) return;
  durumYaz('Bağlantı koptu, yeniden bağlanılıyor...', 'bekle');
  const bekle = YENIDEN_BAGLAN_MS[Math.min(durum.denemeSayac, YENIDEN_BAGLAN_MS.length - 1)];
  durum.denemeSayac += 1;
  clearTimeout(yenidenZamanlayici);
  yenidenZamanlayici = setTimeout(baglan, bekle);
}

function baglan() {
  sesiKapat();
  if (durum.bitti) return;
  const adres = `${durum.api.replace(/\/$/, '').replace(/^http/, 'ws')}/v1/canli/ws`;
  let ws;
  try {
    ws = new WebSocket(adres);
  } catch (hata) {
    console.error('WebSocket açılamadı', hata);
    yenidenBaglan();
    return;
  }
  durum.ws = ws;
  durum.sonMesaj = Date.now();
  ws.onopen = () => ws.send(JSON.stringify({ tip: 'giris', anahtar: durum.anahtar, kanal: durum.kanal, dinle: true }));
  ws.onmessage = (olay) => {
    durum.sonMesaj = Date.now();
    let m;
    try {
      m = JSON.parse(olay.data);
    } catch (hata) {
      console.warn('Geçersiz mesaj', hata);
      return;
    }
    if (m.tip === 'ping') ws.send(JSON.stringify({ tip: 'pong' }));
    else if (m.tip === 'hazir') {
      durum.denemeSayac = 0;
      if (!m.konumlar?.length) durumYaz('Paylaşım bekleniyor', 'bekle');
      (m.konumlar || []).forEach(konumIsle);
    } else if (m.tip === 'konum') konumIsle(m);
    else if (m.tip === 'hata') {
      console.warn('Canlı servis hatası', m.mesaj);
      durumYaz('Bağlantı kurulamadı. Bağlantı süresi dolmuş olabilir.', 'bekle');
    }
  };
  ws.onerror = () => console.warn('WebSocket hatası');
  ws.onclose = () => yenidenBaglan();
}

/** Her 5 sn: sessizlik denetimi (35 sn mesaj yoksa yeniden baglan) ve konum tazeligi. */
function izle() {
  setInterval(() => {
    if (durum.bitti) return;
    if (durum.ws && Date.now() - durum.sonMesaj > SESSIZLIK_SN * 1000) {
      console.warn('Canlı bağlantı sessiz, yeniden bağlanılıyor');
      durum.ws.close();
      return;
    }
    const m = durum.son;
    if (m?.zaman && Date.now() / 1000 - m.zaman > ESKI_KONUM_SN) {
      durumYaz(`Konum bekleniyor (son: ${saatYaz(new Date(m.zaman * 1000))})`, 'bekle');
    }
  }, 5000);
}

/* ---------- Baslangic ---------- */

function stilKur(yap) {
  const koyu = !matchMedia('(prefers-color-scheme: light)').matches;
  const tema = koyu ? 'dark' : 'light';
  if (koyu) delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = 'light';
  return {
    version: 8,
    glyphs: yap.yaziTipleri,
    sprite: `${yap.simgeler}/${tema}`,
    sources: { harita: { type: 'vector', tiles: [yap.karo.adres], maxzoom: yap.karo.maksYakinlastirma, attribution: yap.atif } },
    layers: layers('harita', namedFlavor(tema), { lang: 'tr' }),
  };
}

async function haritaYapilandirmasi() {
  const varsayilan = {
    karo: { adres: `${VARSAYILAN_KARO}/tiles/turkiye/{z}/{x}/{y}.mvt`, maksYakinlastirma: 15 },
    yaziTipleri: `${VARSAYILAN_KARO}/assets/fonts/{fontstack}/{range}.pbf`,
    simgeler: `${VARSAYILAN_KARO}/assets/sprites/v4`,
    atif: '© OpenStreetMap katkıcıları, Protomaps',
  };
  try {
    const yanit = await fetch(`${durum.api.replace(/\/$/, '')}/v1/yapilandirma`, { headers: { 'X-Harita-Anahtar': durum.anahtar } });
    if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
    const yap = await yanit.json();
    return { ...varsayilan, ...Object.fromEntries(Object.entries(yap).filter(([, v]) => v != null)) };
  } catch (hata) {
    console.warn('Harita yapılandırması alınamadı, varsayılan kullanılıyor', hata);
    return varsayilan;
  }
}

/** Son 3 surumu sol altta gosterir; en yeni surum ilk goruldugunde yesil, sonra normal renkte kalin. */
async function surumGoster() {
  const kutu = $('surum');
  try {
    const liste = (await (await fetch('surum.json', { cache: 'no-store' })).json()).slice(0, 3);
    let goruldu = '';
    try {
      goruldu = localStorage.getItem(SURUM_DEPO) || '';
      localStorage.setItem(SURUM_DEPO, liste[0]?.surum || '');
    } catch (hata) {
      console.warn('Sürüm kaydı tutulamadı', hata);
    }
    liste.forEach((s, i) => kutu.append(el('div', { sinif: i === 0 && s.surum !== goruldu ? 'yeni' : '', metin: `${s.surum} ${s.not}` })));
  } catch (hata) {
    console.warn('Sürüm bilgisi okunamadı', hata);
  }
}

async function baslat() {
  const kanal = new URLSearchParams(location.search).get('k') || '';
  if (!KANAL_DESENI.test(kanal)) {
    durumYaz('Geçersiz takip bağlantısı.', 'bitti');
    $('kart-alt').textContent = 'Bağlantıyı gönderen kişiden yenisini isteyin.';
    return;
  }
  durum.kanal = kanal;
  const deneme = depoOku(DENEME_DEPO);
  const sunucu = await sunucuYapilandirmasi();
  durum.api = deneme.api || VARSAYILAN_API;
  durum.anahtar = ilkGecerliAnahtar(sunucu.anahtar, deneme.anahtar);
  if (!durum.anahtar) {
    durumYaz('Takip şu an kullanılamıyor.', 'bitti');
    console.error('Harita anahtarı yok');
    return;
  }
  const yap = await haritaYapilandirmasi();
  harita = new maplibregl.Map({ container: 'harita', style: stilKur(yap), center: [35.0, 39.0], zoom: 5.5, attributionControl: { compact: true } });
  isaretKur();
  const birak = (olay) => {
    if (olay.originalEvent && durum.takipEt) {
      durum.takipEt = false;
      $('takip-et').hidden = false;
    }
  };
  harita.on('dragstart', birak);
  harita.on('zoomstart', birak);
  $('takip-et').addEventListener('click', () => {
    durum.takipEt = true;
    $('takip-et').hidden = true;
    if (durum.son) harita.easeTo({ center: [durum.son.lon, durum.son.lat], duration: 600 });
  });
  surumGoster();
  izle();
  baglan();
}

baslat();
