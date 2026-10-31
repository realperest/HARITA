/**
 * HARITA veritabani araci: tablo listesi, veri (arama, filtre, siralama, sayfalama, CSV), yapi ve salt okunur SQL.
 * Yonetim anahtari yalniz bu sekmenin oturum deposunda (sessionStorage) tutulur; koda ve depoya yazilmaz.
 */

const VARSAYILAN_API = 'https://harita-api.89.45.45.152.sslip.io';
const OTURUM_ANAHTARI = 'harita-vt-oturum';
const ZAMAN_TIPLERI = /^(timestamp|date)/;
const SAYISAL_TIPLER = /^(smallint|integer|bigint|numeric|double precision|real)/;
const ORNEK_SQL = [
  ['Proje özeti', 'SELECT p.id, p.ad, p.dakika_limiti, count(a.id) AS anahtar_adedi FROM proje p LEFT JOIN proje_anahtar a ON a.proje_id = p.id GROUP BY p.id ORDER BY p.id'],
  ['İl başına mahalle', "SELECT i.ad AS il, count(*) AS mahalle FROM yerlesim m JOIN yerlesim i ON i.id = (SELECT ust_id FROM yerlesim WHERE id = m.ust_id) WHERE m.tur_id = 3 GROUP BY i.ad ORDER BY mahalle DESC LIMIT 20"],
  ['Yer türü dağılımı', 'SELECT t.kod, count(*) AS adet FROM yer_isareti y JOIN tnm_yer_turu t ON t.id = y.tur_id WHERE y.aktif_mi GROUP BY t.kod ORDER BY adet DESC'],
];

const durum = {
  api: VARSAYILAN_API,
  anahtar: '',
  tablolar: [],
  gorunumGoster: false,
  ara: '',
  secili: null,
  sekme: 'veri',
  sayfa: 1,
  boyut: 50,
  veriAra: '',
  kolon: '',
  islem: 'icerir',
  deger: '',
  sirala: '',
  yon: 'artan',
  son: null,
};

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

const sayi = (n, basamak = 0) => Number(n).toLocaleString('tr-TR', { minimumFractionDigits: basamak, maximumFractionDigits: basamak });

function boyutYaz(bayt) {
  if (bayt >= 1024 ** 3) return `${sayi(bayt / 1024 ** 3, 1)} GB`;
  if (bayt >= 1024 ** 2) return `${sayi(bayt / 1024 ** 2, 1)} MB`;
  return `${sayi(bayt / 1024, 0)} KB`;
}

/** ISO zaman metnini GG.AA.YYYY SS:DD bicimine cevirir (yalniz zaman tipli kolonlarda). */
function zamanYaz(metin) {
  const e = /^(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d):(\d\d))?/.exec(metin);
  if (!e) return metin;
  return e[4] ? `${e[3]}.${e[2]}.${e[1]} ${e[4]}:${e[5]}` : `${e[3]}.${e[2]}.${e[1]}`;
}

class HataMesaji extends Error {}

/* ---------- API ---------- */

async function api(yol, secenek = {}) {
  let yanit;
  try {
    yanit = await fetch(`${durum.api.replace(/\/$/, '')}${yol}`, {
      ...secenek,
      headers: { 'X-Yonetim-Anahtari': durum.anahtar, 'Content-Type': 'application/json' },
    });
  } catch (hata) {
    console.error('Ağ hatası', hata);
    throw new HataMesaji('Sunucuya ulaşılamadı.');
  }
  if (yanit.status === 401) {
    oturumKapat();
    throw new HataMesaji('Yönetim anahtarı geçersiz.');
  }
  if (!yanit.ok) {
    let neden = 'İstek başarısız oldu.';
    try {
      neden = (await yanit.json()).detail || neden;
    } catch (hata) {
      console.warn('Hata gövdesi okunamadı', hata);
    }
    throw new HataMesaji(typeof neden === 'string' ? neden : 'İstek başarısız oldu.');
  }
  return yanit.json();
}

/* ---------- Oturum ---------- */

function oturumYaz() {
  try {
    sessionStorage.setItem(OTURUM_ANAHTARI, JSON.stringify({ api: durum.api, anahtar: durum.anahtar }));
  } catch (hata) {
    console.warn('Oturum kaydedilemedi', hata);
  }
}

function oturumOku() {
  try {
    return JSON.parse(sessionStorage.getItem(OTURUM_ANAHTARI) || '{}');
  } catch (hata) {
    console.warn('Oturum okunamadı', hata);
    return {};
  }
}

function oturumKapat() {
  durum.anahtar = '';
  try {
    sessionStorage.removeItem(OTURUM_ANAHTARI);
  } catch (hata) {
    console.warn('Oturum silinemedi', hata);
  }
  $('uygulama').hidden = true;
  $('cikis').hidden = true;
  $('giris-alani').hidden = false;
}

async function girisYap(olay) {
  olay.preventDefault();
  durum.api = $('api-adres').value.trim() || VARSAYILAN_API;
  durum.anahtar = $('yonetim-anahtar').value.trim();
  $('giris-mesaj').textContent = 'Bağlanılıyor...';
  $('giris-mesaj').className = 'mesaj';
  try {
    await api('/yonetim/veritabani/ozet');
    oturumYaz();
    $('yonetim-anahtar').value = '';
    await uygulamaAc();
  } catch (hata) {
    $('giris-mesaj').textContent = hata instanceof HataMesaji ? hata.message : 'Giriş yapılamadı.';
    $('giris-mesaj').className = 'mesaj hata';
  }
}

/* ---------- Ozet ve tablo listesi ---------- */

async function uygulamaAc() {
  $('giris-alani').hidden = true;
  $('uygulama').hidden = false;
  $('cikis').hidden = false;
  await ozetYukle();
}

async function ozetYukle() {
  try {
    const [ozet, tablolar] = await Promise.all([api('/yonetim/veritabani/ozet'), api('/yonetim/veritabani/tablolar')]);
    durum.tablolar = tablolar;
    const kutu = (etiket, deger, alt = '') => el('div', { sinif: 'ozet-kutu' }, el('div', { sinif: 'etiket', metin: etiket }),
      el('div', { sinif: 'deger', metin: deger }), el('div', { sinif: 'alt', metin: alt, title: alt }));
    $('ozet').replaceChildren(kutu('Motor', 'PostgreSQL', ozet.motor), kutu('Boyut', boyutYaz(ozet.boyut_bayt)),
      kutu('Tablo', sayi(ozet.tablo_adedi)), kutu('Toplam satır', sayi(ozet.toplam_satir)));
    tabloListesiYaz();
  } catch (hata) {
    $('ozet').replaceChildren(el('p', { sinif: 'mesaj hata', metin: hata instanceof HataMesaji ? hata.message : 'Veritabanı bilgisi alınamadı.' }));
  }
}

function tabloListesiYaz() {
  const liste = $('tablo-liste');
  const ara = durum.ara.toLowerCase();
  liste.replaceChildren();
  durum.tablolar
    .filter((t) => (durum.gorunumGoster || t.tur === 'tablo') && t.ad.toLowerCase().includes(ara))
    .forEach((t) => {
      const dugme = el('button', { type: 'button', sinif: `tablo-oge${durum.secili === t.ad && durum.sekme !== 'sql' ? ' secili' : ''}`, title: boyutYaz(t.boyut_bayt) },
        el('span', { metin: t.ad }), el('span', { sinif: t.satir === null ? 'gorunum' : 'sayi', metin: t.satir === null ? 'görünüm' : sayi(t.satir) }));
      dugme.addEventListener('click', () => tabloAc(t.ad));
      liste.append(el('li', {}, dugme));
    });
  $('sql-ac').classList.toggle('secili', durum.sekme === 'sql');
}

/* ---------- Tablo icerigi ---------- */

function tabloAc(ad) {
  durum.secili = ad;
  durum.sekme = 'veri';
  Object.assign(durum, { sayfa: 1, veriAra: '', kolon: '', islem: 'icerir', deger: '', sirala: '', yon: 'artan' });
  icerikCiz();
}

function sekmeSatiri(baslik) {
  const dugme = (kod, ad) => {
    const d = el('button', { type: 'button', sinif: `sekme${durum.sekme === kod ? ' aktif' : ''}`, metin: ad });
    d.addEventListener('click', () => { durum.sekme = kod; icerikCiz(); });
    return d;
  };
  return el('div', { sinif: 'baslik-satir' }, el('h2', { metin: baslik }),
    el('div', { sinif: 'sekmeler' }, dugme('veri', 'Veriler'), dugme('yapi', 'Yapı'), dugme('sql', 'SQL')));
}

async function icerikCiz() {
  tabloListesiYaz();
  const kap = $('icerik');
  if (durum.sekme === 'sql') return sqlCiz(kap);
  if (!durum.secili) { kap.replaceChildren(el('p', { sinif: 'soluk', metin: 'Soldan bir tablo seçin.' })); return; }
  if (durum.sekme === 'yapi') return yapiCiz(kap);
  return veriCiz(kap);
}

function sorguMetni() {
  const p = new URLSearchParams({ sayfa: durum.sayfa, boyut: durum.boyut, yon: durum.yon });
  if (durum.veriAra) p.set('ara', durum.veriAra);
  if (durum.kolon) {
    p.set('kolon', durum.kolon);
    p.set('islem', durum.islem);
    if (!['bos', 'dolu'].includes(durum.islem)) p.set('deger', durum.deger);
  }
  if (durum.sirala) p.set('sirala', durum.sirala);
  return p.toString();
}

function hucreYaz(deger, kolon) {
  const td = el('td', { sinif: 'hucre' });
  if (deger === null) { td.append(el('span', { sinif: 'bos', metin: 'NULL' })); return td; }
  if (deger === '[gizli]') { td.append(el('span', { sinif: 'gizli', metin: '[gizli]' })); return td; }
  const kimlik = kolon.birincil || kolon.yabanci || /(^|_)id$/.test(kolon.ad);
  if (SAYISAL_TIPLER.test(kolon.tip) && !kimlik) {
    td.className = 'hucre sayisal';
    td.textContent = /^-?\d+(\.\d+)?$/.test(deger) ? sayi(deger, deger.includes('.') ? Math.min(deger.split('.')[1].length, 6) : 0) : deger;
  } else if (SAYISAL_TIPLER.test(kolon.tip)) {
    td.className = 'hucre sayisal';
    td.textContent = deger;
  } else if (ZAMAN_TIPLERI.test(kolon.tip)) {
    td.textContent = zamanYaz(deger);
  } else {
    td.textContent = deger;
    if (deger.length > 60) td.classList.add('uzun');
  }
  return td;
}

function tabloyuCiz(veri, siralamaCb) {
  const bas = el('tr');
  veri.kolonlar.forEach((k) => {
    const th = el('th', { title: 'Sıralamak için tıklayın' });
    if (k.birincil) th.append(el('span', { sinif: 'rozet', metin: 'PK' }));
    if (k.yabanci) th.append(el('span', { sinif: 'rozet yabanci', metin: 'FK', title: `-> ${k.yabanci}` }));
    th.append(k.ad + (durum.sirala === k.ad ? (durum.yon === 'azalan' ? ' ▼' : ' ▲') : ''), el('span', { sinif: 'tip', metin: k.tip }));
    if (siralamaCb) th.addEventListener('click', () => siralamaCb(k.ad));
    bas.append(th);
  });
  const govde = el('tbody');
  veri.satirlar.forEach((satir) => govde.append(el('tr', {}, ...satir.map((d, i) => hucreYaz(d, veri.kolonlar[i])))));
  return el('div', { sinif: 'tablo-kap' }, el('table', { sinif: 'veri' }, el('thead', {}, bas), govde));
}

async function veriCiz(kap) {
  kap.replaceChildren(sekmeSatiri(`public.${durum.secili}`), el('p', { sinif: 'soluk', metin: 'Yükleniyor...' }));
  let veri;
  try {
    veri = await api(`/yonetim/veritabani/tablo/${encodeURIComponent(durum.secili)}/veri?${sorguMetni()}`);
  } catch (hata) {
    kap.replaceChildren(sekmeSatiri(`public.${durum.secili}`), el('p', { sinif: 'mesaj hata', metin: hata instanceof HataMesaji ? hata.message : 'Veri alınamadı.' }));
    return;
  }
  durum.son = veri;
  const ara = el('input', { sinif: 'girdi', type: 'search', placeholder: 'Tüm kolonlarda ara', 'aria-label': 'Tüm kolonlarda ara', value: durum.veriAra });
  const kolonSec = el('select', { sinif: 'girdi', 'aria-label': 'Filtre kolonu' }, el('option', { value: '', metin: 'Filtre kolonu' }));
  veri.kolonlar.forEach((k) => kolonSec.append(el('option', { value: k.ad, metin: k.ad })));
  kolonSec.value = durum.kolon;
  const islemSec = el('select', { sinif: 'girdi', 'aria-label': 'Filtre işlemi' });
  [['icerir', 'içerir'], ['=', '='], ['<>', '≠'], ['>', '>'], ['<', '<'], ['>=', '≥'], ['<=', '≤'], ['bos', 'boş'], ['dolu', 'dolu']]
    .forEach(([v, ad]) => islemSec.append(el('option', { value: v, metin: ad })));
  islemSec.value = durum.islem;
  const deger = el('input', { sinif: 'girdi', type: 'text', placeholder: 'Değer', 'aria-label': 'Filtre değeri', value: durum.deger });
  const boyutSec = el('select', { sinif: 'girdi', 'aria-label': 'Sayfa boyutu' });
  [25, 50, 100, 200].forEach((b) => boyutSec.append(el('option', { value: String(b), metin: `${b} satır` })));
  boyutSec.value = String(durum.boyut);
  const uygula = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'Filtrele' });
  const temizle = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'Temizle' });
  const csv = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'CSV indir (bu sayfa)' });
  const filtreUygula = () => {
    Object.assign(durum, { veriAra: ara.value.trim(), kolon: kolonSec.value, islem: islemSec.value, deger: deger.value, sayfa: 1 });
    veriCiz(kap);
  };
  uygula.addEventListener('click', filtreUygula);
  [ara, deger].forEach((g) => g.addEventListener('keydown', (o) => { if (o.key === 'Enter') filtreUygula(); }));
  temizle.addEventListener('click', () => { Object.assign(durum, { veriAra: '', kolon: '', islem: 'icerir', deger: '', sayfa: 1 }); veriCiz(kap); });
  boyutSec.addEventListener('change', () => { durum.boyut = Number(boyutSec.value); durum.sayfa = 1; veriCiz(kap); });
  csv.addEventListener('click', () => csvIndir(veri));

  const sayfaAdedi = Math.max(1, Math.ceil(veri.toplam / veri.boyut));
  const onceki = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'Önceki' });
  const sonraki = el('button', { type: 'button', sinif: 'dugme ikincil', metin: 'Sonraki' });
  onceki.disabled = durum.sayfa <= 1;
  sonraki.disabled = durum.sayfa >= sayfaAdedi;
  onceki.addEventListener('click', () => { durum.sayfa -= 1; veriCiz(kap); });
  sonraki.addEventListener('click', () => { durum.sayfa += 1; veriCiz(kap); });

  kap.replaceChildren(
    sekmeSatiri(`public.${durum.secili}`),
    el('div', { sinif: 'arac-satir' }, ara, kolonSec, islemSec, deger, uygula, temizle, boyutSec, csv),
    tabloyuCiz(veri, (kolon) => {
      durum.yon = durum.sirala === kolon && durum.yon === 'artan' ? 'azalan' : 'artan';
      durum.sirala = kolon;
      veriCiz(kap);
    }),
    el('div', { sinif: 'sayfa-satir' }, onceki, el('span', { sinif: 'mono', metin: `Sayfa ${sayi(durum.sayfa)} / ${sayi(sayfaAdedi)} · ${sayi(veri.toplam)} satır` }), sonraki),
  );
}

function csvIndir(veri) {
  const kacis = (d) => (d === null ? '' : `"${String(d).replaceAll('"', '""')}"`);
  const satirlar = [veri.kolonlar.map((k) => kacis(k.ad)).join(';'), ...veri.satirlar.map((s) => s.map(kacis).join(';'))];
  const blob = new Blob([`﻿${satirlar.join('\r\n')}`], { type: 'text/csv;charset=utf-8' });
  const baglanti = el('a', { href: URL.createObjectURL(blob), download: `${veri.tablo}_sayfa${veri.sayfa}.csv` });
  document.body.append(baglanti);
  baglanti.click();
  baglanti.remove();
  setTimeout(() => URL.revokeObjectURL(baglanti.href), 1000);
}

/* ---------- Yapi ---------- */

async function yapiCiz(kap) {
  kap.replaceChildren(sekmeSatiri(`public.${durum.secili}`), el('p', { sinif: 'soluk', metin: 'Yükleniyor...' }));
  try {
    const yapi = await api(`/yonetim/veritabani/tablo/${encodeURIComponent(durum.secili)}/yapi`);
    const bas = el('tr', {}, ...['Kolon', 'Tip', 'Boş olabilir', 'Varsayılan', 'Anahtar'].map((b) => el('th', { metin: b })));
    const govde = el('tbody');
    yapi.kolonlar.forEach((k) => {
      const anahtar = el('td');
      if (k.birincil) anahtar.append(el('span', { sinif: 'rozet', metin: 'PK' }));
      if (k.yabanci) anahtar.append(el('span', { sinif: 'rozet yabanci', metin: 'FK' }), ` ${k.yabanci}`);
      govde.append(el('tr', {}, el('td', { sinif: 'hucre', metin: k.ad }), el('td', { sinif: 'hucre', metin: k.tip }),
        el('td', { metin: k.bos_olabilir ? 'evet' : 'hayır' }), el('td', { sinif: 'hucre', metin: k.varsayilan || '' }), anahtar));
    });
    const dizinler = el('tbody');
    yapi.dizinler.forEach((d) => dizinler.append(el('tr', {}, el('td', { sinif: 'hucre', metin: d.ad }), el('td', { sinif: 'hucre uzun', metin: d.tanim }))));
    kap.replaceChildren(sekmeSatiri(`public.${durum.secili}`),
      el('div', { sinif: 'tablo-kap' }, el('table', { sinif: 'veri' }, el('thead', {}, bas), govde)),
      el('h3', { metin: 'Dizinler' }),
      el('div', { sinif: 'tablo-kap' }, el('table', { sinif: 'veri' }, el('thead', {}, el('tr', {}, el('th', { metin: 'Ad' }), el('th', { metin: 'Tanım' }))), dizinler)));
  } catch (hata) {
    kap.replaceChildren(sekmeSatiri(`public.${durum.secili}`), el('p', { sinif: 'mesaj hata', metin: hata instanceof HataMesaji ? hata.message : 'Yapı alınamadı.' }));
  }
}

/* ---------- SQL ---------- */

function sqlCiz(kap) {
  const girdi = el('textarea', { sinif: 'sql-girdi', spellcheck: 'false', 'aria-label': 'SQL sorgusu', placeholder: 'SELECT ... (yalnız okuma; en fazla 1.000 satır)' });
  const calistir = el('button', { type: 'button', sinif: 'dugme', metin: 'Çalıştır (Ctrl+Enter)' });
  const sonuc = el('div');
  const ornekler = el('div', { sinif: 'ornekler' });
  ORNEK_SQL.forEach(([ad, sorgu]) => {
    const d = el('button', { type: 'button', sinif: 'dugme ikincil', metin: ad });
    d.addEventListener('click', () => { girdi.value = sorgu; });
    ornekler.append(d);
  });
  const calistirFn = async () => {
    sonuc.replaceChildren(el('p', { sinif: 'soluk', metin: 'Çalışıyor...' }));
    try {
      const v = await api('/yonetim/veritabani/sql', { method: 'POST', body: JSON.stringify({ sorgu: girdi.value }) });
      const kolonlar = v.kolonlar.map((ad) => ({ ad, tip: 'text', birincil: false, yabanci: null }));
      sonuc.replaceChildren(
        el('p', { sinif: 'soluk mono', metin: `${sayi(v.satirlar.length)} satır${v.kesildi ? ' (ilk 1.000 satır gösteriliyor)' : ''}` }),
        v.kolonlar.length ? tabloyuCiz({ kolonlar, satirlar: v.satirlar }, null) : el('p', { sinif: 'soluk', metin: 'Sonuç yok.' }));
    } catch (hata) {
      sonuc.replaceChildren(el('p', { sinif: 'mesaj hata', metin: hata instanceof HataMesaji ? hata.message : 'Sorgu çalıştırılamadı.' }));
    }
  };
  calistir.addEventListener('click', calistirFn);
  girdi.addEventListener('keydown', (o) => { if (o.key === 'Enter' && (o.ctrlKey || o.metaKey)) calistirFn(); });
  kap.replaceChildren(el('div', { sinif: 'baslik-satir' }, el('h2', { metin: 'SQL komutu' }), el('span', { sinif: 'soluk', metin: 'Salt okunur: yalnız SELECT / WITH' })),
    ornekler, girdi, el('div', { sinif: 'arac-satir' }, calistir), sonuc);
}

/* ---------- Surum ve baslangic ---------- */

async function surumGoster() {
  const kutu = $('surum');
  try {
    const liste = (await (await fetch('surum.json', { cache: 'no-store' })).json()).slice(0, 3);
    liste.forEach((s, i) => kutu.append(el('div', { sinif: i === 0 ? 'yeni' : '', metin: `${s.surum} ${s.not}` })));
  } catch (hata) {
    console.warn('Sürüm bilgisi okunamadı', hata);
  }
}

function baslat() {
  $('api-adres').value = VARSAYILAN_API;
  $('giris-form').addEventListener('submit', girisYap);
  $('cikis').addEventListener('click', oturumKapat);
  $('tablo-ara').addEventListener('input', (o) => { durum.ara = o.target.value; tabloListesiYaz(); });
  $('gorunum-goster').addEventListener('change', (o) => { durum.gorunumGoster = o.target.checked; tabloListesiYaz(); });
  $('sql-ac').addEventListener('click', () => { durum.sekme = 'sql'; icerikCiz(); });
  surumGoster();
  const kayit = oturumOku();
  if (kayit.anahtar) {
    durum.api = kayit.api || VARSAYILAN_API;
    durum.anahtar = kayit.anahtar;
    uygulamaAc().catch(() => oturumKapat());
  } else {
    $('giris-alani').hidden = false;
  }
}

baslat();
