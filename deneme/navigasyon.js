/**
 * HARITA navigasyon denemesi: hedef arama, Valhalla rotasi, adim adim Turkce sesli yonlendirme,
 * konum takibi, rotadan sapinca yeniden rota ve masaustunde denemek icin simulasyon.
 * Harita anahtari deneme sayfasiyla ayni tarayici kaydindan ya da sunucu yapilandirmasindan gelir.
 */
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/+esm';
import { layers, namedFlavor } from 'https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/+esm';

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
  katmanKod: 'v-dark',
  mtAnahtar: '',
  profil: 'araba',
  ses: true,
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
  cizim: { 'rota-tum': BOS, 'rota-kalan': BOS, hedef: BOS, 'manevra-nokta': BOS },
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
  depoYaz(NAV_DEPO, { katmanKod: durum.katmanKod, profil: durum.profil, ses: durum.ses, simAcik: durum.simAcik, simHiz: durum.simHiz });
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

/** Baslangictan sirayla duraklara rota ister. Baslangicta yon varsa Valhalla aracin gittigi yondeki yolu secer. */
async function rotaIste(baslangic, duraklar, ilkDurak = 0) {
  const bas = { lat: baslangic.lat, lon: baslangic.lon };
  if (Number.isFinite(baslangic.yon) && (baslangic.hiz ?? 0) > 2) Object.assign(bas, { heading: Math.round(baslangic.yon), heading_tolerance: 60 });
  const v = await api('/valhalla/route', {
    method: 'POST',
    body: JSON.stringify({
      locations: [bas, ...duraklar.map((d) => ({ lat: d.lat, lon: d.lon }))],
      costing: COSTING[durum.profil],
      directions_options: { language: 'tr-TR', units: 'kilometers' },
    }),
  });
  return rotaHazirla(v, ilkDurak);
}

/** Henuz ulasilmamis duraklar (yeniden rota ve baslangic icin). */
function kalanDuraklar() {
  return durum.duraklar.slice(durum.gecilenDurak);
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
  if (oncelikli) speechSynthesis.cancel();
  // Valhalla Turkce metinlerinde sayi ile birim bitisik gelebiliyor ("2kilometre"); okunurken ayrilir
  const konusma = new SpeechSynthesisUtterance(yolAdiDuzelt(metin).replace(/(\d)([a-zçğıöşü])/gi, '$1 $2'));
  konusma.lang = 'tr-TR';
  const ses = turkceSes();
  if (ses) konusma.voice = ses;
  konusma.onerror = (olay) => console.warn('Sesli okuma hatası', olay.error);
  speechSynthesis.speak(konusma);
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

/** Secili katman; MapTiler anahtari yoksa MapTiler katmanlari yerine koyu sokak katmani kullanilir. */
function aktifKatman() {
  const k = KATMANLAR.find((x) => x.kod === durum.katmanKod) || KATMANLAR[0];
  return k.tur !== 'vektor' && !durum.mtAnahtar ? KATMANLAR[0] : k;
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
    const gerekli = k.tur !== 'vektor' && !durum.mtAnahtar;
    const secenek = el('option', { value: k.kod, metin: gerekli ? `${k.ad} (MapTiler anahtarı gerekli)` : k.ad });
    if (gerekli) secenek.disabled = true;
    gruplar.get(k.grup).append(secenek);
  }
  gruplar.forEach((g) => sec.append(g));
  sec.value = aktifKatman().kod;
}

/** Rota, hedef ve manevra katmanlari; stil her degistiginde yeniden eklenir. */
function kaplamaKur() {
  for (const ad of Object.keys(durum.cizim)) {
    if (!harita.getSource(ad)) harita.addSource(ad, { type: 'geojson', data: durum.cizim[ad] });
  }
  const yuvarlak = { 'line-join': 'round', 'line-cap': 'round' };
  const kat = (tanim) => { if (!harita.getLayer(tanim.id)) harita.addLayer(tanim); };
  kat({ id: 'rota-tum', type: 'line', source: 'rota-tum', layout: yuvarlak,
    paint: { 'line-color': '#8B949E', 'line-opacity': 0.5, 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3, 18, 10] } });
  kat({ id: 'rota-kalan-kenar', type: 'line', source: 'rota-kalan', layout: yuvarlak,
    paint: { 'line-color': '#0B2A4A', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 6, 18, 17] } });
  kat({ id: 'rota-kalan', type: 'line', source: 'rota-kalan', layout: yuvarlak,
    paint: { 'line-color': '#58A6FF', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3.5, 18, 11] } });
  kat({ id: 'manevra-nokta', type: 'circle', source: 'manevra-nokta',
    paint: { 'circle-radius': 6, 'circle-color': '#FFFFFF', 'circle-stroke-color': '#58A6FF', 'circle-stroke-width': 3 } });
  // Duraklar: son durak (hedef) kirmizi, ara duraklar turuncu, gecilenler gri; ustunde sira numarasi
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
  $('baslat').hidden = mod !== 'onizleme';
  $('iptal').hidden = mod !== 'onizleme';
  $('bitir').hidden = !nav;
  $('ses').hidden = !nav;
  $('ortala').hidden = !nav || durum.takip;
  $('sapma').hidden = !(nav && durum.simAcik);
  $('sim-hiz-alan').hidden = !durum.simAcik;
  $('durak-ekle').hidden = mod !== 'onizleme';
  $('durak-ekle').textContent = durum.durakEkle ? 'Durak ekleniyor: arayın ya da dokunun' : 'Durak ekle';
  $('durak-ekle').classList.toggle('etkin', durum.durakEkle);
  $('ses').textContent = durum.ses ? 'Ses: açık' : 'Ses: kapalı';
  document.documentElement.style.setProperty('--alt-yukseklik', `${altYukseklik()}px`);
}

function ozetYaz(kalanSn, kalanM, hizMs) {
  $('kalan-sure').textContent = sureYaz(kalanSn);
  $('kalan-mesafe').textContent = mesafeYaz(kalanM);
  $('varis').textContent = saatYaz(new Date(Date.now() + kalanSn * 1000));
  $('hiz').textContent = Number.isFinite(hizMs) ? `${sayi(hizMs * 3.6)} km/sa` : '-';
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
  if (yolda) sesliYonlendir(rota, i, manevraM, k.hiz);
  ozetYaz(kalanSure(rota, o.ilerleme), kalanM, k.hiz);
  kameraGuncelle(gosterilen, yon, k.hiz);
}

function konumIzlemeBaslat() {
  if (!('geolocation' in navigator)) {
    planMesaj('Bu tarayıcı konum vermiyor; simülasyonu kullanabilirsiniz.', 'uyari');
    return;
  }
  if (durum.izleme != null) return;
  durum.izleme = navigator.geolocation.watchPosition(
    (olcum) => {
      if (durum.simAcik && durum.mod === 'nav') return;
      const c = olcum.coords;
      konumGeldi({
        lat: c.latitude, lon: c.longitude, dogruluk: c.accuracy,
        hiz: Number.isFinite(c.speed) ? c.speed : null,
        yon: Number.isFinite(c.heading) && (c.speed ?? 0) > 1 ? c.heading : null,
      });
    },
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
    const yeni = await rotaIste(k, kalanDuraklar(), durum.gecilenDurak);
    if (durum.mod !== 'nav') return;
    rotaAyarla(yeni);
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
    const rota = await rotaIste(baslangic, duraklar, ilkDurak);
    rotaAyarla(rota);
    durum.mod = 'onizleme';
    planMesaj(not, not ? 'uyari' : '');
    arayuzGuncelle();
    ozetYaz(rota.sure, rota.toplam, durum.konum?.hiz);
    rotayaSigdir(rota);
  } catch (hata) {
    console.warn('Rota alınamadı', hata);
    planMesaj(hata instanceof HataMesaji ? hata.message : 'Rota alınamadı.', 'hata');
  }
}

function hedefTemizle() {
  Object.assign(durum, { hedef: null, duraklar: [], gecilenDurak: 0, durakEkle: false, rota: null, mod: 'plan' });
  for (const ad of Object.keys(durum.cizim)) veriYaz(ad, BOS);
  $('hedef-ara').value = '';
  duraklarListesiYaz();
  planMesaj('');
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
  Object.assign(durum, { mod: 'nav', takip: true, sapmaSayac: 0, sonYenidenRota: 0 });
  arayuzGuncelle();
  ekranAcikTut(true);
  const ilk = durum.rota.manevralar[0];
  durum.soylenen.set(`${durum.rota.no}:0`, { uzak: true, yakin: true });
  soyle(`Navigasyon başladı. ${buyukBasla(ilk?.verbal_pre_transition_instruction || '')}`, true);
  if (durum.simAcik) simBaslat();
  else konumGeldi({ ...durum.konum });
}

/** Navigasyonu bitirir. Varildiysa hedef temizlenir, degilse rota onizlemesine donulur. */
function navBitir(varildi = false) {
  simDurdur();
  ekranAcikTut(false);
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
  const { lat, lng } = olay.lngLat;
  const hedef = { lat, lon: lng, ad: 'Haritadan seçilen nokta' };
  hedefSec(hedef);
  try {
    const v = await api(`/v1/ters-arama?lat=${lat.toFixed(6)}&lon=${lng.toFixed(6)}`);
    const o = v.features?.[0]?.properties;
    if (o?.name && durum.duraklar.includes(hedef)) {
      hedef.ad = [o.name, o.housenumber].filter(Boolean).join(' ');
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
  $('hedef-ara').addEventListener('input', (o) => aramaYap(o.target.value));
  $('hedef-ara').addEventListener('keydown', (o) => {
    if (o.key === 'Enter') $('sonuclar').querySelector('button')?.click();
  });
  $('profil').addEventListener('change', (o) => {
    durum.profil = o.target.value;
    ayarKaydet();
    if (durum.mod === 'onizleme') onizlemeHesapla();
  });
  $('sim').addEventListener('change', (o) => {
    durum.simAcik = o.target.checked;
    ayarKaydet();
    arayuzGuncelle();
  });
  $('sim-hiz').addEventListener('change', (o) => {
    durum.simHiz = Number(o.target.value);
    ayarKaydet();
  });
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
  $('baslat').addEventListener('click', navBaslat);
  $('iptal').addEventListener('click', hedefTemizle);
  $('bitir').addEventListener('click', () => navBitir(false));
  $('ses').addEventListener('click', () => {
    durum.ses = !durum.ses;
    if (!durum.ses && 'speechSynthesis' in window) speechSynthesis.cancel();
    ayarKaydet();
    arayuzGuncelle();
  });
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
    if (document.visibilityState === 'visible' && durum.mod === 'nav') ekranAcikTut(true);
  });
  new ResizeObserver(() => document.documentElement.style.setProperty('--alt-yukseklik', `${altYukseklik()}px`)).observe($('alt'));
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
  const eskiKatman = ayar.tema === 'light' ? 'v-light' : 'v-dark';
  Object.assign(durum, {
    katmanKod: KATMANLAR.some((k) => k.kod === ayar.katmanKod) ? ayar.katmanKod : eskiKatman,
    profil: COSTING[ayar.profil] ? ayar.profil : 'araba',
    ses: ayar.ses !== false,
    simAcik: Boolean(ayar.simAcik),
    simHiz: Number(ayar.simHiz) || 50,
  });
  $('profil').value = durum.profil;
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
  konumIsaretiKur();
  olaylariBagla();
  arayuzGuncelle();
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
  durum.duraklar = noktalar.map((n, i) => ({ ...n, ad: adlar[i] || (i === noktalar.length - 1 ? 'Hedef' : `${i + 1}. durak`) }));
  durum.hedef = durum.duraklar.at(-1);
  duraklariCiz();
  duraklarListesiYaz();
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
