/**
 * HARITA navigasyon denemesi: hedef arama, Valhalla rotasi, adim adim Turkce sesli yonlendirme,
 * konum takibi, rotadan sapinca yeniden rota ve masaustunde denemek icin simulasyon.
 * Harita anahtari deneme sayfasiyla ayni tarayici kaydindan ya da sunucu yapilandirmasindan gelir.
 */
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/+esm';
import { layers, namedFlavor } from 'https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/+esm';
import { UcBoyutKontrolu } from './harita-3d.js';

const VARSAYILAN_API = 'https://harita-api.89.45.45.152.sslip.io';
const VARSAYILAN_KARO = 'https://harita-karo.89.45.45.152.sslip.io';
const DENEME_DEPO = 'harita_deneme_v1';
const NAV_DEPO = 'harita_nav_v1';
const SURUM_DEPO = 'harita_nav_surum_goruldu';
const ANAHTAR_EN_AZ = 16;
const DUNYA_R = 6371008.8;

const COSTING = { araba: 'auto', motosiklet: 'motorcycle', yaya: 'pedestrian' };

const MT_ATIF = '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">&copy; MapTiler</a> '
  + '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap katkıcıları</a>';

/**
 * Secilebilir harita katmanlari (deneme sayfasiyla ayni). tur: vektor (kendi karolarimiz), mt (MapTiler raster),
 * karma (uydu + kendi yol ve etiketlerimiz). acik: arayuz acik temaya gecer.
 */
const KATMANLAR = [
  { kod: 'oto', grup: 'Otomatik', ad: 'Otomatik (gündüz açık, gece koyu)', tur: 'oto' },
  { kod: 'v-dark', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - koyu', tur: 'vektor', tema: 'dark' },
  { kod: 'v-light', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - açık', tur: 'vektor', tema: 'light', acik: true },
  { kod: 'v-white', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - beyaz', tur: 'vektor', tema: 'white', acik: true },
  { kod: 'v-grayscale', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - gri', tur: 'vektor', tema: 'grayscale', acik: true },
  { kod: 'v-black', grup: 'Kendi verimiz (HARITA)', ad: 'Sokak - siyah', tur: 'vektor', tema: 'black' },
  { kod: 'karma', grup: 'Uydu', ad: 'Uydu + kendi yol ve etiketlerimiz', tur: 'karma', harita: 'satellite', uzanti: 'jpg' },
  { kod: 'mt-hybrid', grup: 'Uydu', ad: 'Hibrit (MapTiler)', tur: 'mt', harita: 'hybrid-v4', uzanti: 'jpg' },
  { kod: 'mt-satellite', grup: 'Uydu', ad: 'Uydu (MapTiler)', tur: 'mt', harita: 'satellite', uzanti: 'jpg' },
  { kod: 'mt-streets', grup: 'MapTiler', ad: 'Sokak (MapTiler)', tur: 'mt', harita: 'streets-v2', uzanti: 'png', acik: true },
  { kod: 'mt-osm', grup: 'MapTiler', ad: 'Ayrıntılı (MapTiler)', tur: 'mt', harita: 'openstreetmap', uzanti: 'png', acik: true },
];
const YER_DEPO = 'harita_nav_yerler';
/** "Yolda ara" turleri (HARITA yer turu kodlari). */
const YOLDA_TURLERI = [
  { kod: 'akaryakit', ad: 'Yakıt' }, { kod: 'yeme_icme', ad: 'Yemek' }, { kod: 'eczane', ad: 'Eczane' },
  { kod: 'banka', ad: 'ATM / Banka' }, { kod: 'market', ad: 'Market' }, { kod: 'otel', ad: 'Otel' },
];
const YOLDA_TAMPON_M = 800;
const YOLDA_KOORD_MAKS = 1500;
/** Hiz limiti sorgusunda bir istekteki rota noktasi sayisi. */
const HIZ_PARCA_NOKTA = 500;
const HIZ_ASIM_TOLERANS_KMH = 5;
const HIZ_ASIM_ARDISIK = 3;
const HIZ_UYARI_ARALIK_MS = 45000;
const SON_YER_MAKS = 6;
/** Varis paylasiminda konum en sik bu araliklarla gonderilir. */
const PAYLASIM_ARALIK_MS = 4000;
const KOYU_KATMAN = KATMANLAR.find((k) => k.kod === 'v-dark');
const ACIK_KATMAN = KATMANLAR.find((k) => k.kod === 'v-light');

/** Konum bu kadar metreden uzak ve ardisik bu kadar olcumde rota disindaysa yeniden rota istenir. */
const SAPMA_ESIK_M = 35;
const SAPMA_ARDISIK = 3;
const YENIDEN_ROTA_ARALIK_MS = 10000;
const VARIS_ESIK_M = 20;
/** Baslangic rota basindan bu kadar uzaksa Baslat'ta rota guncel konumdan yeniden hesaplanir. */
const BASLANGIC_FARK_M = 80;

const TUR_ETIKET = {
  il: 'İl', ilce: 'İlçe', mahalle_koy: 'Mahalle / Köy', sehir: 'Şehir merkezi', kasaba: 'Kasaba',
  koy: 'Köy merkezi', mezra: 'Mezra', semt: 'Semt', sokak: 'Sokak', kapi: 'Kapı no', yer: 'Yer',
};

const HATA_METNI = {
  400: 'Bu iki nokta arasında rota bulunamadı.',
  401: 'Harita anahtarı geçersiz veya eksik.',
  403: 'Bu servis için izniniz yok.',
  404: 'Sonuç bulunamadı.',
  422: 'Girilen değer geçersiz.',
  429: 'İstek sınırı aşıldı, biraz bekleyin.',
  502: 'Servis şu an yanıt vermiyor.',
  503: 'Servis hazır değil.',
};

const BOS = { type: 'FeatureCollection', features: [] };

const durum = {
  api: VARSAYILAN_API,
  anahtar: '',
  sunucuAnahtar: '',
  yap: null,
  katmanKod: 'oto',
  mtAnahtar: '',
  profil: 'araba',
  ses: true,
  tercih: { otoyol: false, ucret: false },
  alternatifler: [],
  secilenAlt: 0,
  ilerleme: 0,
  yolTarifiAcik: false,
  paylasim: null,
  yoldaTur: null,
  yolda: [],
  hizAsimSayac: 0,
  sonHizUyari: 0,
  simAcik: false,
  simHiz: 50,
  konum: null,
  hedef: null,
  duraklar: [],
  gecilenDurak: 0,
  durakEkle: false,
  rota: null,
  rotaSayac: 0,
  mod: 'plan',
  takip: true,
  sapmaSayac: 0,
  sonYenidenRota: 0,
  yenidenRotaSuruyor: false,
  soylenen: new Map(),
  sonManevra: -1,
  sonYon: null,
  izleme: null,
  ekranKilidi: null,
  ilkKonum: true,
  cizim: { yolda: BOS, 'rota-alt-0': BOS, 'rota-alt-1': BOS, 'rota-tum': BOS, 'rota-kalan': BOS, hedef: BOS, 'manevra-nokta': BOS, uyari: BOS },
};
const simDurum = { d: 0, sapma: 0, sapmaAdim: 0, zamanlayici: null };
let harita = null;
let konumIsareti = null;
let isaretEkli = false;
let aramaSirasi = 0;

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

/** Ekranda gosterilecek mesafe: yakinda 5-10 m adimla, uzakta km. */
function mesafeYaz(m) {
  if (m >= 10000) return `${sayi(m / 1000)} km`;
  if (m >= 1000) return `${sayi(m / 1000, 1)} km`;
  if (m >= 100) return `${sayi(Math.round(m / 10) * 10)} m`;
  return `${sayi(Math.max(0, Math.round(m / 5) * 5))} m`;
}

/** Sesli okunacak mesafe: 50 m adim ya da 0,1 km. */
function sesliMesafe(m) {
  // 975 m ve ustu "1 kilometre" okunur ("1.000 metre" yerine)
  if (m < 975) return `${sayi(Math.max(50, Math.round(m / 50) * 50))} metre`;
  return `${sayi(Math.round(m / 100) / 10, m >= 10000 ? 0 : 1)} kilometre`;
}

function sureYaz(sn) {
  const dk = Math.max(0, Math.round(sn / 60));
  if (dk < 60) return `${sayi(dk)} dk`;
  return `${sayi(Math.floor(dk / 60))} sa ${sayi(dk % 60)} dk`;
}

/** GG.AA.YYYY SS:DD */
function tarihSaatYaz(tarih) {
  return `${tarih.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' })} ${saatYaz(tarih)}`;
}

function saatYaz(tarih) {
  return tarih.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function planMesaj(metin, tur = '') {
  const kutu = $('plan-mesaj');
  kutu.textContent = metin;
  kutu.className = `mesaj ${tur}`.trim();
}

function depoOku(ad) {
  try {
    return JSON.parse(localStorage.getItem(ad) || '{}');
  } catch (hata) {
    console.warn('Kayıtlı ayarlar okunamadı', ad, hata);
    return {};
  }
}

function depoYaz(ad, veri) {
  try {
    localStorage.setItem(ad, JSON.stringify({ ...depoOku(ad), ...veri }));
  } catch (hata) {
    console.warn('Ayarlar kaydedilemedi', ad, hata);
  }
}

function ayarKaydet() {
  depoYaz(NAV_DEPO, { katmanKod: durum.katmanKod, profil: durum.profil, ses: durum.ses, simAcik: durum.simAcik, simHiz: durum.simHiz, tercih: durum.tercih });
}

const anahtarTemizle = (deger) => String(deger || '').replace(/['"\s]/g, '');

/** Verilen adaylardan ilk gecerli (yeterince uzun) anahtari dondurur; kisa deger tarayici otomatik doldurmasindan kalmadir. */
function ilkGecerliAnahtar(...adaylar) {
  for (const aday of adaylar) {
    const temiz = anahtarTemizle(aday);
    if (temiz.length >= ANAHTAR_EN_AZ) return temiz;
  }
  return '';
}

function gecikmeli(islev, ms) {
  let zamanlayici;
  return (...args) => {
    clearTimeout(zamanlayici);
    zamanlayici = setTimeout(() => islev(...args), ms);
  };
}

/** Kullaniciya gosterilecek sade hata; kod, varsa HTTP durum kodudur. */
class HataMesaji extends Error {
  constructor(mesaj, kod = 0) {
    super(mesaj);
    this.kod = kod;
  }
}

/** HARITA API cagrisi. Kayitli anahtar gecersizse bir kez sunucu anahtariyla yeniden dener. */
async function api(yol, secenek = {}, tekrar = true) {
  if (!durum.anahtar) throw new HataMesaji('Harita anahtarı yok. Önce harita denemesi sayfasında bağlanın.');
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
  if (yanit.status === 401 && tekrar && durum.sunucuAnahtar && durum.sunucuAnahtar !== durum.anahtar) {
    console.warn('Kayıtlı harita anahtarı geçersiz, sunucu anahtarı deneniyor');
    durum.anahtar = durum.sunucuAnahtar;
    return api(yol, secenek, false);
  }
  if (!yanit.ok) {
    console.warn('API hata kodu', yanit.status, yol);
    throw new HataMesaji(HATA_METNI[yanit.status] || 'Beklenmeyen bir hata oluştu.', yanit.status);
  }
  return yanit.json();
}

/* ---------- Geometri ---------- */

const rad = (d) => (d * Math.PI) / 180;
const der = (r) => (r * 180) / Math.PI;

/** Iki nokta ([boylam, enlem]) arasi metre (haversine). */
function mesafeM(a, b) {
  const dEnlem = rad(b[1] - a[1]);
  const dBoylam = rad(b[0] - a[0]);
  const s = Math.sin(dEnlem / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dBoylam / 2) ** 2;
  return 2 * DUNYA_R * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** a'dan b'ye pusula yonu (0-360, kuzey 0). */
function yonAcisi(a, b) {
  const y = Math.sin(rad(b[0] - a[0])) * Math.cos(rad(b[1]));
  const x = Math.cos(rad(a[1])) * Math.sin(rad(b[1])) - Math.sin(rad(a[1])) * Math.cos(rad(b[1])) * Math.cos(rad(b[0] - a[0]));
  return (der(Math.atan2(y, x)) + 360) % 360;
}

/** p noktasini verilen yonde m metre tasir. */
function kaydir(p, yon, m) {
  const d = m / DUNYA_R;
  const t = rad(yon);
  const f1 = rad(p[1]);
  const l1 = rad(p[0]);
  const f2 = Math.asin(Math.sin(f1) * Math.cos(d) + Math.cos(f1) * Math.sin(d) * Math.cos(t));
  const l2 = l1 + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(f1), Math.cos(d) - Math.sin(f1) * Math.sin(f2));
  return [der(l2), der(f2)];
}

/** p noktasinin AB parcasina izdusumu: t (0-1, parca uzerindeki oran) ve metre cinsinden uzaklik. */
function parcayaIzdusum(p, a, b) {
  const kx = Math.cos(rad(p[1])) * DUNYA_R * (Math.PI / 180);
  const ky = DUNYA_R * (Math.PI / 180);
  const ax = (a[0] - p[0]) * kx;
  const ay = (a[1] - p[1]) * ky;
  const dx = (b[0] - a[0]) * kx;
  const dy = (b[1] - a[1]) * ky;
  const uz2 = dx * dx + dy * dy;
  const t = uz2 > 0 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / uz2)) : 0;
  return { t, uzaklik: Math.hypot(ax + t * dx, ay + t * dy) };
}

/** Kodlanmis polyline'i [boylam, enlem] listesine cevirir (Valhalla: hassasiyet 6). */
function polylineCoz(metin, hassasiyet = 6) {
  const carpan = 10 ** hassasiyet;
  const sonuc = [];
  let indeks = 0;
  let enlem = 0;
  let boylam = 0;
  while (indeks < metin.length) {
    for (const hedef of ['enlem', 'boylam']) {
      let deger = 0;
      let kaydirma = 0;
      let bayt;
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

const cizgi = (koordinatlar) => (koordinatlar.length >= 2
  ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: koordinatlar }, properties: {} }] }
  : BOS);
const nokta = (p) => ({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: {} }] });

/* ---------- Rota ---------- */

/**
 * Valhalla yanitini navigasyonun kullanacagi bicime cevirir: cok duraklı rotada bacaklar tek cizgide birlesir,
 * manevra konumlari kaydirilir; bacakSonM her duragin rota uzerindeki mesafesidir.
 */
function rotaHazirla(v, ilkDurak = 0) {
  const koord = [];
  const manevralar = [];
  const bacakSonIndeks = [];
  for (const bacak of v.trip.legs) {
    const parca = polylineCoz(bacak.shape, 6);
    // Sonraki bacagin ilk noktasi oncekinin son noktasidir; tekrar eklenmez
    const kayma = koord.length ? koord.length - 1 : 0;
    koord.push(...(koord.length ? parca.slice(1) : parca));
    for (const m of bacak.maneuvers) {
      manevralar.push({ ...m, begin_shape_index: m.begin_shape_index + kayma, end_shape_index: m.end_shape_index + kayma });
    }
    bacakSonIndeks.push(koord.length - 1);
  }
  const kum = [0];
  for (let i = 1; i < koord.length; i++) kum.push(kum[i - 1] + mesafeM(koord[i - 1], koord[i]));
  const son = kum[kum.length - 1] || 0;
  return {
    koord, kum, toplam: son, sure: v.trip.summary.time, segman: 0, no: 0, ilkDurak,
    bacakSonM: bacakSonIndeks.map((i) => kum[i] ?? son),
    manevralar: manevralar.map((m) => ({ ...m, basM: kum[m.begin_shape_index] ?? 0, sonM: kum[m.end_shape_index] ?? son })),
  };
}

/**
 * Baslangictan sirayla duraklara rota ister. Baslangicta yon varsa Valhalla aracin gittigi yondeki yolu secer.
 * alternatifIste: tek hedefte (ara nokta yok) 2 alternatif rota da istenir; rota.alternatifler icinde gelir.
 */
async function rotaIste(baslangic, duraklar, ilkDurak = 0, alternatifIste = false) {
  const bas = { lat: baslangic.lat, lon: baslangic.lon };
  if (Number.isFinite(baslangic.yon) && (baslangic.hiz ?? 0) > 2) Object.assign(bas, { heading: Math.round(baslangic.yon), heading_tolerance: 60 });
  const costing = COSTING[durum.profil];
  const tercih = {};
  if (durum.profil !== 'yaya') {
    if (durum.tercih.otoyol) tercih.use_highways = 0;
    if (durum.tercih.ucret) tercih.use_tolls = 0;
  }
  const tekHedef = duraklar.length === 1 && !(duraklar[0].ara || []).length;
  const govde = {
    // Ara (gecis) noktalari: GPX izinin yollarindan gecmek icin; "through" bacak bolmez, duraga ulasildi denmez
    locations: [bas, ...duraklar.flatMap((d) => [...(d.ara || []).map((a) => ({ lat: a.lat, lon: a.lon, type: 'through' })),
      { lat: d.lat, lon: d.lon }])],
    costing,
    directions_options: { language: 'tr-TR', units: 'kilometers' },
  };
  if (Object.keys(tercih).length) govde.costing_options = { [costing]: tercih };
  if (alternatifIste && tekHedef) govde.alternates = 2;
  const v = await api('/valhalla/route', { method: 'POST', body: JSON.stringify(govde) });
  const rota = rotaHazirla(v, ilkDurak);
  // Cok uzun dolambacli alternatifler elenir
  rota.alternatifler = (alternatifIste && tekHedef ? v.alternates || [] : []).map((alt) => rotaHazirla(alt, ilkDurak))
    .filter((alt) => alt.sure <= rota.sure * 1.8);
  return rota;
}

/** Henuz ulasilmamis duraklar (yeniden rota ve baslangic icin). */
function kalanDuraklar(konum = null) {
  const kalan = durum.duraklar.slice(durum.gecilenDurak);
  const ilk = kalan[0];
  if (!konum || !ilk?.ara?.length) return kalan;
  // Yeniden rotada gecilmis ara noktalara geri donulmez: konuma en yakin ara noktadan sonrakiler tutulur
  const p = [konum.lon, konum.lat];
  let en = 0;
  ilk.ara.forEach((a, i) => { if (mesafeM(p, [a.lon, a.lat]) < mesafeM(p, [ilk.ara[en].lon, ilk.ara[en].lat])) en = i; });
  const yakin = mesafeM(p, [ilk.ara[en].lon, ilk.ara[en].lat]) < 150;
  return [{ ...ilk, ara: ilk.ara.slice(en + (yakin ? 1 : 0)) }, ...kalan.slice(1)];
}

/** Duraklari haritaya numarali isaret olarak cizer (son durak hedef rengiyle). */
function duraklariCiz() {
  veriYaz('hedef', {
    type: 'FeatureCollection',
    features: durum.duraklar.map((d, i) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: [d.lon, d.lat] },
      properties: { no: String(i + 1), son: i === durum.duraklar.length - 1, gecildi: i < durum.gecilenDurak },
    })),
  });
}

/** Yeni rotayi etkin yapar ve haritaya cizer. */
function rotaAyarla(rota) {
  durum.rotaSayac += 1;
  rota.no = durum.rotaSayac;
  durum.rota = rota;
  durum.soylenen.clear();
  durum.sonManevra = -1;
  veriYaz('rota-tum', cizgi(rota.koord));
  veriYaz('rota-kalan', cizgi(rota.koord));
  veriYaz('manevra-nokta', BOS);
  veriYaz('uyari', BOS);
  yoldaTemizle();
  uyarilariGetir(rota);
}

/** Rota boyunca gonderilecek en fazla nokta (uzun rotada aradaki noktalar seyreltilir). */
const UYARI_MAKS_NOKTA = 20000;

/**
 * Rota boyunca hiz kamerasi ve hiz kesicileri getirir (rota_m: rota basindan uzaklik) ve haritaya cizer.
 * Hata olursa navigasyon uyarisiz devam eder.
 */
async function uyarilariGetir(rota) {
  const adim = Math.ceil(rota.koord.length / UYARI_MAKS_NOKTA);
  const noktalar = rota.koord.filter((_, i) => i % adim === 0 || i === rota.koord.length - 1).map(([lon, lat]) => [lat, lon]);
  try {
    const v = await api('/v1/yol/uyarilar', { method: 'POST', body: JSON.stringify({ noktalar, tampon_m: 25 }) });
    if (durum.rota !== rota) return;
    rota.uyarilar = v.uyarilar || [];
    rota.uyariSoylendi = new Set();
    veriYaz('uyari', {
      type: 'FeatureCollection',
      features: rota.uyarilar.map((u) => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: [u.lon, u.lat] },
        properties: { kamera: u.tur === 'hiz_kamerasi', hiz: u.hiz_siniri_kmh ? String(u.hiz_siniri_kmh) : '' },
      })),
    });
  } catch (hata) {
    console.warn('Yol uyarıları alınamadı', hata);
  }
}

/** Ondeki hiz kamerasi (hiza gore 300-700 m) ve hiz kesici (120-250 m) icin bir kez sesli uyari. */
function sesliUyarilar(rota, ilerleme, hizMs) {
  if (!rota.uyarilar?.length || durum.profil === 'yaya') return;
  const v = Math.max(hizMs || 0, 8);
  for (const u of rota.uyarilar) {
    const kalan = u.rota_m - ilerleme;
    if (kalan < -20) continue;
    const kamera = u.tur === 'hiz_kamerasi';
    const esik = kamera ? Math.min(700, Math.max(300, v * 25)) : Math.min(250, Math.max(120, v * 10));
    if (kalan > 700) break;
    if (kalan > esik) continue;
    if (rota.uyariSoylendi.has(u.id) || kalan < 0) continue;
    rota.uyariSoylendi.add(u.id);
    soyle(kamera
      ? `${sesliMesafe(kalan)} sonra hız kamerası${u.hiz_siniri_kmh ? `, hız sınırı ${u.hiz_siniri_kmh}` : ''}.`
      : 'Dikkat, ileride hız kesici var.');
  }
}

/** Son bilinen parcadan sonra bu kadar metrelik rota parcasinda eslesme aranir. */
const ESLESME_PENCERE_M = 1500;

/**
 * Konumu rotaya oturtur: en yakin parca, rota uzerindeki nokta, baslangictan ilerleme ve rotaya uzaklik.
 * Yalniz son bilinen parcanin biraz gerisinden ileriye bakilir; boylece rotadan sapinca rotanin
 * yakindaki baska bir bolumune (donus yolu, paralel sokak) atlanmaz ve sapma dogru algilanir.
 */
function rotayaOturt(rota, p) {
  const n = rota.koord.length;
  if (n < 2) return null;
  const bas = Math.max(0, rota.segman - 2);
  let son = bas + 1;
  while (son < n - 1 && rota.kum[son] - rota.kum[rota.segman] < ESLESME_PENCERE_M) son++;
  let en = null;
  for (let i = bas; i < son; i++) {
    const iz = parcayaIzdusum(p, rota.koord[i], rota.koord[i + 1]);
    if (!en || iz.uzaklik < en.uzaklik) en = { i, ...iz };
  }
  const a = rota.koord[en.i];
  const b = rota.koord[en.i + 1];
  return {
    segman: en.i,
    nokta: [a[0] + (b[0] - a[0]) * en.t, a[1] + (b[1] - a[1]) * en.t],
    ilerleme: rota.kum[en.i] + (rota.kum[en.i + 1] - rota.kum[en.i]) * en.t,
    uzaklik: en.uzaklik,
    yon: yonAcisi(a, b),
  };
}

/** Rota uzerinde baslangictan d metre sonraki nokta ve oradaki yon (simulasyon icin). */
function rotaUzerindeNokta(rota, d) {
  const { koord, kum } = rota;
  if (koord.length < 2) return { nokta: koord[0], yon: 0 };
  let alt = 0;
  let ust = kum.length - 1;
  while (ust - alt > 1) {
    const orta = (alt + ust) >> 1;
    if (kum[orta] <= d) alt = orta; else ust = orta;
  }
  const a = koord[alt];
  const b = koord[alt + 1];
  const uz = kum[alt + 1] - kum[alt];
  const t = uz > 0 ? Math.min(1, Math.max(0, (d - kum[alt]) / uz)) : 0;
  return { nokta: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], yon: yonAcisi(a, b) };
}

/** Ilerlemeden sonraki ilk manevra (0. manevra yola cikistir, atlanir). */
function siradakiManevra(rota, ilerleme) {
  const m = rota.manevralar;
  for (let i = 1; i < m.length; i++) if (m[i].basM > ilerleme + 3) return i;
  return m.length - 1;
}

/** Kalan sure: icinde bulunulan manevranin kalan payi + sonraki manevralarin Valhalla sureleri. */
function kalanSure(rota, ilerleme) {
  let toplam = 0;
  for (const m of rota.manevralar) {
    if (m.sonM <= ilerleme) continue;
    if (m.basM >= ilerleme) toplam += m.time;
    else {
      const uz = m.sonM - m.basM;
      toplam += uz > 0 ? (m.time * (m.sonM - ilerleme)) / uz : 0;
    }
  }
  return toplam;
}

/* ---------- Ses ---------- */

function turkceSes() {
  if (!('speechSynthesis' in window)) return null;
  return speechSynthesis.getVoices().find((v) => (v.lang || '').toLowerCase().startsWith('tr')) || null;
}

/** Metni Turkce okur; oncelikliyse sirada bekleyen konusmalari keser. */
/*
 * Valhalla'nin Turkce sablonu her yol adinin arkasina "caddesine / caddesinde ..." ekler; ad zaten yol turuyle bitince
 * "Cumhuriyet Caddesi caddesine" gibi tekrar olusur. Bu durumda genel kelime atilir ve ek, ada ses uyumuyla baglanir:
 * "Cumhuriyet Caddesi'ne", "Utangac Sokagi'nda", "Ataturk Bulvari'ndan", "Gul Sokak'a", "Istiklal Cadde'ye".
 */
// Iyelik ekiyle biten yol turleri: ek "n" kaynastirmasiyla gelir (Caddesi'ne)
const IYELIKLI_YOL = ['caddesi', 'sokağı', 'sokaği', 'bulvarı', 'yolu', 'otoyolu', 'çevreyolu', 'meydanı', 'köprüsü', 'geçidi',
  'tüneli', 'viyadüğü', 'kavşağı', 'çıkmazı', 'yokuşu', 'parkı', 'çarşısı', 'sahili', 'kordonu', 'sokakları', 'caddeleri', 'rampası'];
// Yalin yol turleri ve kisaltmalar (kisaltma okunusu: Cd. -> Cadde, Sk. -> Sokak)
const YALIN_YOL = { cadde: 'cadde', sokak: 'sokak', bulvar: 'bulvar', yol: 'yol', otoyol: 'otoyol', meydan: 'meydan', köprü: 'köprü',
  geçit: 'geçit', tünel: 'tünel', viyadük: 'viyadük', kavşak: 'kavşak', çıkmaz: 'çıkmaz', yokuş: 'yokuş', 'cd.': 'cadde', 'cad.': 'cadde',
  'sk.': 'sokak', 'sok.': 'sokak', 'blv.': 'bulvar', 'bulv.': 'bulvar' };
// Yalniz yol turu kelimesinin hemen ardindan gelen genel kelime eslenir ("Cumhuriyet Caddesi" tek basina eslenmez)
const YOL_TURU_DESENI = [...IYELIKLI_YOL, ...Object.keys(YALIN_YOL)]
  .sort((a, b) => b.length - a.length).map((k) => k.replace(/\./g, '\\.')).join('|');
// Valhalla'nin ekledigi genel kelime hep kucuk harfle gelir ("caddesine"); adin kendi parcasi buyuk harfle baslar
// ("Ankara Yolu Caddesi"). Bu yuzden genel kelime buyuk / kucuk harfe duyarli eslenir, yol turu duyarsiz.
const YOL_TURU_DUYARSIZ = YOL_TURU_DESENI.replace(/\p{L}/gu, (h) => `[${h}${h.toLocaleUpperCase('tr-TR')}]`);
const GENEL_CADDE = new RegExp(`(?<=^|[\\s/])(${YOL_TURU_DUYARSIZ})\\s+cadde(si|sine|sinde|sinden|sini)(?=[\\s.,;:!?)]|$)`, 'gu');

function sesliEk(kelime, hal, iyelikli) {
  const unluler = [...kelime].filter((h) => 'aıoueiöü'.includes(h));
  const son = unluler.at(-1) || 'e';
  const kalin = 'aıou'.includes(son);
  const unluyleBiter = 'aıoueiöü'.includes(kelime.at(-1));
  const sert = 'fstkçşhp'.includes(kelime.at(-1));
  const a = kalin ? 'a' : 'e';
  const dortlu = { a: 'ı', ı: 'ı', o: 'u', u: 'u', e: 'i', i: 'i', ö: 'ü', ü: 'ü' }[son];
  if (hal === 'sine') return iyelikli ? `n${a}` : unluyleBiter ? `y${a}` : a;
  if (hal === 'sinde') return iyelikli ? `nd${a}` : `${sert ? 't' : 'd'}${a}`;
  if (hal === 'sinden') return iyelikli ? `nd${a}n` : `${sert ? 't' : 'd'}${a}n`;
  if (hal === 'sini') return iyelikli ? `n${dortlu}` : unluyleBiter ? `y${dortlu}` : dortlu;
  return '';
}

// Yol numaralari (D260, O-4, E80): "caddesine" yerine "yoluna"
const YOL_NUMARASI = /(?<=^|[\s/])([A-ZÇĞİÖŞÜ]{1,3}[ -]?\d{1,4}[A-Z]?)\s+cadde(si|sine|sinde|sinden|sini)(?=[\s.,;:!?)]|$)/gu;
const YOL_NUMARASI_EKI = { si: 'yolu', sine: 'yoluna', sinde: 'yolunda', sinden: 'yolundan', sini: 'yolunu' };
// Sira sayilari cumle ortasinda kucuk harfle ("ve İkinci çıkıştan" -> "ve ikinci çıkıştan")
const SIRA_SAYISI = /(?<=[^.!?]\s)(Birinci|İkinci|Üçüncü|Dördüncü|Beşinci|Altıncı|Yedinci|Sekizinci|Dokuzuncu|Onuncu)(?=\s)/gu;

/**
 * Valhalla Turkce talimat metnini duzeltir: "X Caddesi caddesine" -> "X Caddesi'ne", "D260 caddesine" -> "D260 yoluna",
 * bitisik "veİkinci" -> "ve ikinci". Yol turu olmayan adlara ve isaret metinlerine dokunmaz.
 */
function yolAdiDuzelt(metin) {
  if (!metin) return metin;
  return metin
    .replace(/(?<=\s|^)ve(?=[A-ZÇĞİÖŞÜ])/gu, 've ')
    .replace(GENEL_CADDE, (tam, onceki, hal) => {
      const kucuk = onceki.toLocaleLowerCase('tr-TR');
      const iyelikli = IYELIKLI_YOL.includes(kucuk);
      const yalin = YALIN_YOL[kucuk];
      if (!iyelikli && !yalin) return tam;
      const ek = sesliEk(iyelikli ? kucuk : yalin, hal.toLocaleLowerCase('tr-TR'), iyelikli);
      return ek ? `${onceki}'${ek}` : onceki;
    })
    .replace(YOL_NUMARASI, (tam, numara, hal) => `${numara} ${YOL_NUMARASI_EKI[hal.toLocaleLowerCase('tr-TR')]}`)
    .replace(SIRA_SAYISI, (sira) => sira.toLocaleLowerCase('tr-TR'));
}

function soyle(metin, oncelikli = false) {
  if (!durum.ses || !metin || !('speechSynthesis' in window)) return;
  // Valhalla Turkce metinlerinde sayi ile birim bitisik gelebiliyor ("2kilometre"); okunurken ayrilir
  const duzgun = yolAdiDuzelt(metin).replace(/(\d)([a-zçğıöşü])/gi, '$1 $2');
  const oku = () => {
    const konusma = new SpeechSynthesisUtterance(duzgun);
    konusma.lang = 'tr-TR';
    const ses = turkceSes();
    if (ses) konusma.voice = ses;
    konusma.onerror = (olay) => sesHatasi(olay.error);
    speechSynthesis.resume();
    speechSynthesis.speak(konusma);
  };
  // Android Chrome'da cancel()'dan hemen sonra speak() cumleyi yutabilir: kisa beklenir
  if (oncelikli && (speechSynthesis.speaking || speechSynthesis.pending)) {
    speechSynthesis.cancel();
    setTimeout(oku, 150);
  } else oku();
}

let sesAcildi = false;

/**
 * Mobil tarayicilar sesli okumayi yalniz kullanici dokunusuyla baslatir (iPhone'da ilk konusma dokunusun icinde olmali).
 * Ilk dokunusta sessiz, bos bir cumle okutarak ses motoru uyandirilir.
 */
function sesiAc() {
  if (sesAcildi || !('speechSynthesis' in window)) return;
  sesAcildi = true;
  try {
    speechSynthesis.resume();
    const bos = new SpeechSynthesisUtterance(' ');
    bos.volume = 0;
    speechSynthesis.speak(bos);
  } catch (hata) {
    console.warn('Ses motoru uyandırılamadı', hata);
  }
}

/** Ses hatasini kullaniciya anlasilir bildirir (30 sn'de bir); kesilme / iptal hatalari bizim kendi kesmemizdir, bildirilmez. */
function sesHatasi(kod) {
  console.warn('Sesli okuma hatası', kod);
  if (['interrupted', 'canceled'].includes(kod) || Date.now() - (sesHatasi.son || 0) < 30000) return;
  sesHatasi.son = Date.now();
  const metin = {
    'not-allowed': 'Tarayıcı sesi engelledi: sayfaya bir kez dokunun ve "Sesi dene"yi kullanın.',
    'synthesis-failed': 'Telefonun konuşma motoru çalışmadı. Ayarlar > Erişilebilirlik > Metni sese (Google) bölümünü kontrol edin.',
    'synthesis-unavailable': 'Telefonda sesli okuma motoru yok. Ayarlar > Erişilebilirlik > Metni sese bölümünü kontrol edin.',
    'language-unavailable': 'Telefonda Türkçe ses yüklü değil. Metni sese ayarlarından Türkçe sesi indirin.',
    'voice-unavailable': 'Seçilen ses kullanılamıyor. Metni sese ayarlarından Türkçe sesi indirin.',
    network: 'Bu ses internet gerektiriyor; bağlantınızı kontrol edin.',
  }[kod] || `Sesli okuma hatası: ${kod}`;
  bildir(metin);
}

/** Menudeki "Sesi dene": test cumlesini okutur ve hangi sesin secildigini yazar. */
function sesiDene() {
  const bilgi = $('ses-bilgi');
  if (!('speechSynthesis' in window)) {
    bilgi.textContent = 'Bu tarayıcı sesli okumayı desteklemiyor.';
    bilgi.className = 'mesaj hata';
    return;
  }
  if (!durum.ses) {
    durum.ses = true;
    ayarKaydet();
    arayuzGuncelle();
  }
  sesAcildi = false;
  sesiAc();
  const ses = turkceSes();
  const sesSayisi = speechSynthesis.getVoices().length;
  bilgi.textContent = ses ? `Türkçe ses: ${ses.name}` : `Türkçe ses bulunamadı (${sesSayisi} ses var); varsayılan ses denenecek.`;
  bilgi.className = `mesaj ${ses ? 'basari' : 'uyari'}`;
  soyle('Sesli yönlendirme çalışıyor.', true);
}

/** Siradaki manevra icin uzak ve yakin anonslari bir kez yapar; esikler hiza gore buyur. */
function sesliYonlendir(rota, i, kalanM, hizMs) {
  const m = rota.manevralar[i];
  const anahtar = `${rota.no}:${i}`;
  const soylenen = durum.soylenen.get(anahtar) || {};
  const yaya = durum.profil === 'yaya';
  const v = Math.max(hizMs || 0, yaya ? 1.4 : 8);
  const uzak = yaya ? 120 : Math.min(1500, Math.max(250, v * 30));
  const yakin = yaya ? 25 : Math.min(220, Math.max(45, v * 7));
  if (!soylenen.yakin && kalanM <= yakin) {
    soylenen.yakin = true;
    soylenen.uzak = true;
    soyle(m.verbal_pre_transition_instruction || m.instruction, true);
  } else if (!soylenen.uzak && kalanM <= uzak && kalanM > yakin * 1.6) {
    soylenen.uzak = true;
    soyle(`${sesliMesafe(kalanM)} sonra, ${m.verbal_transition_alert_instruction || m.instruction}`);
  }
  durum.soylenen.set(anahtar, soylenen);
}

/* ---------- Harita ---------- */

function varsayilanYapilandirma() {
  return {
    karo: { adres: `${VARSAYILAN_KARO}/tiles/turkiye/{z}/{x}/{y}.mvt`, maksYakinlastirma: 15 },
    yaziTipleri: `${VARSAYILAN_KARO}/assets/fonts/{fontstack}/{range}.pbf`,
    simgeler: `${VARSAYILAN_KARO}/assets/sprites/v4`,
    atif: '© OpenStreetMap katkıcıları, Protomaps',
  };
}

/**
 * Verilen anda ve konumda gunes ufkun ustunde mi (gun dogumu / batimi yaklasimi, +-birkac dakika). Konum verilmezse
 * cihaz konumu, yoksa harita merkezi kullanilir. Kutup bolgelerinde gun / gece sabittir.
 */
function gunduzMu(tarih = new Date(), konum = null) {
  const c = konum || (durum.konum ? { lat: durum.konum.lat, lon: durum.konum.lon }
    : harita ? { lat: harita.getCenter().lat, lon: harita.getCenter().lng } : { lat: 39, lon: 35 });
  const rad = Math.PI / 180;
  const yilGunu = Math.floor((Date.UTC(tarih.getUTCFullYear(), tarih.getUTCMonth(), tarih.getUTCDate()) - Date.UTC(tarih.getUTCFullYear(), 0, 0)) / 86400000);
  const b = (2 * Math.PI * (yilGunu - 81)) / 364;
  const zamanDenklemiDk = 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);
  const sapma = 23.45 * rad * Math.sin((2 * Math.PI * (284 + yilGunu)) / 365);
  const cosH = (Math.sin(-0.833 * rad) - Math.sin(c.lat * rad) * Math.sin(sapma)) / (Math.cos(c.lat * rad) * Math.cos(sapma));
  if (cosH >= 1) return false;
  if (cosH <= -1) return true;
  const yarimGunDk = (Math.acos(cosH) / rad) * 4;
  const ogleDk = 720 - 4 * c.lon - zamanDenklemiDk;
  const simdiDk = tarih.getUTCHours() * 60 + tarih.getUTCMinutes();
  const fark = ((((simdiDk - ogleDk + 720) % 1440) + 1440) % 1440) - 720;
  return Math.abs(fark) <= yarimGunDk;
}

/** Secili katman ("oto" gunduz acik, gece koyu sokak katmani olur); MapTiler anahtari yoksa MapTiler katmanlari yerine koyu sokak katmani kullanilir. */
function aktifKatman() {
  if (durum.katmanKod === 'oto') return gunduzMu() ? ACIK_KATMAN : KOYU_KATMAN;
  const k = KATMANLAR.find((x) => x.kod === durum.katmanKod) || KOYU_KATMAN;
  return k.tur !== 'vektor' && !durum.mtAnahtar ? KOYU_KATMAN : k;
}

function mtAdres(k) {
  return `https://api.maptiler.com/maps/${k.harita}/{z}/{x}/{y}.${k.uzanti}?key=${encodeURIComponent(durum.mtAnahtar)}`;
}

/** Karma katman: uydu uzerinde okunur olsun diye yollar acik renk, yazilar beyaz ve koyu konturlu. */
function karmaKatmanlari() {
  const tum = layers('harita', namedFlavor('dark'), { lang: 'tr' });
  const cizgiler = tum
    .filter((l) => l.type === 'line' && ['roads', 'boundaries'].includes(l['source-layer']) && !/casing|tunnel_|bridges_/.test(l.id))
    .map((l) => ({
      ...l,
      paint: { ...l.paint, 'line-color': l['source-layer'] === 'boundaries' ? '#FFD166' : '#FFFFFF', 'line-opacity': /roads_(other|minor_service|link)/.test(l.id) ? 0.3 : 0.8 },
    }));
  const yazilar = tum.filter((l) => l.type === 'symbol').map((l) => ({
    ...l,
    paint: { ...l.paint, 'text-color': '#FFFFFF', 'text-halo-color': 'rgba(0,0,0,0.85)', 'text-halo-width': 1.6, 'text-halo-blur': 0.5 },
  }));
  return [...cizgiler, ...yazilar];
}

function stilKur() {
  const yap = durum.yap;
  const k = aktifKatman();
  const kaynaklar = { harita: { type: 'vector', tiles: [yap.karo.adres], maxzoom: yap.karo.maksYakinlastirma, attribution: yap.atif } };
  let katmanlar;
  let sprite = 'dark';
  if (k.tur === 'vektor') {
    sprite = k.tema;
    katmanlar = layers('harita', namedFlavor(k.tema), { lang: 'tr' });
  } else {
    kaynaklar.zemin = { type: 'raster', tiles: [mtAdres(k)], tileSize: 512, maxzoom: 20, attribution: MT_ATIF };
    katmanlar = [{ id: 'zemin', type: 'raster', source: 'zemin' }];
    if (k.tur === 'karma') katmanlar.push(...karmaKatmanlari());
  }
  return { version: 8, glyphs: yap.yaziTipleri, sprite: `${yap.simgeler}/${sprite}`, sources: kaynaklar, layers: katmanlar };
}

/** Arayuz rengi katmana uyar: acik sokak katmanlarinda acik tema, digerlerinde koyu. */
function temaUygula() {
  const acik = Boolean(aktifKatman().acik);
  if (acik) document.documentElement.dataset.theme = 'light';
  else delete document.documentElement.dataset.theme;
  document.querySelector('meta[name="theme-color"]').setAttribute('content', acik ? '#F6F8FA' : '#0E1116');
}

function katmanSecimiDoldur() {
  const sec = $('katman');
  sec.replaceChildren();
  const gruplar = new Map();
  for (const k of KATMANLAR) {
    if (!gruplar.has(k.grup)) gruplar.set(k.grup, el('optgroup', { label: k.grup }));
    const gerekli = k.tur !== 'vektor' && k.tur !== 'oto' && !durum.mtAnahtar;
    const secenek = el('option', { value: k.kod, metin: gerekli ? `${k.ad} (MapTiler anahtarı gerekli)` : k.ad });
    if (gerekli) secenek.disabled = true;
    gruplar.get(k.grup).append(secenek);
  }
  gruplar.forEach((g) => sec.append(g));
  sec.value = durum.katmanKod === 'oto' ? 'oto' : aktifKatman().kod;
}

/** Rota, hedef ve manevra katmanlari; stil her degistiginde yeniden eklenir. */
function kaplamaKur() {
  for (const ad of Object.keys(durum.cizim)) {
    if (!harita.getSource(ad)) harita.addSource(ad, { type: 'geojson', data: durum.cizim[ad] });
  }
  const yuvarlak = { 'line-join': 'round', 'line-cap': 'round' };
  const kat = (tanim) => { if (!harita.getLayer(tanim.id)) harita.addLayer(tanim); };
  for (const i of [0, 1]) {
    kat({ id: `rota-alt-${i}`, type: 'line', source: `rota-alt-${i}`, layout: yuvarlak,
      paint: { 'line-color': '#8FB8E8', 'line-opacity': 0.75, 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3, 18, 9] } });
  }
  kat({ id: 'rota-tum', type: 'line', source: 'rota-tum', layout: yuvarlak,
    paint: { 'line-color': '#8B949E', 'line-opacity': 0.5, 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3, 18, 10] } });
  kat({ id: 'rota-kalan-kenar', type: 'line', source: 'rota-kalan', layout: yuvarlak,
    paint: { 'line-color': '#0B2A4A', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 6, 18, 17] } });
  kat({ id: 'rota-kalan', type: 'line', source: 'rota-kalan', layout: yuvarlak,
    paint: { 'line-color': '#58A6FF', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3.5, 18, 11] } });
  kat({ id: 'manevra-nokta', type: 'circle', source: 'manevra-nokta',
    paint: { 'circle-radius': 6, 'circle-color': '#FFFFFF', 'circle-stroke-color': '#58A6FF', 'circle-stroke-width': 3 } });
  // Duraklar: son durak (hedef) kirmizi, ara duraklar turuncu, gecilenler gri; ustunde sira numarasi
  // Hiz kamerasi kirmizi, hiz kesici turuncu; kameranin hiz siniri ustunde yazar
  kat({ id: 'uyari', type: 'circle', source: 'uyari', minzoom: 11,
    paint: {
      'circle-radius': ['case', ['get', 'kamera'], 8, 5],
      'circle-color': ['case', ['get', 'kamera'], '#F85149', '#D29922'],
      'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 2,
    } });
  kat({ id: 'uyari-hiz', type: 'symbol', source: 'uyari', minzoom: 13,
    layout: { 'text-field': ['get', 'hiz'], 'text-font': ['Noto Sans Medium'], 'text-size': 9, 'text-allow-overlap': true },
    paint: { 'text-color': '#FFFFFF' } });
  kat({ id: 'yolda', type: 'circle', source: 'yolda',
    paint: { 'circle-radius': 8, 'circle-color': '#BC8CFF', 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 2 } });
  kat({ id: 'yolda-ad', type: 'symbol', source: 'yolda', minzoom: 12,
    layout: { 'text-field': ['get', 'ad'], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-offset': [0, 1.2], 'text-anchor': 'top', 'text-max-width': 8 },
    paint: { 'text-color': '#E6EDF3', 'text-halo-color': '#0E1116', 'text-halo-width': 1.5 } });
  kat({ id: 'hedef', type: 'circle', source: 'hedef',
    paint: {
      'circle-radius': ['case', ['get', 'son'], 10, 9],
      'circle-color': ['case', ['get', 'gecildi'], '#8B949E', ['get', 'son'], '#F85149', '#D29922'],
      'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 2,
    } });
  kat({ id: 'hedef-no', type: 'symbol', source: 'hedef',
    layout: { 'text-field': ['get', 'no'], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-allow-overlap': true },
    paint: { 'text-color': '#FFFFFF' } });
}

function veriYaz(ad, veri) {
  durum.cizim[ad] = veri;
  const kaynak = harita?.getSource(ad);
  if (kaynak) kaynak.setData(veri);
}

function konumIsaretiKur() {
  const kap = el('div', { sinif: 'konum-isaret', 'aria-hidden': 'true' });
  kap.innerHTML = '<svg viewBox="-17 -17 34 34"><circle class="yonsuz" r="7"></circle>'
    + '<path class="govde" d="M0 -14 L10 11 L0 5 L-10 11 Z" display="none"></path></svg>';
  konumIsareti = new maplibregl.Marker({ element: kap, rotationAlignment: 'map', pitchAlignment: 'map' });
}

/** Konum isaretini tasir; yon biliniyorsa ok, bilinmiyorsa daire gosterir. */
function konumIsaretiGuncelle(p, yon) {
  const kap = konumIsareti.getElement();
  const yonlu = Number.isFinite(yon);
  kap.querySelector('.govde').setAttribute('display', yonlu ? 'inline' : 'none');
  kap.querySelector('.yonsuz').setAttribute('display', yonlu ? 'none' : 'inline');
  konumIsareti.setLngLat(p).setRotation(yonlu ? yon : 0);
  if (!isaretEkli) {
    konumIsareti.addTo(harita);
    isaretEkli = true;
  }
}

function altYukseklik() {
  return $('alt').offsetHeight;
}

/** Navigasyonda kamera konumu takip eder; konum ekranin alt kisminda, ileri gorus genis kalir. */
function kameraGuncelle(p, yon, hizMs) {
  if (!durum.takip) return;
  const yaya = durum.profil === 'yaya';
  const v = hizMs || 0;
  const zoom = yaya ? 18 : v > 22 ? 15.4 : v > 12 ? 16.2 : 17;
  const yukseklik = harita.getContainer().clientHeight;
  harita.easeTo({
    center: p,
    bearing: yon ?? harita.getBearing(),
    pitch: 55,
    zoom,
    duration: 900,
    easing: (t) => t,
    padding: { top: Math.round(yukseklik * 0.45), bottom: altYukseklik(), left: 0, right: 0 },
  });
}

function rotayaSigdir(rota) {
  let [bati, guney, dogu, kuzey] = [180, 90, -180, -90];
  for (const [x, y] of rota.koord) {
    bati = Math.min(bati, x); dogu = Math.max(dogu, x);
    guney = Math.min(guney, y); kuzey = Math.max(kuzey, y);
  }
  const ust = $('plan').hidden ? 120 : $('plan').offsetHeight + 24;
  harita.fitBounds([[bati, guney], [dogu, kuzey]], {
    padding: { top: ust, bottom: altYukseklik() + 30, left: 30, right: 30 }, maxZoom: 17, duration: 800, bearing: 0, pitch: 0,
  });
}

/* ---------- Arayuz ---------- */

/** Moda gore kartlari ve dugmeleri gosterir: plan (hedef yok), onizleme (rota hazir), nav (yolda). */
function arayuzGuncelle() {
  const { mod } = durum;
  const nav = mod === 'nav';
  $('plan').hidden = nav;
  $('manevra').hidden = !nav;
  $('alt-ipucu').hidden = mod !== 'plan';
  $('ozet').hidden = mod === 'plan';
  $('sayfa-tutac').hidden = mod === 'plan';
  $('hiz-kutu').hidden = !nav;
  if (!nav) $('hiz-sinir').hidden = true;
  $('baslat').hidden = mod !== 'onizleme';
  $('iptal').hidden = mod !== 'onizleme';
  $('bitir').hidden = !nav;
  $('ses').hidden = !nav;
  $('ortala').hidden = !nav || durum.takip;
  $('sapma').hidden = !(nav && durum.simAcik);
  $('sim-hiz-alan').hidden = !durum.simAcik;
  $('durak-ekle').hidden = mod !== 'onizleme';
  $('ev-kaydet').hidden = mod !== 'onizleme';
  $('is-kaydet').hidden = mod !== 'onizleme';
  $('yolda').hidden = mod === 'plan';
  $('varis-paylas').hidden = !nav;
  $('varis-paylas').textContent = durum.paylasim ? 'Paylaşımı durdur' : 'Varışımı paylaş';
  $('varis-baglanti').hidden = !nav || !durum.paylasim;
  $('paylasim-rozet').hidden = !durum.paylasim;
  $('durak-ekle').textContent = durum.durakEkle ? 'Durak ekleniyor: arayın ya da dokunun' : 'Durak ekle';
  $('durak-ekle').classList.toggle('etkin', durum.durakEkle);
  $('ses').textContent = durum.ses ? 'Ses: açık' : 'Ses: kapalı';
  $('ses-onay').checked = durum.ses;
  $('tercih-bolum').hidden = durum.profil === 'yaya';
  profilGoster();
  if (mod === 'plan') sayfaAc(false);
  if (!nav) yolTarifiAc(false);
  document.documentElement.style.setProperty('--alt-yukseklik', `${altYukseklik()}px`);
}

/** Ulasim segmentini ve gizli secimi gunceller. */
function profilGoster() {
  $('profil').value = durum.profil;
  document.querySelectorAll('#profil-segment button').forEach((d) => {
    const etkin = d.dataset.profil === durum.profil;
    d.classList.toggle('etkin', etkin);
    d.setAttribute('aria-pressed', String(etkin));
  });
}

function ozetYaz(kalanSn, kalanM, hizMs) {
  $('kalan-sure').textContent = sureYaz(kalanSn);
  $('kalan-mesafe').textContent = mesafeYaz(kalanM);
  $('varis').textContent = saatYaz(new Date(Date.now() + kalanSn * 1000));
  $('hiz').textContent = Number.isFinite(hizMs) ? String(Math.round(hizMs * 3.6)) : '0';
}

/** Manevra simgesi: Valhalla'nin donus oncesi ve sonrasi yonlerinin farki kadar dondurulmus ok; varista hedef isareti. */
function simgeCiz(m) {
  const varis = [4, 5, 6].includes(m.type);
  $('simge-ok').setAttribute('display', varis ? 'none' : 'inline');
  $('simge-hedef').setAttribute('display', varis ? 'inline' : 'none');
  if (varis) return;
  let aci = 0;
  if (m.type === 12) aci = 180;
  else if (m.type === 13) aci = -180;
  else if (Number.isFinite(m.bearing_before) && Number.isFinite(m.bearing_after)) aci = ((m.bearing_after - m.bearing_before + 540) % 360) - 180;
  $('simge-ok').setAttribute('transform', `rotate(${Math.round(aci)})`);
}

/** Adi olmayan yollarda Valhalla talimati kucuk harfle baslar ("sola donun."); ekranda buyuk harfle baslatir. */
const buyukBasla = (metin) => {
  const duz = yolAdiDuzelt(metin);
  return duz ? duz.charAt(0).toLocaleUpperCase('tr-TR') + duz.slice(1) : '';
};

function manevraKartiYaz(rota, i, kalanM) {
  const m = rota.manevralar[i];
  $('manevra-mesafe').textContent = mesafeYaz(kalanM);
  $('manevra-metin').textContent = buyukBasla(m.instruction);
  simgeCiz(m);
  const sonraki = rota.manevralar[i + 1];
  const sonra = $('manevra-sonra');
  if (sonraki && sonraki.basM - m.basM < 300) {
    sonra.textContent = `Sonra: ${buyukBasla(sonraki.instruction)}`;
    sonra.hidden = false;
  } else sonra.hidden = true;
}

function manevraKartiMesaj(baslik, metin) {
  $('manevra-mesafe').textContent = baslik;
  $('manevra-metin').textContent = metin;
  $('manevra-sonra').hidden = true;
}

/* ---------- Konum ---------- */

/** Her konum olcumu (GPS ya da simulasyon) buraya gelir; navigasyonda rota, kart, ses ve kamera guncellenir. */
function konumGeldi(k) {
  const onceki = durum.konum;
  if (!Number.isFinite(k.yon) && onceki && mesafeM([onceki.lon, onceki.lat], [k.lon, k.lat]) > 3) {
    k.yon = yonAcisi([onceki.lon, onceki.lat], [k.lon, k.lat]);
  }
  if (!Number.isFinite(k.yon) && onceki && Number.isFinite(onceki.yon)) k.yon = onceki.yon;
  durum.konum = k;
  const p = [k.lon, k.lat];

  if (durum.mod !== 'nav') {
    konumIsaretiGuncelle(p, k.yon);
    if (durum.ilkKonum && !durum.hedef) harita.flyTo({ center: p, zoom: 15, duration: 800 });
    durum.ilkKonum = false;
    return;
  }

  const rota = durum.rota;
  const o = rotayaOturt(rota, p);
  if (!o) { navBitir(true); return; }
  const esik = Math.max(SAPMA_ESIK_M, (k.dogruluk || 0) * 1.5);
  const yolda = o.uzaklik <= esik;
  if (yolda) {
    durum.sapmaSayac = 0;
    rota.segman = o.segman;
  } else {
    durum.sapmaSayac += 1;
    if (durum.sapmaSayac >= SAPMA_ARDISIK) yenidenRota(k);
  }

  const gosterilen = yolda ? o.nokta : p;
  const yon = yolda ? o.yon : k.yon;
  konumIsaretiGuncelle(gosterilen, yon);
  if (yolda) veriYaz('rota-kalan', cizgi([o.nokta, ...rota.koord.slice(o.segman + 1)]));

  const kalanM = Math.max(0, rota.toplam - o.ilerleme);
  durum.ilerleme = o.ilerleme;
  if (yolda && kalanM <= VARIS_ESIK_M) { navBitir(true); return; }
  // Ara duraklar: durak noktasina gelince bir sonraki duraga gecilir
  const bacak = durum.gecilenDurak - rota.ilkDurak;
  if (yolda && bacak < rota.bacakSonM.length - 1 && o.ilerleme >= rota.bacakSonM[bacak] - VARIS_ESIK_M) {
    durum.gecilenDurak += 1;
    const durak = durum.duraklar[durum.gecilenDurak - 1];
    soyle(`${durum.gecilenDurak}. durağa ulaştınız${durak?.ad ? `: ${durak.ad}` : ''}.`, true);
    duraklariCiz();
  }

  const i = siradakiManevra(rota, o.ilerleme);
  const manevraM = Math.max(0, rota.manevralar[i].basM - o.ilerleme);
  if (i !== durum.sonManevra) {
    // Gecilen manevradan sonra uzun yol varsa "... devam edin" bilgisini bir kez soyle
    const gecen = rota.manevralar[i - 1];
    if (durum.sonManevra >= 0 && i > durum.sonManevra && manevraM > 2000 && gecen?.verbal_post_transition_instruction) {
      soyle(gecen.verbal_post_transition_instruction);
    }
    durum.sonManevra = i;
    veriYaz('manevra-nokta', nokta(rota.koord[rota.manevralar[i].begin_shape_index] || rota.koord[rota.koord.length - 1]));
  }
  if (!durum.yenidenRotaSuruyor) manevraKartiYaz(rota, i, manevraM);
  if (durum.yolTarifiAcik) yolTarifiYaz();
  if (yolda) sesliYonlendir(rota, i, manevraM, k.hiz);
  if (yolda) sesliUyarilar(rota, o.ilerleme, k.hiz);
  ozetYaz(kalanSure(rota, o.ilerleme), kalanM, k.hiz);
  if (yolda) hizLimitiGoster(rota, o.ilerleme, k.hiz);
  paylasimGonder(k, rota, o.ilerleme);
  kameraGuncelle(gosterilen, yon, k.hiz);
}

function olcumIsle(olcum) {
  if (durum.simAcik && durum.mod === 'nav') return;
  const c = olcum.coords;
  konumGeldi({
    lat: c.latitude, lon: c.longitude, dogruluk: c.accuracy,
    hiz: Number.isFinite(c.speed) ? c.speed : null,
    yon: Number.isFinite(c.heading) && (c.speed ?? 0) > 1 ? c.heading : null,
  });
}

function konumIzlemeBaslat() {
  if (!('geolocation' in navigator)) {
    planMesaj('Bu tarayıcı konum vermiyor; simülasyonu kullanabilirsiniz.', 'uyari');
    return;
  }
  if (durum.izleme != null) return;
  durum.izleme = navigator.geolocation.watchPosition(
    olcumIsle,
    (hata) => {
      console.warn('Konum alınamadı', hata.code, hata.message);
      durum.izleme = null;
      planMesaj(hata.code === 1
        ? 'Konum izni verilmedi. Tarayıcı ayarlarından izin verin ya da simülasyonu kullanın.'
        : 'Konum alınamadı. Açık alanda tekrar deneyin ya da simülasyonu kullanın.', 'uyari');
    },
    { enableHighAccuracy: true, maximumAge: 1000, timeout: 20000 },
  );
}

/** Rotadan cikildiginda guncel konumdan yeni rota ister (en fazla 10 saniyede bir). */
async function yenidenRota(k) {
  if (durum.yenidenRotaSuruyor || Date.now() - durum.sonYenidenRota < YENIDEN_ROTA_ARALIK_MS) return;
  durum.yenidenRotaSuruyor = true;
  durum.sonYenidenRota = Date.now();
  manevraKartiMesaj('Yeni rota', 'Rota yeniden hesaplanıyor...');
  soyle('Rota yeniden hesaplanıyor.', true);
  try {
    const yeni = await rotaIste(k, kalanDuraklar(k), durum.gecilenDurak);
    if (durum.mod !== 'nav') return;
    rotaAyarla(yeni);
    hizLimitiYukle(yeni);
    durum.sapmaSayac = 0;
    if (durum.simAcik) Object.assign(simDurum, { d: 0, sapma: 0, sapmaAdim: 0 });
  } catch (hata) {
    console.warn('Yeniden rota alınamadı', hata);
    manevraKartiMesaj('Rota yok', hata instanceof HataMesaji ? `${hata.message} Tekrar denenecek.` : 'Yeni rota alınamadı, tekrar denenecek.');
  } finally {
    durum.yenidenRotaSuruyor = false;
  }
}

/* ---------- Simulasyon ---------- */

function simAdim() {
  const rota = durum.rota;
  if (!rota || durum.mod !== 'nav') return;
  const hiz = durum.simHiz / 3.6;
  simDurum.d = Math.min(rota.toplam, simDurum.d + hiz);
  let { nokta: p, yon } = rotaUzerindeNokta(rota, simDurum.d);
  // Sapma denemesi: konumu birkac adimda rotanin sagina 120 m'ye kadar kaydirir
  if (simDurum.sapmaAdim > 0) {
    simDurum.sapmaAdim -= 1;
    simDurum.sapma = Math.min(120, simDurum.sapma + 30);
  }
  if (simDurum.sapma > 0) p = kaydir(p, (yon + 90) % 360, simDurum.sapma);
  konumGeldi({ lat: p[1], lon: p[0], hiz, yon, dogruluk: 5 });
}

function simBaslat() {
  simDurdur();
  Object.assign(simDurum, { d: 0, sapma: 0, sapmaAdim: 0 });
  simDurum.zamanlayici = setInterval(simAdim, 1000);
  simAdim();
}

function simDurdur() {
  if (simDurum.zamanlayici) clearInterval(simDurum.zamanlayici);
  simDurum.zamanlayici = null;
}

/* ---------- Akis ---------- */

/**
 * Secilen yer hedef olur; "Durak ekle" acikken mevcut duraklarin sonuna eklenir (onceki hedef ara durak olur).
 * Ardindan baslangictan (konum ya da harita merkezi) rota onizlemesi hesaplanir.
 */
async function hedefSec(hedef) {
  if (durum.durakEkle && durum.duraklar.length) durum.duraklar.push(hedef);
  else durum.duraklar = [hedef];
  durum.durakEkle = false;
  durum.gecilenDurak = 0;
  durum.hedef = hedef;
  sonYerEkle(hedef);
  $('sonuclar').replaceChildren();
  $('hedef-ara').value = '';
  duraklariCiz();
  duraklarListesiYaz();
  await onizlemeHesapla();
}

/** Plan kartindaki durak listesi (sirali, silinebilir). */
function duraklarListesiYaz() {
  const liste = $('durak-listesi');
  liste.replaceChildren();
  durum.duraklar.forEach((d, i) => {
    const sil = el('button', { type: 'button', sinif: 'durak-sil', 'aria-label': `${i + 1}. duragi kaldir`, metin: 'Kaldır' });
    sil.addEventListener('click', () => durakSil(i));
    const son = i === durum.duraklar.length - 1;
    liste.append(el('li', {}, el('span', { sinif: 'durak-no', metin: son ? 'Hedef' : `${i + 1}.` }), el('span', { sinif: 'durak-ad', metin: d.ad }), sil));
  });
  $('paylas').hidden = !durum.duraklar.length;
  $('gpx-indir').hidden = !durum.duraklar.length;
  $('google-ac').hidden = !durum.duraklar.length;
  $('yandex-ac').hidden = !durum.duraklar.length;
}

/**
 * Dis navigasyon icin nokta listesi: tum duraklar zorunlu, kalan yer GPX ara noktalariyla (sira korunarak, esit aralikla) doldurulur.
 * Donus: {noktalar, eksik} (eksik: sigmayan durak var mi).
 */
function disNoktalar(enFazla) {
  const duraklar = durum.duraklar.slice(durum.gecilenDurak);
  const tum = duraklar.flatMap((d, di) => [...(d.ara || []).map((a) => ({ ...a, ara: true, di })), { lat: d.lat, lon: d.lon, di }]);
  const durakSay = duraklar.length;
  if (durakSay > enFazla) return { noktalar: duraklar.slice(0, enFazla), eksik: true };
  const araListe = tum.filter((n) => n.ara);
  const yer = enFazla - durakSay;
  const secilen = new Set(yer > 0 && araListe.length
    ? Array.from({ length: Math.min(yer, araListe.length) }, (_, k) => araListe[Math.floor(((k + 0.5) * araListe.length) / Math.min(yer, araListe.length))])
    : []);
  return { noktalar: tum.filter((n) => !n.ara || secilen.has(n)), eksik: false };
}

const ciftYaz = (n) => `${n.lat.toFixed(6)},${n.lon.toFixed(6)}`;

/** Rotayi Google Haritalar'da acar (telefonda Google Haritalar uygulamasi). Google en fazla 9 ara nokta kabul eder. */
function googleAc() {
  const { noktalar, eksik } = disNoktalar(10);
  const hedef = noktalar.at(-1);
  const p = new URLSearchParams({ api: '1', destination: ciftYaz(hedef),
    travelmode: { araba: 'driving', motosiklet: 'two-wheeler', yaya: 'walking' }[durum.profil] || 'driving' });
  if (durum.konum) p.set('origin', ciftYaz(durum.konum));
  if (noktalar.length > 1) p.set('waypoints', noktalar.slice(0, -1).map(ciftYaz).join('|'));
  window.open(`https://www.google.com/maps/dir/?${p}`, '_blank', 'noopener');
  if (eksik) planMesaj('Google en fazla 10 nokta kabul ediyor; ilk 10 durak gönderildi.', 'uyari');
}

/** Rotayi Yandex Haritalar / Navigasyon'da acar; baslangic bos birakilirsa Yandex anlik konumu kullanir. */
function yandexAc() {
  const { noktalar, eksik } = disNoktalar(20);
  const rtext = [durum.konum ? ciftYaz(durum.konum) : '', ...noktalar.map(ciftYaz)].join('~');
  const p = new URLSearchParams({ rtext, rtt: durum.profil === 'yaya' ? 'pd' : 'auto' });
  window.open(`https://yandex.com.tr/maps/?${p}`, '_blank', 'noopener');
  if (eksik) planMesaj("Yandex'e ilk 20 durak gönderildi.", 'uyari');
}

/** Duraklari ve profili paylasim koduyla paylasir; baglanti panoya kopyalanir (destekleniyorsa paylasim penceresi acilir). */
async function rotaPaylas() {
  try {
    const v = await api('/v1/paylasim', {
      method: 'POST',
      body: JSON.stringify({ profil: durum.profil, duraklar: durum.duraklar.map(({ lat, lon, ad, ara }) => ({ lat, lon, ad, ara })) }),
    });
    const adres = `${location.origin}${location.pathname}?kod=${v.kod}`;
    if (navigator.share) {
      await navigator.share({ title: 'Rota', text: `Rota kodu: ${v.kod}`, url: adres });
    } else {
      await navigator.clipboard.writeText(adres);
    }
    planMesaj(`Paylaşım kodu ${v.kod} (bağlantı kopyalandı, ${tarihSaatYaz(new Date(v.bitis))} tarihine kadar geçerli).`, 'basari');
  } catch (hata) {
    if (hata?.name === 'AbortError') return;
    console.warn('Paylaşım başarısız', hata);
    planMesaj(hata instanceof HataMesaji ? hata.message : 'Paylaşım oluşturulamadı.', 'hata');
  }
}

/** Duraklari ve (varsa) hesaplanan rota cizgisini GPX dosyasi olarak indirir. */
async function gpxIndir() {
  const govde = { ad: durum.duraklar.at(-1)?.ad || 'Rota', duraklar: durum.duraklar.map(({ lat, lon, ad }) => ({ lat, lon, ad })) };
  if (durum.rota) govde.noktalar = durum.rota.koord.map(([lon, lat]) => [lat, lon]);
  try {
    const yanit = await fetch(`${durum.api.replace(/\/$/, '')}/v1/gpx/olustur`, {
      method: 'POST', headers: { 'X-Harita-Anahtar': durum.anahtar, 'Content-Type': 'application/json' }, body: JSON.stringify(govde),
    });
    if (!yanit.ok) throw new HataMesaji(HATA_METNI[yanit.status] || 'GPX oluşturulamadı.', yanit.status);
    const baglanti = el('a', { href: URL.createObjectURL(await yanit.blob()), download: 'rota.gpx' });
    baglanti.click();
    setTimeout(() => URL.revokeObjectURL(baglanti.href), 1000);
  } catch (hata) {
    console.warn('GPX indirilemedi', hata);
    planMesaj(hata instanceof HataMesaji ? hata.message : 'GPX oluşturulamadı.', 'hata');
  }
}

/** Secilen GPX dosyasindaki duraklari (yol noktalari, rota ya da izin basi / sonu) yukler ve onizler. */
async function gpxYukle(dosya) {
  if (!dosya) return;
  try {
    const v = await api(`/v1/gpx/oku?iz_takip=${$('iz-takip').checked}`, { method: 'POST', body: await dosya.text() });
    duraklariYukle(v.duraklar);
    await onizlemeHesapla();
    const ara = v.duraklar.reduce((t, d) => t + (d.ara?.length || 0), 0);
    planMesaj(`${v.duraklar.length} durak GPX dosyasından yüklendi${ara ? `; rota izin yollarını ${ara} ara noktayla takip ediyor` : ''}.`, 'basari');
  } catch (hata) {
    console.warn('GPX okunamadı', hata);
    planMesaj(hata instanceof HataMesaji ? hata.message : 'GPX dosyası okunamadı.', 'hata');
  }
}

/** Disaridan gelen noktalari durak listesi yapar (adi olmayana sira adi verilir). */
function duraklariYukle(noktalar, adlar = []) {
  durum.duraklar = noktalar.map((n, i) => ({
    lat: n.lat, lon: n.lon, ad: n.ad || adlar[i] || (i === noktalar.length - 1 ? 'Hedef' : `${i + 1}. durak`),
    ...(n.ara?.length ? { ara: n.ara } : {}),
  }));
  durum.gecilenDurak = 0;
  durum.hedef = durum.duraklar.at(-1);
  duraklariCiz();
  duraklarListesiYaz();
}

async function durakSil(i) {
  durum.duraklar.splice(i, 1);
  if (!durum.duraklar.length) { hedefTemizle(); return; }
  durum.hedef = durum.duraklar.at(-1);
  duraklariCiz();
  duraklarListesiYaz();
  await onizlemeHesapla();
}

async function onizlemeHesapla() {
  if (!durum.duraklar.length) return;
  // Konum yoksa: birden cok durakta rota ilk duraktan baslar, tek hedefte harita merkezinden
  let baslangic = durum.konum;
  let duraklar = durum.duraklar;
  let ilkDurak = 0;
  let not = '';
  if (!baslangic && durum.duraklar.length > 1) {
    [baslangic, ilkDurak, duraklar] = [durum.duraklar[0], 1, durum.duraklar.slice(1)];
    not = 'Konum yok: rota ilk duraktan başlıyor. Simülasyonla deneyebilirsiniz.';
  } else if (!baslangic) {
    const c = harita.getCenter();
    baslangic = { lat: c.lat, lon: c.lng };
    not = 'Konum yok: başlangıç harita merkezi alındı. Simülasyonla deneyebilirsiniz.';
  }
  planMesaj('Rota hesaplanıyor...');
  try {
    const rota = await rotaIste(baslangic, duraklar, ilkDurak, true);
    rotaAyarla(rota);
    durum.alternatifler = [rota, ...rota.alternatifler];
    durum.secilenAlt = 0;
    durum.mod = 'onizleme';
    alternatifleriGoster();
    planMesaj(not, not ? 'uyari' : '');
    arayuzGuncelle();
    ozetYaz(rota.sure, rota.toplam, durum.konum?.hiz);
    rotayaSigdir(rota);
    havaGoster(rota);
  } catch (hata) {
    console.warn('Rota alınamadı', hata);
    planMesaj(hata instanceof HataMesaji ? hata.message : 'Rota alınamadı.', 'hata');
  }
}

const HAVA_UYARI_METNI = {
  firtina: 'fırtına', kar: 'kar', buzlanma: 'buzlanma', kuvvetli_yagis: 'kuvvetli yağış', kuvvetli_ruzgar: 'kuvvetli rüzgar', sis: 'sis',
};

/** Onizlenen rota boyunca varis saatindeki havayi ozetler: sicaklik araligi, ilk uyarinin yeri. Hata olursa gizli kalir. */
async function havaGoster(rota) {
  const alan = $('hava');
  alan.hidden = true;
  const adim = Math.ceil(rota.koord.length / 5000);
  const noktalar = rota.koord.filter((_, i) => i % adim === 0 || i === rota.koord.length - 1).map(([lon, lat]) => [lat, lon]);
  try {
    const v = await api('/v1/yol/hava', { method: 'POST', body: JSON.stringify({ noktalar, sure_sn: rota.sure }) });
    if (durum.rota !== rota) return;
    const tahminli = v.noktalar.filter((n) => n.tahmin_var && n.sicaklik_c !== null);
    if (!tahminli.length) return;
    const sicak = tahminli.map((n) => n.sicaklik_c);
    const [enAz, enCok] = [Math.round(Math.min(...sicak)), Math.round(Math.max(...sicak))];
    const ilk = tahminli.find((n) => n.uyarilar.length);
    let metin = `Yol boyunca hava: ${enAz === enCok ? enAz : `${enAz} / ${enCok}`} °C, ${tahminli[0].durum || ''}`.trim();
    if (ilk) metin += `. Dikkat: ${ilk.uyarilar.map((u) => HAVA_UYARI_METNI[u] || u).join(', ')} (${mesafeYaz(ilk.rota_m)} sonra, ${saatYaz(new Date(ilk.varis))})`;
    alan.textContent = `${metin}.`;
    alan.classList.toggle('uyari-var', Boolean(ilk));
    alan.hidden = false;
  } catch (hata) {
    console.warn('Hava durumu alınamadı', hata);
  }
}

function hedefTemizle() {
  $('hava').hidden = true;
  Object.assign(durum, { hedef: null, duraklar: [], gecilenDurak: 0, durakEkle: false, rota: null, mod: 'plan', alternatifler: [], secilenAlt: 0 });
  for (const ad of Object.keys(durum.cizim)) veriYaz(ad, BOS);
  $('hedef-ara').value = '';
  duraklarListesiYaz();
  planMesaj('');
  alternatifleriGoster();
  arayuzGuncelle();
}

async function ekranAcikTut(ac) {
  try {
    if (ac && 'wakeLock' in navigator) {
      durum.ekranKilidi = await navigator.wakeLock.request('screen');
    } else if (!ac && durum.ekranKilidi) {
      await durum.ekranKilidi.release();
      durum.ekranKilidi = null;
    }
  } catch (hata) {
    console.warn('Ekran açık tutulamadı', hata);
  }
}

async function navBaslat() {
  if (!durum.rota) return;
  durum.gecilenDurak = 0;
  duraklariCiz();
  if (!durum.simAcik) {
    if (!durum.konum) {
      planMesaj('Konum henüz alınmadı. Konum iznini verin ya da simülasyonu açın.', 'uyari');
      konumIzlemeBaslat();
      return;
    }
    // Onizleme baska bir baslangictan hesaplandiysa guncel konumdan yeniden hesapla
    if (mesafeM([durum.konum.lon, durum.konum.lat], durum.rota.koord[0]) > BASLANGIC_FARK_M) {
      try {
        rotaAyarla(await rotaIste(durum.konum, durum.duraklar));
      } catch (hata) {
        console.warn('Başlangıç rotası alınamadı', hata);
        planMesaj(hata instanceof HataMesaji ? hata.message : 'Rota alınamadı.', 'hata');
        return;
      }
    }
  }
  // Rota ilk duraktan basladiysa (konumsuz simulasyon) o durak gecilmis sayilir
  durum.gecilenDurak = durum.rota.ilkDurak;
  duraklariCiz();
  Object.assign(durum, { mod: 'nav', takip: true, sapmaSayac: 0, sonYenidenRota: 0, alternatifler: [], secilenAlt: 0 });
  alternatifleriGoster();
  arayuzGuncelle();
  sayfaAc(false);
  ekranAcikTut(true);
  setTimeout(() => { if (durum.mod === 'nav') arkaPlanKoru(true); }, 2500);
  hizLimitiYukle(durum.rota);
  const ilk = durum.rota.manevralar[0];
  durum.soylenen.set(`${durum.rota.no}:0`, { uzak: true, yakin: true });
  soyle(`Navigasyon başladı. ${buyukBasla(ilk?.verbal_pre_transition_instruction || '')}`, true);
  if (durum.simAcik) simBaslat();
  else konumGeldi({ ...durum.konum });
}

/** Navigasyonu bitirir. Varildiysa hedef temizlenir, degilse rota onizlemesine donulur. */
function navBitir(varildi = false) {
  paylasimiDurdur(varildi);
  simDurdur();
  ekranAcikTut(false);
  arkaPlanKoru(false);
  if (varildi) {
    const son = durum.rota?.manevralar.at(-1);
    soyle(son?.verbal_pre_transition_instruction || 'Hedefinize ulaştınız.', true);
  } else if ('speechSynthesis' in window) speechSynthesis.cancel();
  harita.easeTo({ pitch: 0, bearing: 0, padding: { top: 0, bottom: 0, left: 0, right: 0 }, duration: 600 });
  if (varildi) {
    const ad = durum.hedef?.ad;
    hedefTemizle();
    planMesaj(`Hedefe ulaşıldı${ad ? `: ${ad}` : ''}.`, 'basari');
    if (durum.konum) konumIsaretiGuncelle([durum.konum.lon, durum.konum.lat], durum.konum.yon);
    return;
  }
  durum.mod = 'onizleme';
  durum.takip = true;
  durum.gecilenDurak = 0;
  arayuzGuncelle();
  veriYaz('manevra-nokta', BOS);
  duraklariCiz();
  // Yolda yeniden rota yalniz kalan duraklari kapsayabilir; onizleme tum duraklarla yeniden hesaplanir
  onizlemeHesapla();
}

/* ---------- Alternatif rotalar ---------- */

/** Alternatif rotalari haritada soluk cizgi, altta secim dugmesi olarak gosterir (yalniz onizlemede ve tek hedefte). */
function alternatifleriGoster() {
  const liste = durum.mod === 'onizleme' ? durum.alternatifler : [];
  const diger = liste.filter((_, i) => i !== durum.secilenAlt);
  [0, 1].forEach((i) => veriYaz(`rota-alt-${i}`, diger[i] ? cizgi(diger[i].koord) : BOS));
  const kutu = $('alternatifler');
  kutu.replaceChildren();
  kutu.hidden = liste.length < 2;
  if (liste.length < 2) return;
  const enHizli = Math.min(...liste.map((r) => r.sure));
  liste.forEach((r, i) => {
    const fark = r.sure - enHizli;
    const etkin = i === durum.secilenAlt;
    const dugme = el('button', { type: 'button', sinif: `alt-secim${etkin ? ' etkin' : ''}`, 'aria-pressed': String(etkin) },
      el('span', { sinif: 'as-sure', metin: sureYaz(r.sure) }),
      el('span', { sinif: 'as-fark', metin: `${fark < 30 ? 'En hızlı' : `+${sureYaz(fark)}`} · ${mesafeYaz(r.toplam)}` }));
    dugme.addEventListener('click', () => rotaSec(i));
    kutu.append(dugme);
  });
}

/** Onizlemede verilen siradaki alternatifi etkin rota yapar. */
function rotaSec(i) {
  if (durum.mod !== 'onizleme' || !durum.alternatifler[i] || i === durum.secilenAlt) return;
  durum.secilenAlt = i;
  rotaAyarla(durum.alternatifler[i]);
  ozetYaz(durum.rota.sure, durum.rota.toplam, durum.konum?.hiz);
  alternatifleriGoster();
  havaGoster(durum.rota);
}

/** Haritada soluk alternatif cizgisine dokunulduysa onu secer; dokunulduysa true doner. */
function alternatifDokunmasi(olay) {
  if (durum.mod !== 'onizleme' || durum.alternatifler.length < 2) return false;
  const katmanlar = ['rota-alt-0', 'rota-alt-1'].filter((k) => harita.getLayer(k));
  const kutu = [[olay.point.x - 10, olay.point.y - 10], [olay.point.x + 10, olay.point.y + 10]];
  const bulunan = harita.queryRenderedFeatures(kutu, { layers: katmanlar });
  if (!bulunan.length) return false;
  const diger = durum.alternatifler.filter((_, i) => i !== durum.secilenAlt);
  const hedef = diger[Number(bulunan[0].layer.id.slice(-1))];
  if (hedef) rotaSec(durum.alternatifler.indexOf(hedef));
  return true;
}

/* ---------- Varisi paylas ---------- */

/** Kisa sureli bildirim (4,5 sn). */
function bildir(metin) {
  const kutu = $('bildirim');
  kutu.textContent = metin;
  kutu.hidden = false;
  clearTimeout(bildir.zamanlayici);
  bildir.zamanlayici = setTimeout(() => { kutu.hidden = true; }, 4500);
}

/** Tahmin edilemez takip kodu (15 karakter, karisik harf ve rakam). */
function rastgeleKod(uzunluk = 15) {
  const harfler = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  return [...crypto.getRandomValues(new Uint8Array(uzunluk))].map((b) => harfler[b % harfler.length]).join('');
}

/** Paylasim kapaliysa baslatir ve baglantiyi paylasir; aciksa durdurur. Yalniz navigasyondayken. */
async function varisPaylasDegistir() {
  if (durum.paylasim) {
    paylasimiDurdur(false);
    bildir('Paylaşım durduruldu.');
    return;
  }
  if (durum.mod !== 'nav' || !durum.rota) return;
  const kanal = `y${rastgeleKod()}`;
  const adres = new URL(`takip.html?k=${kanal}`, location.href).href;
  durum.paylasim = { kanal, adres, son: 0, hata: 0 };
  arayuzGuncelle();
  paylasimGonder(durum.konum, durum.rota, durum.ilerleme, true);
  const ad = durum.hedef?.ad;
  try {
    if (navigator.share) {
      await navigator.share({ title: 'Varışımı takip et', text: `${ad ? `${ad} yolculuğumu` : 'Yolculuğumu'} canlı takip edebilirsin.`, url: adres });
    } else {
      await navigator.clipboard.writeText(adres);
      bildir('Takip bağlantısı kopyalandı.');
    }
  } catch (hata) {
    if (hata?.name === 'AbortError') {
      paylasimiDurdur(false);
      bildir('Paylaşım iptal edildi.');
      return;
    }
    console.warn('Takip bağlantısı paylaşılamadı', hata);
    bildir('Bağlantı paylaşılamadı; "Bağlantıyı kopyala" düğmesini deneyin.');
  }
}

async function paylasimBaglantisiniKopyala() {
  if (!durum.paylasim) return;
  try {
    await navigator.clipboard.writeText(durum.paylasim.adres);
    bildir('Takip bağlantısı kopyalandı.');
  } catch (hata) {
    console.warn('Bağlantı kopyalanamadı', hata);
    bildir('Bağlantı kopyalanamadı.');
  }
}

/** Konumu ve varis bilgisini (kalan sure / mesafe, tahmini varis) canli kanala gonderir; en sik 4 sn'de bir. */
function paylasimGonder(k, rota, ilerleme, zorla = false) {
  const p = durum.paylasim;
  if (!p || !k || !rota) return;
  const simdi = Date.now();
  if (!zorla && simdi - p.son < PAYLASIM_ARALIK_MS) return;
  p.son = simdi;
  const kalanSn = Math.round(kalanSure(rota, ilerleme));
  const govde = {
    id: 'surucu', lat: k.lat, lon: k.lon,
    veri: {
      kalanM: Math.round(Math.max(0, rota.toplam - ilerleme)), kalanSn, varis: new Date(simdi + kalanSn * 1000).toISOString(),
      hedefAd: durum.hedef?.ad, hedef: durum.hedef ? { lat: durum.hedef.lat, lon: durum.hedef.lon } : undefined, bitti: false,
    },
  };
  if (Number.isFinite(k.hiz)) govde.hiz = Math.min(100, Math.max(0, k.hiz));
  if (Number.isFinite(k.yon)) govde.yon = ((k.yon % 360) + 360) % 360;
  if (Number.isFinite(k.dogruluk)) govde.dogruluk = Math.min(10000, Math.max(0, k.dogruluk));
  api(`/v1/canli/${p.kanal}/konum`, { method: 'POST', body: JSON.stringify(govde) }).then(() => { p.hata = 0; }).catch((hata) => {
    p.hata += 1;
    console.warn('Konum paylaşılamadı', hata);
    if (p.hata === 5) bildir('Paylaşım bağlantısı kesildi, yeniden deneniyor.');
  });
}

/** Paylasimi bitirir; izleyen sayfaya "bitti" (varildiysa "vardi") bilgisi gonderilir. */
function paylasimiDurdur(varildi = false) {
  const p = durum.paylasim;
  if (!p) return;
  durum.paylasim = null;
  const k = durum.konum;
  if (k) {
    api(`/v1/canli/${p.kanal}/konum`, { method: 'POST', body: JSON.stringify({ id: 'surucu', lat: k.lat, lon: k.lon, veri: { bitti: true, varildi } }) })
      .catch((hata) => console.warn('Paylaşım bitişi gönderilemedi', hata));
  }
  arayuzGuncelle();
}

/* ---------- Yolda ara ---------- */

/** Tur dugmelerini (yakit, yemek, eczane...) cizer; secili olan vurgulanir, yeniden dokunmak kapatir. */
function yoldaTurleriYaz() {
  const kutu = $('yolda-turler');
  kutu.replaceChildren();
  for (const t of YOLDA_TURLERI) {
    const etkin = durum.yoldaTur === t.kod;
    const dugme = el('button', { type: 'button', sinif: `cip${etkin ? ' etkin' : ''}`, 'aria-pressed': String(etkin), metin: t.ad });
    dugme.addEventListener('click', () => (etkin ? yoldaTemizle() : yoldaAra(t.kod)));
    kutu.append(dugme);
  }
}

/** Haritadaki ve listedeki "yolda ara" sonuclarini temizler. */
function yoldaTemizle() {
  durum.yoldaTur = null;
  durum.yolda = [];
  veriYaz('yolda', BOS);
  $('yolda-sonuc').replaceChildren();
  yoldaTurleriYaz();
}

/** Rotanin kalan bolumunden en fazla enFazla noktalik seyreltilmis [boylam, enlem] listesi. */
function kalanRotaNoktalari(rota, enFazla = YOLDA_KOORD_MAKS) {
  const kalan = rota.koord.slice(Math.max(0, rota.segman));
  const adim = Math.max(1, Math.ceil(kalan.length / enFazla));
  return kalan.filter((_, i) => i % adim === 0 || i === kalan.length - 1);
}

/** Rotanin kalan kismi boyunca secilen turdeki yerleri bulur; en yakindan baslayarak siralar. */
async function yoldaAra(tur) {
  const rota = durum.rota;
  if (!rota) return;
  durum.yoldaTur = tur;
  durum.yolda = [];
  veriYaz('yolda', BOS);
  yoldaTurleriYaz();
  const liste = $('yolda-sonuc');
  liste.replaceChildren(el('li', {}, el('span', { sinif: 'ayrinti', metin: 'Aranıyor...' })));
  const kalanM = Math.max(1, rota.toplam - (durum.mod === 'nav' ? durum.ilerleme : 0));
  try {
    const v = await api('/v1/adres/rota-boyunca', {
      method: 'POST',
      body: JSON.stringify({ koordinatlar: kalanRotaNoktalari(rota), tur, tampon_m: YOLDA_TAMPON_M, limit: 12 }),
    });
    if (durum.rota !== rota || durum.yoldaTur !== tur) return;
    durum.yolda = v.map((y) => ({
      ad: y.ad || 'Adsız', lat: y.merkez.lat, lon: y.merkez.lon,
      ileriM: Math.round((y.ek?.rota_orani ?? 0) * kalanM), uzakM: Math.round(y.mesafe_m ?? 0),
    })).sort((a, b) => a.ileriM - b.ileriM);
    veriYaz('yolda', {
      type: 'FeatureCollection',
      features: durum.yolda.map((y) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [y.lon, y.lat] }, properties: { ad: y.ad } })),
    });
    yoldaSonucYaz();
  } catch (hata) {
    console.warn('Yolda arama başarısız', hata);
    liste.replaceChildren(el('li', {}, el('span', { sinif: 'ayrinti', metin: hata instanceof HataMesaji ? hata.message : 'Arama yapılamadı.' })));
  }
}

function yoldaSonucYaz() {
  const liste = $('yolda-sonuc');
  liste.replaceChildren();
  if (!durum.yolda.length) {
    liste.append(el('li', {}, el('span', { sinif: 'ayrinti', metin: 'Rota üzerinde bulunamadı.' })));
    return;
  }
  for (const y of durum.yolda) {
    const dugme = el('button', { type: 'button' }, el('span', { sinif: 'ad', metin: y.ad }),
      el('span', { sinif: 'ayrinti', metin: `${mesafeYaz(y.ileriM)} ileride · rotaya ${mesafeYaz(y.uzakM)}` }));
    dugme.addEventListener('click', () => yoldaDurakEkle(y));
    liste.append(el('li', {}, dugme));
  }
}

/** Secilen yeri hedeften once durak olarak ekler; yolda ise rota hemen yeniden hesaplanir. */
async function yoldaDurakEkle(yer) {
  const durak = { lat: yer.lat, lon: yer.lon, ad: yer.ad };
  durum.duraklar.splice(Math.max(0, durum.duraklar.length - 1), 0, durak);
  duraklarListesiYaz();
  duraklariCiz();
  if (durum.mod === 'nav' && durum.konum) {
    durum.sonYenidenRota = 0;
    soyle(`${yer.ad} durak olarak eklendi.`);
    await yenidenRota(durum.konum);
  } else {
    await onizlemeHesapla();
  }
}

/* ---------- Ev, is ve son yerler ---------- */

function yerleriOku() {
  const v = depoOku(YER_DEPO);
  return { ev: v.ev || null, is: v.is || null, son: Array.isArray(v.son) ? v.son : [] };
}

/** Hedefi son yerlere ekler (40 m icindeki eskisi degistirilir, en fazla SON_YER_MAKS tutulur). */
function sonYerEkle(hedef) {
  if (!hedef || !Number.isFinite(hedef.lat)) return;
  const kayit = { ad: hedef.ad, lat: hedef.lat, lon: hedef.lon };
  const liste = yerleriOku().son.filter((s) => mesafeM([s.lon, s.lat], [kayit.lon, kayit.lat]) > 40);
  depoYaz(YER_DEPO, { son: [kayit, ...liste].slice(0, SON_YER_MAKS) });
}

/** Onizlemedeki hedefi Ev ya da Is olarak kaydeder. */
function hedefiKaydet(tur) {
  const h = durum.duraklar.at(-1);
  if (!h) return;
  depoYaz(YER_DEPO, { [tur]: { ad: h.ad, lat: h.lat, lon: h.lon } });
  planMesaj(`${tur === 'ev' ? 'Ev' : 'İş'} olarak kaydedildi: ${h.ad}`, 'basari');
}

/** Arama kutusu bos ve odakliyken Ev, Is ve son hedefleri listeler. */
function kayitliYerleriYaz() {
  const liste = $('sonuclar');
  liste.replaceChildren();
  const y = yerleriOku();
  const ogeler = [];
  if (y.ev) ogeler.push({ ...y.ev, etiket: 'Ev' });
  if (y.is) ogeler.push({ ...y.is, etiket: 'İş' });
  y.son.forEach((s) => ogeler.push({ ...s, etiket: 'Son' }));
  for (const o of ogeler) {
    const dugme = el('button', { type: 'button' },
      el('span', { sinif: 'ad', metin: o.etiket === 'Son' ? o.ad : `${o.etiket}: ${o.ad}` }),
      el('span', { sinif: 'ayrinti', metin: o.etiket === 'Son' ? 'Son hedef' : 'Kayıtlı yer' }));
    dugme.addEventListener('click', () => hedefSec({ lat: o.lat, lon: o.lon, ad: o.ad }));
    liste.append(el('li', {}, dugme));
  }
}

/* ---------- Hiz limiti ---------- */

/**
 * Rotanin yol hiz limitlerini (OSM "maxspeed" verisi) Valhalla trace_attributes ile parca parca ister.
 * rota.hizSegmanlari: [{bas, son, limit}] (metre, rota basindan; limiti kayitsiz yollar listede yoktur, gosterge cikmaz).
 */
async function hizLimitiYukle(rota) {
  rota.hizSegmanlari = [];
  if (durum.profil === 'yaya') return;
  const n = rota.koord.length;
  for (let bas = 0; bas < n - 1; bas += HIZ_PARCA_NOKTA - 1) {
    const parca = rota.koord.slice(bas, Math.min(n, bas + HIZ_PARCA_NOKTA));
    if (parca.length < 2) break;
    try {
      const v = await api('/valhalla/trace_attributes', {
        method: 'POST',
        body: JSON.stringify({
          shape: parca.map(([lon, lat]) => ({ lat, lon })), costing: COSTING[durum.profil], shape_match: 'edge_walk',
          filters: { attributes: ['edge.speed_limit', 'edge.begin_shape_index', 'edge.end_shape_index'], action: 'include' },
        }),
      });
      if (durum.rota !== rota) return;
      for (const e of v.edges || []) {
        if (!e.speed_limit) continue;
        const b = rota.kum[Math.min(n - 1, bas + e.begin_shape_index)];
        const s = rota.kum[Math.min(n - 1, bas + e.end_shape_index)];
        if (s > b) rota.hizSegmanlari.push({ bas: b, son: s, limit: e.speed_limit });
      }
    } catch (hata) {
      console.warn('Hız limitleri alınamadı', hata);
    }
  }
}

/** Rotada verilen ilerlemedeki hiz limiti (km/sa); kayitli degilse null. */
function hizLimitiBul(rota, ilerleme) {
  const seg = rota.hizSegmanlari;
  if (!seg?.length) return null;
  let alt = 0;
  let ust = seg.length - 1;
  while (alt <= ust) {
    const orta = (alt + ust) >> 1;
    if (seg[orta].son < ilerleme) alt = orta + 1;
    else if (seg[orta].bas > ilerleme) ust = orta - 1;
    else return seg[orta].limit;
  }
  return null;
}

/** Limit tabelasini gosterir; hiz limiti asilirsa gosterge kirmizi olur ve (45 sn'de bir) sesli uyarilir. */
function hizLimitiGoster(rota, ilerleme, hizMs) {
  const limit = hizLimitiBul(rota, ilerleme);
  $('hiz-sinir').hidden = limit == null;
  if (limit != null) $('hiz-sinir-deger').textContent = String(limit);
  const kmsa = Number.isFinite(hizMs) ? hizMs * 3.6 : 0;
  const asim = limit != null && kmsa > limit + HIZ_ASIM_TOLERANS_KMH;
  $('hiz-kutu').classList.toggle('hizli', asim);
  durum.hizAsimSayac = asim ? durum.hizAsimSayac + 1 : 0;
  if (durum.hizAsimSayac >= HIZ_ASIM_ARDISIK && Date.now() - durum.sonHizUyari > HIZ_UYARI_ARALIK_MS) {
    durum.sonHizUyari = Date.now();
    soyle(`Hız sınırı ${limit}. Hızınızı azaltın.`);
  }
}

/* ---------- Paneller: alt sayfa, sol cekmece, yol tarifi ---------- */

/** Alt sayfanin ayrintilarini acar / kapatir. */
function sayfaAc(ac) {
  $('alt').classList.toggle('acik', ac);
  $('sayfa-tutac').setAttribute('aria-expanded', String(ac));
  $('sayfa-tutac').setAttribute('aria-label', ac ? 'Ayrıntıları kapat' : 'Ayrıntıları aç');
}

/** Sol cekmeceyi acar / kapatir; kapaliyken odak alamaz (inert). */
function menuAc(ac) {
  $('cekmece').classList.toggle('acik', ac);
  $('cekmece').setAttribute('aria-hidden', String(!ac));
  $('cekmece').toggleAttribute('inert', !ac);
  $('perde').hidden = !ac;
  $('menu-ac').setAttribute('aria-expanded', String(ac));
  if (ac) $('menu-kapat').focus();
  else $('menu-ac').focus();
}

/** Ustteki manevra kartina dokununca siradaki donuslerin listesini acar / kapatir. */
function yolTarifiAc(ac) {
  durum.yolTarifiAcik = ac;
  $('yol-tarifi').hidden = !ac;
  $('manevra-ana').setAttribute('aria-expanded', String(ac));
  if (ac) yolTarifiYaz();
}

function yolTarifiYaz() {
  const liste = $('yol-tarifi');
  liste.replaceChildren();
  const rota = durum.rota;
  if (!rota) return;
  const bas = Math.max(0, durum.sonManevra);
  rota.manevralar.slice(bas + 1, bas + 13).forEach((m) => {
    liste.append(el('li', {}, el('span', { sinif: 'yt-mesafe', metin: mesafeYaz(Math.max(0, m.basM - durum.ilerleme)) }),
      el('span', { metin: buyukBasla(m.instruction) })));
  });
  if (!liste.children.length) liste.append(el('li', {}, el('span', { metin: 'Başka dönüş yok, hedefe kadar düz devam edin.' })));
}

/** Dikey surukleme: esik asilirsa yukari / asagi, hareketsiz dokunusta (ya da klavyede) dokun geri cagrisi. */
function dikeyKaydir(oge, { yukari, asagi, dokun }) {
  let bas = null;
  let tasindi = false;
  oge.addEventListener('pointerdown', (o) => { bas = o.clientY; tasindi = false; oge.setPointerCapture?.(o.pointerId); });
  oge.addEventListener('pointermove', (o) => { if (bas !== null && Math.abs(o.clientY - bas) > 10) tasindi = true; });
  oge.addEventListener('pointerup', (o) => {
    if (bas === null) return;
    const fark = o.clientY - bas;
    bas = null;
    if (tasindi && fark <= -30) yukari?.();
    else if (tasindi && fark >= 30) asagi?.();
    else if (!tasindi) dokun?.();
  });
  oge.addEventListener('pointercancel', () => { bas = null; });
  oge.addEventListener('click', (o) => { if (o.detail === 0) dokun?.(); });
}

/** Ekranin sol kenarindan saga cekince cekmeceyi acar, cekmeceyi sola cekince kapatir (dokunmatik). */
function menuKaydirmaKur() {
  let bas = null;
  let kaynak = '';
  document.addEventListener('pointerdown', (o) => {
    bas = null;
    if (o.pointerType !== 'touch') return;
    if ($('cekmece').classList.contains('acik')) [bas, kaynak] = [o.clientX, 'kapat'];
    else if (o.clientX < 18 && durum.mod !== 'nav') [bas, kaynak] = [o.clientX, 'ac'];
  }, { passive: true });
  document.addEventListener('pointermove', (o) => {
    if (bas === null) return;
    const dx = o.clientX - bas;
    if (kaynak === 'ac' && dx > 50) { menuAc(true); bas = null; }
    else if (kaynak === 'kapat' && dx < -50) { menuAc(false); bas = null; }
  }, { passive: true });
  document.addEventListener('pointerup', () => { bas = null; });
  document.addEventListener('pointercancel', () => { bas = null; });
}

/* ---------- Arka plan: ekran kilitliyken / uygulama aktif degilken ---------- */

let sessizSesOge = null;

/** 1 saniyelik sessiz ses (8 kHz, 8 bit, mono) uretir; mobil tarayicilar ses calan sayfayi arka planda daha az askiya alir. */
function sessizSesAdresi() {
  const ornek = 8000;
  const tampon = new ArrayBuffer(44 + ornek);
  const gorunum = new DataView(tampon);
  const yaz = (konum, metin) => [...metin].forEach((h, i) => gorunum.setUint8(konum + i, h.charCodeAt(0)));
  yaz(0, 'RIFF');
  gorunum.setUint32(4, 36 + ornek, true);
  yaz(8, 'WAVE');
  yaz(12, 'fmt ');
  gorunum.setUint32(16, 16, true);
  gorunum.setUint16(20, 1, true);
  gorunum.setUint16(22, 1, true);
  gorunum.setUint32(24, ornek, true);
  gorunum.setUint32(28, ornek, true);
  gorunum.setUint16(32, 1, true);
  gorunum.setUint16(34, 8, true);
  yaz(36, 'data');
  gorunum.setUint32(40, ornek, true);
  new Uint8Array(tampon, 44).fill(128);
  return URL.createObjectURL(new Blob([tampon], { type: 'audio/wav' }));
}

/**
 * Navigasyon suresince sayfayi canli tutmaya calisir: sessiz ses dongusu + medya oturumu (kilit ekraninda "Navigasyon"
 * gorunur). Tarayici kisitlari nedeniyle kesin degildir; en guvenli yol uygulama (yerel kabuk) surumudur.
 */
function arkaPlanKoru(ac) {
  try {
    if (ac) {
      if (!sessizSesOge) {
        sessizSesOge = new Audio(sessizSesAdresi());
        sessizSesOge.loop = true;
      }
      sessizSesOge.play().catch((hata) => console.warn('Arka plan sesi başlatılamadı', hata));
      if ('mediaSession' in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({ title: 'Navigasyon', artist: durum.hedef?.ad || 'HARITA', album: 'HARITA navigasyon' });
        navigator.mediaSession.playbackState = 'playing';
        // Kilit ekranindan duraklatma sesi kesmesin: oturum canli kalir
        for (const eylem of ['play', 'pause']) {
          navigator.mediaSession.setActionHandler(eylem, () => sessizSesOge?.play().catch((hata) => console.warn('Ses sürdürülemedi', hata)));
        }
      }
    } else {
      sessizSesOge?.pause();
      if ('mediaSession' in navigator) {
        navigator.mediaSession.playbackState = 'none';
        navigator.mediaSession.metadata = null;
      }
    }
  } catch (hata) {
    console.warn('Arka plan koruması kurulamadı', hata);
  }
}

/** Uygulamaya donuldugunde: ekran kilidi ve ses geri alinir, konum izleme canlandirilir, tek olcumle rota konumuna yetisilir. */
function onPlanaDonuldu() {
  if (durum.mod !== 'nav') return;
  ekranAcikTut(true);
  sessizSesOge?.play().catch((hata) => console.warn('Arka plan sesi sürdürülemedi', hata));
  if (durum.simAcik || !('geolocation' in navigator)) return;
  if (durum.izleme == null) konumIzlemeBaslat();
  navigator.geolocation.getCurrentPosition(olcumIsle, (hata) => console.warn('Dönüşte konum alınamadı', hata.message),
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 8000 });
}

/* ---------- Arama ---------- */

function sonuclariYaz(ozellikler) {
  const liste = $('sonuclar');
  liste.replaceChildren();
  if (!ozellikler.length) {
    planMesaj('Sonuç bulunamadı.', 'uyari');
    return;
  }
  planMesaj('');
  for (const f of ozellikler) {
    const o = f.properties || {};
    const [lon, lat] = f.geometry.coordinates;
    const ayrinti = [TUR_ETIKET[o.type] || o.type, o.district, o.city, o.state].filter(Boolean).join(', ');
    const dugme = el('button', { type: 'button' }, el('span', { sinif: 'ad', metin: o.name || 'Adsız' }), el('span', { sinif: 'ayrinti', metin: ayrinti }));
    dugme.addEventListener('click', () => hedefSec({ lat, lon, ad: o.name || 'Seçilen yer' }));
    liste.append(el('li', {}, dugme));
  }
}

const aramaYap = gecikmeli(async (q) => {
  const sira = ++aramaSirasi;
  if (q.trim().length < 2) {
    $('sonuclar').replaceChildren();
    return;
  }
  const c = durum.konum ? { lat: durum.konum.lat, lng: durum.konum.lon } : harita.getCenter();
  try {
    const v = await api(`/v1/arama?q=${encodeURIComponent(q.trim())}&limit=7&lat=${c.lat.toFixed(5)}&lon=${c.lng.toFixed(5)}`);
    if (sira === aramaSirasi) sonuclariYaz(v.features || []);
  } catch (hata) {
    console.warn('Arama başarısız', hata);
    if (sira === aramaSirasi) planMesaj(hata instanceof HataMesaji ? hata.message : 'Arama yapılamadı.', 'hata');
  }
}, 300);

/** Haritaya dokunulan noktayi hedef yapar; adini ters aramayla bulur. */
async function haritaDokunma(olay) {
  if (durum.mod === 'nav') return;
  if (alternatifDokunmasi(olay)) return;
  const { lat, lng } = olay.lngLat;
  const hedef = { lat, lon: lng, ad: 'Haritadan seçilen nokta' };
  hedefSec(hedef);
  try {
    const v = await api(`/v1/ters-arama?lat=${lat.toFixed(6)}&lon=${lng.toFixed(6)}`);
    const o = v.features?.[0]?.properties;
    if (o?.name && durum.duraklar.includes(hedef)) {
      hedef.ad = [o.name, o.housenumber].filter(Boolean).join(' ');
      sonYerEkle(hedef);
      duraklarListesiYaz();
    }
  } catch (hata) {
    console.warn('Ters arama başarısız', hata);
  }
}

/* ---------- Surum ---------- */

/** Son 3 surumu sag altta gosterir; en yeni surum ilk goruldugunde yesil, sonra normal renkte kalin. */
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

/* ---------- Baslangic ---------- */

async function sunucuYapilandirmasi() {
  try {
    const yanit = await fetch('yapilandirma.json', { cache: 'no-store' });
    return yanit.ok ? await yanit.json() : {};
  } catch (hata) {
    console.warn('Sunucu yapılandırması okunamadı', hata);
    return {};
  }
}

async function haritaYapilandirmasi() {
  try {
    const yap = await api('/v1/yapilandirma');
    const dolu = Object.fromEntries(Object.entries(yap).filter(([, v]) => v != null));
    return { ...varsayilanYapilandirma(), ...dolu };
  } catch (hata) {
    console.warn('Harita yapılandırması alınamadı, varsayılan kullanılıyor', hata);
    if (hata instanceof HataMesaji) planMesaj(hata.message, 'hata');
    return varsayilanYapilandirma();
  }
}

function olaylariBagla() {
  $('hedef-ara').addEventListener('input', (o) => {
    if (o.target.value.trim()) aramaYap(o.target.value);
    else { aramaSirasi += 1; kayitliYerleriYaz(); }
  });
  $('hedef-ara').addEventListener('focus', () => { if (!$('hedef-ara').value.trim() && durum.mod !== 'nav') kayitliYerleriYaz(); });
  $('varis-paylas').addEventListener('click', varisPaylasDegistir);
  $('varis-baglanti').addEventListener('click', paylasimBaglantisiniKopyala);
  $('ev-kaydet').addEventListener('click', () => hedefiKaydet('ev'));
  $('is-kaydet').addEventListener('click', () => hedefiKaydet('is'));
  yoldaTurleriYaz();
  $('hedef-ara').addEventListener('keydown', (o) => {
    if (o.key === 'Enter') $('sonuclar').querySelector('button')?.click();
  });
  document.querySelectorAll('#profil-segment button').forEach((d) => d.addEventListener('click', () => {
    if (durum.profil === d.dataset.profil) return;
    durum.profil = d.dataset.profil;
    ayarKaydet();
    arayuzGuncelle();
    if (durum.mod === 'onizleme') onizlemeHesapla();
  }));
  for (const kod of ['otoyol', 'ucret']) {
    $(`tercih-${kod}`).addEventListener('change', (o) => {
      durum.tercih[kod] = o.target.checked;
      ayarKaydet();
      if (durum.mod === 'onizleme') onizlemeHesapla();
    });
  }
  $('menu-ac').addEventListener('click', () => menuAc(true));
  $('menu-kapat').addEventListener('click', () => menuAc(false));
  $('perde').addEventListener('click', () => menuAc(false));
  document.addEventListener('keydown', (o) => { if (o.key === 'Escape' && $('cekmece').classList.contains('acik')) menuAc(false); });
  menuKaydirmaKur();
  dikeyKaydir($('sayfa-tutac'), { yukari: () => sayfaAc(true), asagi: () => sayfaAc(false), dokun: () => sayfaAc(!$('alt').classList.contains('acik')) });
  dikeyKaydir($('ozet').querySelector('.ozet-metin'), { yukari: () => sayfaAc(true), asagi: () => sayfaAc(false) });
  $('manevra-ana').addEventListener('click', () => yolTarifiAc(!durum.yolTarifiAcik));
  $('sim').addEventListener('change', (o) => {
    durum.simAcik = o.target.checked;
    ayarKaydet();
    arayuzGuncelle();
  });
  $('sim-hiz').addEventListener('change', (o) => {
    durum.simHiz = Number(o.target.value);
    ayarKaydet();
  });
  $('paylas').addEventListener('click', rotaPaylas);
  $('gpx-indir').addEventListener('click', gpxIndir);
  $('google-ac').addEventListener('click', googleAc);
  $('yandex-ac').addEventListener('click', yandexAc);
  $('gpx-yukle').addEventListener('change', (olay) => { gpxYukle(olay.target.files[0]); olay.target.value = ''; });
  $('konumum').addEventListener('click', () => {
    durum.ilkKonum = true;
    if (durum.konum) harita.flyTo({ center: [durum.konum.lon, durum.konum.lat], zoom: 15, duration: 800 });
    konumIzlemeBaslat();
  });
  $('katman').addEventListener('change', (o) => {
    durum.katmanKod = o.target.value;
    ayarKaydet();
    temaUygula();
    // Stil tamamen yenilenir; rota, hedef ve manevra katmanlari style.load ile geri eklenir
    harita.setStyle(stilKur(), { diff: false });
  });
  $('durak-ekle').addEventListener('click', () => {
    durum.durakEkle = !durum.durakEkle;
    arayuzGuncelle();
    if (durum.durakEkle) $('hedef-ara').focus();
  });
  $('baslat').addEventListener('click', () => { sesiAc(); navBaslat(); });
  $('ses-dene').addEventListener('click', sesiDene);
  document.addEventListener('pointerdown', sesiAc, { once: true, passive: true });
  $('iptal').addEventListener('click', hedefTemizle);
  $('bitir').addEventListener('click', () => navBitir(false));
  const sesDegistir = (acik) => {
    durum.ses = acik;
    if (!durum.ses && 'speechSynthesis' in window) speechSynthesis.cancel();
    ayarKaydet();
    arayuzGuncelle();
  };
  $('ses').addEventListener('click', () => sesDegistir(!durum.ses));
  $('ses-onay').addEventListener('change', (o) => sesDegistir(o.target.checked));
  $('ortala').addEventListener('click', () => {
    durum.takip = true;
    arayuzGuncelle();
    if (durum.konum) kameraGuncelle([durum.konum.lon, durum.konum.lat], durum.konum.yon, durum.konum.hiz);
  });
  $('sapma').addEventListener('click', () => {
    simDurum.sapmaAdim = 6;
  });
  // Kullanici haritayi elle kaydirirsa takip durur, "Ortala" ile geri gelir
  const takipBirak = (olay) => {
    if (durum.mod === 'nav' && olay.originalEvent && durum.takip) {
      durum.takip = false;
      arayuzGuncelle();
    }
  };
  harita.on('dragstart', takipBirak);
  harita.on('rotatestart', takipBirak);
  harita.on('click', haritaDokunma);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') onPlanaDonuldu();
  });
  new ResizeObserver(() => document.documentElement.style.setProperty('--alt-yukseklik', `${altYukseklik()}px`)).observe($('alt'));
}

/** "Otomatik" katmanda gun dogumu / batimi gecince haritayi 5 dakikada bir kontrol edip acik / koyu stile gecirir. */
function otoTemaIzle() {
  let son = aktifKatman().kod;
  setInterval(() => {
    if (durum.katmanKod !== 'oto') return;
    const simdi = aktifKatman().kod;
    if (simdi === son) return;
    son = simdi;
    temaUygula();
    harita.setStyle(stilKur(), { diff: false });
  }, 5 * 60 * 1000);
}

/** Cihazda Turkce ses yoksa bir kez uyarir (sesler tarayicida gec yuklenebilir). */
function sesDenetle() {
  if (!('speechSynthesis' in window)) {
    planMesaj('Bu tarayıcı sesli okuma desteklemiyor; talimatlar yalnız ekranda görünür.', 'uyari');
    return;
  }
  const denetle = () => {
    const sesler = speechSynthesis.getVoices();
    if (sesler.length && !turkceSes()) console.warn('Türkçe ses bulunamadı, varsayılan ses kullanılacak');
  };
  denetle();
  speechSynthesis.addEventListener('voiceschanged', denetle);
}

async function baslat() {
  const ayar = depoOku(NAV_DEPO);
  // Eski kayitta yalniz tema varsa (acik/koyu) karsilik gelen sokak katmanina cevir
  const eskiKatman = ayar.tema ? (ayar.tema === 'light' ? 'v-light' : 'v-dark') : 'oto';
  Object.assign(durum, {
    katmanKod: KATMANLAR.some((k) => k.kod === ayar.katmanKod) ? ayar.katmanKod : eskiKatman,
    tercih: { otoyol: Boolean(ayar.tercih?.otoyol), ucret: Boolean(ayar.tercih?.ucret) },
    profil: COSTING[ayar.profil] ? ayar.profil : 'araba',
    ses: ayar.ses !== false,
    simAcik: Boolean(ayar.simAcik),
    simHiz: Number(ayar.simHiz) || 50,
  });
  $('profil').value = durum.profil;
  $('tercih-otoyol').checked = durum.tercih.otoyol;
  $('tercih-ucret').checked = durum.tercih.ucret;
  $('sim').checked = durum.simAcik;
  $('sim-hiz').value = String(durum.simHiz);

  const deneme = depoOku(DENEME_DEPO);
  const sunucu = await sunucuYapilandirmasi();
  durum.api = deneme.api || VARSAYILAN_API;
  durum.sunucuAnahtar = ilkGecerliAnahtar(sunucu.anahtar);
  durum.anahtar = ilkGecerliAnahtar(deneme.anahtar, durum.sunucuAnahtar);
  durum.mtAnahtar = ilkGecerliAnahtar(deneme.mtAnahtar, sunucu.mtAnahtar);
  katmanSecimiDoldur();
  temaUygula();
  durum.yap = await haritaYapilandirmasi();

  harita = new maplibregl.Map({
    container: 'harita',
    style: stilKur(),
    center: [35.0, 39.0],
    zoom: 5.5,
    attributionControl: { compact: true },
  });
  harita.on('style.load', kaplamaKur);
  // 3D bina dugmesi: tema secili katmana uyar (uydu / karma katmanda koyu tema)
  harita.addControl(new UcBoyutKontrolu({ get tema() { const k = aktifKatman(); return k.tur === 'vektor' ? k.tema : 'dark'; } }), 'top-right');
  konumIsaretiKur();
  olaylariBagla();
  arayuzGuncelle();
  otoTemaIzle();
  surumGoster();
  sesDenetle();
  konumIzlemeBaslat();
  await baglantidanAc();
}

/**
 * Sayfa baglantiyla acildiysa duraklari hazirlar (baska uygulamalardan "bu adrese git" icin):
 *   navigasyon.html?duraklar=41.01,28.97;40.99,29.02&adlar=Market|Musteri&profil=motosiklet
 *   navigasyon.html?hedef=40.99,29.02&ad=Musteri
 *   navigasyon.html?baglanti=<Google / Yandex / Apple / Waze baglantisi>
 * sim=1 simulasyonu acar. Ses icin tarayici bir dokunus ister; navigasyon "Baslat" ile baslar.
 */
async function baglantidanAc() {
  const p = new URLSearchParams(location.search);
  if (COSTING[p.get('profil')]) {
    durum.profil = p.get('profil');
    $('profil').value = durum.profil;
  }
  if (p.get('sim') === '1') {
    durum.simAcik = true;
    $('sim').checked = true;
    arayuzGuncelle();
  }
  const adlar = (p.get('adlar') || p.get('ad') || '').split('|');
  let noktalar = [];
  const ham = p.get('duraklar') || p.get('hedef');
  if (ham) {
    noktalar = ham.split(';').map((s) => s.split(',').map(Number)).filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b)
      && Math.abs(a) <= 90 && Math.abs(b) <= 180).map(([lat, lon]) => ({ lat, lon }));
  } else if (/^[A-Za-z0-9]{8}$/.test(p.get('kod') || '')) {
    try {
      const v = await api(`/v1/paylasim/${p.get('kod')}`);
      noktalar = v.duraklar;
      if (COSTING[v.profil]) {
        durum.profil = v.profil;
        $('profil').value = v.profil;
      }
    } catch (hata) {
      console.warn('Paylasim kodu acilamadi', hata);
      planMesaj(hata?.kod === 404 ? 'Paylaşım bulunamadı ya da süresi doldu.' : 'Paylaşım açılamadı.', 'hata');
      return;
    }
  } else if (p.get('baglanti')) {
    try {
      noktalar = (await api(`/v1/baglanti/coz?adres=${encodeURIComponent(p.get('baglanti'))}`)).noktalar;
      // Baglantinin ilk noktasi cihazin bulundugu yerse (baslangic) durak sayilmaz
      if (noktalar.length > 1 && durum.konum && mesafeM([durum.konum.lon, durum.konum.lat], [noktalar[0].lon, noktalar[0].lat]) < 300) noktalar.shift();
    } catch (hata) {
      console.warn('Harita baglantisi cozulemedi', hata);
      planMesaj(hata instanceof HataMesaji ? hata.message : 'Bağlantı açılamadı.', 'hata');
      return;
    }
  }
  if (!noktalar.length) return;
  duraklariYukle(noktalar, adlar);
  // Onizleme mumkunse gercek konumdan baslasin: ilk GPS olcumu icin kisa sure beklenir
  if (!durum.konum) {
    planMesaj('Konum bekleniyor...');
    await konumBekle(6000);
  }
  await onizlemeHesapla();
}

/** Ilk konum olcumunu en fazla sureMs bekler (gelmezse devam edilir). */
function konumBekle(sureMs) {
  return new Promise((coz) => {
    const bas = Date.now();
    const bak = () => (durum.konum || Date.now() - bas > sureMs ? coz() : setTimeout(bak, 250));
    bak();
  });
}

baslat();
