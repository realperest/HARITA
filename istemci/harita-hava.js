/**
 * HARITA hava durumu katmani: RainViewer yagmur radari (anahtarsiz, son ~1 saat animasyonlu) + haritanin ortasindaki konumun
 * hava karti (HARITA servisi: POST /v1/yol/hava, Open-Meteo). MotoConvoy'daki radar.js ve hava.js'in MapLibre kontrolu olarak
 * paketlenmis halidir. Bagimliligi yoktur; herhangi bir MapLibre haritasiyla calisir.
 *
 * Kullanim:
 *   import { HavaKontrolu } from './harita-hava.js';
 *   harita.addControl(new HavaKontrolu({ havaGetir: (lat, lon) => api('/v1/yol/hava', { method: 'POST', body: JSON.stringify({ noktalar: [[lat, lon], [lat + 0.0001, lon]] }) }) }), 'top-left');
 *
 * Kapaliyken hicbir katman, istek ya da animasyon yoktur. Dugme radar ve hava kartini birlikte acip kapatir.
 * Not: RainViewer en fazla 7. yakinlastirma duzeyinde veri verir; daha yakinda ayni karo buyutulur. Ucretsiz surumde
 * yalniz gecmis kareler vardir (tahmin karesi yok).
 */

export const AYAR = {
  RADAR_API: 'https://api.rainviewer.com/public/weather-maps.json',
  KARE_SAYISI: 6,
  KARE_MS: 700,
  SON_KARE_MS: 1800,
  RADAR_YENILE_MS: 5 * 60 * 1000,
  SAYDAMLIK: 0.7,
  GECIS_MS: 600,
  MAKS_YAKIN: 7,
  ZAMAN_ASIMI_MS: 10000,
  STIL_DENEME: 20,
  STIL_BEKLEME_MS: 250,
  HAVA_YENILE_MS: 5 * 60 * 1000,
  HAVA_HATA_MS: 2 * 60 * 1000,
  HAVA_TASIMA_M: 8000,
};

const UYARI_METNI = {
  firtina: 'Fırtına', kar: 'Kar', buzlanma: 'Buzlanma riski', kuvvetli_yagis: 'Kuvvetli yağış', kuvvetli_ruzgar: 'Kuvvetli rüzgâr', sis: 'Sis',
};

const SVG = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
  + 'stroke-linecap="round" stroke-linejoin="round"><path d="M7 18a4 4 0 0 1-.6-7.96A5.5 5.5 0 0 1 17 8.5a4.75 4.75 0 0 1 .5 9.5z"/>'
  + '<path d="M9 21l1-2M13 21l1-2M17 21l1-2"/></svg>';

/** API cevabindan son N gecmis radar karesini ({zaman: ms, adres: karo sablonu}) cikarir; gecersiz cevapta bos dizi doner. */
export function radarKareleri(json, adet = AYAR.KARE_SAYISI) {
  if (!json || !json.host || !json.radar || !Array.isArray(json.radar.past)) return [];
  return json.radar.past.slice(-adet).filter((k) => k && k.path && typeof k.time === 'number')
    .map((k) => ({ zaman: k.time * 1000, adres: `${json.host}${k.path}/256/{z}/{x}/{y}/2/1_1.png` }));
}

/** Iki nokta arasi mesafe (metre, haversine). */
export function mesafeM(a, b) {
  const R = 6371000;
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

/** Servis noktasini ekranda gosterilecek metinlere cevirir; tahmin yoksa null. */
export function havaOzeti(nokta) {
  if (!nokta || !nokta.tahmin_var || typeof nokta.sicaklik_c !== 'number') return null;
  let ana = `${Math.round(nokta.sicaklik_c)} °C`;
  if (nokta.durum) ana += `, ${nokta.durum}`;
  const parca = [];
  if (typeof nokta.ruzgar_kmh === 'number') {
    let ruzgar = `Rüzgâr ${Math.round(nokta.ruzgar_kmh)} km/s`;
    if (typeof nokta.ruzgar_hamle_kmh === 'number' && nokta.ruzgar_hamle_kmh - nokta.ruzgar_kmh >= 10) ruzgar += ` (hamle ${Math.round(nokta.ruzgar_hamle_kmh)})`;
    parca.push(ruzgar);
  }
  if (typeof nokta.yagis_olasiligi === 'number') parca.push(`Yağış olasılığı %${Math.round(nokta.yagis_olasiligi)}`);
  if (typeof nokta.yagis_mm === 'number' && nokta.yagis_mm > 0) parca.push(`Yağış ${(Math.round(nokta.yagis_mm * 10) / 10).toFixed(1).replace('.', ',')} mm`);
  const uyarilar = (nokta.uyarilar || []).map((u) => UYARI_METNI[u]).filter(Boolean);
  return { ana, detay: parca.join(', '), uyarilar };
}

/** MapLibre kontrolu: kose dugmesi + radar animasyonu + zaman cizelgesi + hava karti. secenek.havaGetir(lat, lon) -> HARITA /v1/yol/hava cevabi. */
export class HavaKontrolu {
  constructor(secenek = {}) {
    this.secenek = secenek;
    this.acik = false;
    this.kareler = [];
    this.sira = 0;
    this.zamanlayici = null;
    this.yenile = null;
    this.havaSon = null;
    this.havaIstek = 0;
    this.ozet = null;
    this.radarYagis = null;
    this.radarIstek = 0;
    this.radarResimleri = new Map();
  }

  onAdd(harita) {
    this.harita = harita;
    this.kap = document.createElement('div');
    this.kap.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    this.dugme = document.createElement('button');
    this.dugme.type = 'button';
    this.dugme.innerHTML = SVG;
    this.dugme.addEventListener('click', () => this.degistir());
    this.kap.appendChild(this.dugme);
    this.yaz(false);

    this.panel = document.createElement('div');
    this.panel.className = 'hava-panel';
    this.panel.hidden = true;
    this.panel.innerHTML = '<div class="hava-kart"><div class="hava-satir"><span class="hava-etiket">HAVA</span><b class="hava-ana"></b></div>'
      + '<div class="hava-detay"></div><div class="hava-uyari" hidden></div><div class="hava-radar" hidden></div></div>'
      + '<div class="hava-zaman" hidden><div class="hava-iz"><div class="hava-imlec"></div></div><div class="hava-saatler"></div></div>';
    harita.getContainer().appendChild(this.panel);

    /* setStyle katmanlari siler: radar istenmisse yeni stilde yeniden kurulur. */
    this.stilOlayi = () => { if (this.acik) this.radarYenile().catch((e) => console.warn('Radar yeniden kurulamadi', e)); };
    this.hareketOlayi = () => { if (this.acik) { this.havaGuncelle(); this.radarNoktasi(); } };
    harita.on('style.load', this.stilOlayi);
    harita.on('moveend', this.hareketOlayi);
    return this.kap;
  }

  onRemove() {
    this.kapat();
    this.harita.off('style.load', this.stilOlayi);
    this.harita.off('moveend', this.hareketOlayi);
    this.panel.remove();
    this.kap.remove();
    this.harita = null;
  }

  /** Dugmenin gorunumunu ve erisilebilir metnini gunceller. */
  yaz(acik) {
    this.acik = acik;
    const metin = `Hava durumu ve radar: ${acik ? 'açık' : 'kapalı'}`;
    this.dugme.title = metin;
    this.dugme.setAttribute('aria-label', metin);
    this.dugme.setAttribute('aria-pressed', acik ? 'true' : 'false');
    this.dugme.style.color = acik ? '#ff8a00' : '';
  }

  async degistir() {
    if (this.acik) { this.kapat(); return; }
    this.yaz(true);
    this.panel.hidden = false;
    this.havaSon = null;
    this.havaGuncelle();
    try {
      await this.radarAc();
    } catch (hata) {
      console.warn('Radar açılamadı', hata);
      this.kapat();
      this.dugme.title = 'Hava durumu şu an alınamadı';
    }
  }

  kapat() {
    this.yaz(false);
    this.radarDurdur();
    this.katmanlariSil();
    this.kareler = [];
    this.havaIstek += 1;
    this.radarIstek += 1;
    this.ozet = null;
    this.radarYagis = null;
    if (this.panel) { this.panel.hidden = true; this.panel.querySelector('.hava-zaman').hidden = true; }
  }

  /* ---- Radar ---- */

  kimlik(i) { return `hava-radar-${i}`; }

  katmanlariSil() {
    const h = this.harita;
    if (!h || !h.getStyle()) return;
    for (let i = 0; i < AYAR.KARE_SAYISI; i += 1) {
      if (h.getLayer(this.kimlik(i))) h.removeLayer(this.kimlik(i));
      if (h.getSource(this.kimlik(i))) h.removeSource(this.kimlik(i));
    }
  }

  katmanlariEkle(liste) {
    liste.forEach((k, i) => {
      this.harita.addSource(this.kimlik(i), {
        type: 'raster', tiles: [k.adres], tileSize: 256, maxzoom: AYAR.MAKS_YAKIN,
        attribution: '<a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>',
      });
      this.harita.addLayer({ id: this.kimlik(i), type: 'raster', source: this.kimlik(i),
        paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-opacity-transition': { duration: AYAR.GECIS_MS, delay: 0 } } });
    });
  }

  /* Stil henuz yuklenmediyse ("Style is not done loading") ekleyebilene kadar kisa araliklarla dener (en cok ~5 sn). */
  async katmanlariBekleyerekEkle(liste) {
    let sonHata = null;
    for (let i = 0; i < AYAR.STIL_DENEME; i += 1) {
      if (!this.acik) return;
      try {
        this.katmanlariSil();
        this.katmanlariEkle(liste);
        return;
      } catch (hata) {
        if (!/not done loading/i.test(String(hata && hata.message))) throw hata;
        sonHata = hata;
        await new Promise((coz) => setTimeout(coz, AYAR.STIL_BEKLEME_MS));
      }
    }
    throw sonHata;
  }

  async radarGetir() {
    const kontrol = new AbortController();
    const t = setTimeout(() => kontrol.abort(), AYAR.ZAMAN_ASIMI_MS);
    try {
      const yanit = await fetch(AYAR.RADAR_API, { signal: kontrol.signal });
      if (!yanit.ok) throw new Error(`Radar HTTP ${yanit.status}`);
      return radarKareleri(await yanit.json());
    } finally {
      clearTimeout(t);
    }
  }

  async radarYenile() {
    const liste = await this.radarGetir();
    if (!this.acik) return;
    if (!liste.length) throw new Error('Radar karesi yok');
    if (this.zamanlayici) { clearTimeout(this.zamanlayici); this.zamanlayici = null; }
    await this.katmanlariBekleyerekEkle(liste);
    if (!this.acik) { this.katmanlariSil(); return; }
    this.kareler = liste;
    this.sira = 0;
    this.zamanKur(liste.length);
    this.oynat();
    this.radarNoktasi();
  }

  async radarAc() {
    await this.radarYenile();
    if (!this.acik) return;
    this.yenile = setInterval(() => this.radarYenile().catch((e) => console.warn('Radar yenilenemedi', e)), AYAR.RADAR_YENILE_MS);
  }

  radarDurdur() {
    if (this.zamanlayici) { clearTimeout(this.zamanlayici); this.zamanlayici = null; }
    if (this.yenile) { clearInterval(this.yenile); this.yenile = null; }
  }

  yuzde(sira, adet) { return adet > 1 ? (sira / (adet - 1)) * 100 : 100; }

  /* Zaman cizelgesi: kare basina bir isaret, sonuncusu "simdi"; imlec kareler arasinda kayar. */
  zamanKur(adet) {
    const kutu = this.panel.querySelector('.hava-zaman');
    const iz = kutu.querySelector('.hava-iz');
    iz.querySelectorAll('.hava-nokta').forEach((n) => n.remove());
    const saatler = kutu.querySelector('.hava-saatler');
    saatler.textContent = '';
    this.kareler.forEach((k, i) => {
      const e = document.createElement('span');
      e.textContent = new Date(k.zaman).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false });
      e.style.left = `${this.yuzde(i, adet)}%`;
      saatler.appendChild(e);
    });
    for (let i = 0; i < adet; i += 1) {
      const n = document.createElement('i');
      n.className = `hava-nokta${i === adet - 1 ? ' simdi' : ''}`;
      n.style.left = `${this.yuzde(i, adet)}%`;
      iz.insertBefore(n, iz.firstChild);
    }
    kutu.hidden = false;
  }

  imlecKoy(sira, adet) {
    const imlec = this.panel.querySelector('.hava-imlec');
    const basaDondu = sira === 0;
    imlec.classList.toggle('aniden', basaDondu);
    if (basaDondu) void imlec.offsetWidth;
    imlec.style.left = `${this.yuzde(sira, adet)}%`;
    this.panel.querySelectorAll('.hava-saatler span').forEach((e, i) => e.classList.toggle('aktif', i === sira));
  }

  /* Siradaki kareyi gosterir, oncekini gizler ve bir sonraki gecisi planlar. */
  oynat() {
    if (!this.acik || !this.kareler.length) return;
    const son = this.kareler.length - 1;
    for (let i = 0; i <= son; i += 1) {
      if (this.harita.getLayer(this.kimlik(i))) this.harita.setPaintProperty(this.kimlik(i), 'raster-opacity', i === this.sira ? AYAR.SAYDAMLIK : 0);
    }
    this.imlecKoy(this.sira, this.kareler.length);
    const bekle = this.sira === son ? AYAR.SON_KARE_MS : AYAR.KARE_MS;
    this.sira = this.sira === son ? 0 : this.sira + 1;
    this.zamanlayici = setTimeout(() => this.oynat(), bekle);
  }

  /* ---- Hava karti ---- */

  /* Karti ozet (saatlik tahmin) ve radar gozlemiyle birlikte cizer. Tahmin bir model ongorusudur; radar o an gercekten
     yagis gorunup gorunmedigini gosterir. Ikisi celisirse radar satiri uyari olarak one cikar. */
  kartGoster(sonuc) {
    if (sonuc !== undefined) this.ozet = sonuc;
    const kart = this.panel.querySelector('.hava-kart');
    const radar = kart.querySelector('.hava-radar');
    const yagisVar = this.radarYagis === true;
    if (!this.acik || (!this.ozet && this.radarYagis === null)) { kart.hidden = true; return; }
    kart.querySelector('.hava-ana').textContent = this.ozet ? this.ozet.ana : 'Tahmin alınamadı';
    kart.querySelector('.hava-detay').textContent = this.ozet ? this.ozet.detay : '';
    const uyarilar = this.ozet ? this.ozet.uyarilar : [];
    const uyari = kart.querySelector('.hava-uyari');
    uyari.textContent = uyarilar.join(', ');
    uyari.hidden = uyarilar.length === 0;
    radar.hidden = this.radarYagis === null;
    radar.textContent = yagisVar ? 'Radar: bu noktada şu an yağış görünüyor' : 'Radar: bu noktada yağış görünmüyor';
    radar.classList.toggle('yagis', yagisVar);
    kart.classList.toggle('uyari-var', uyarilar.length > 0 || yagisVar);
    kart.hidden = false;
  }

  /* Radar karesinin haritanin ortasindaki pikseli: yagis ekosu var mi (true/false); resim alinamazsa null. */
  async radarNoktasi() {
    if (!this.acik || !this.kareler.length) return;
    const istek = ++this.radarIstek;
    const c = this.harita.getCenter();
    const z = AYAR.MAKS_YAKIN;
    const n = 2 ** z;
    const xf = ((c.lng + 180) / 360) * n;
    const enlem = (c.lat * Math.PI) / 180;
    const yf = ((1 - Math.asinh(Math.tan(enlem)) / Math.PI) / 2) * n;
    const adres = this.kareler[this.kareler.length - 1].adres.replace('{z}', z).replace('{x}', Math.floor(xf)).replace('{y}', Math.floor(yf));
    let sonuc = null;
    try {
      const resim = await this.radarResmi(adres);
      const tuval = document.createElement('canvas');
      tuval.width = 256;
      tuval.height = 256;
      const cizim = tuval.getContext('2d', { willReadFrequently: true });
      cizim.drawImage(resim, 0, 0);
      const px = Math.min(253, Math.max(2, Math.floor((xf % 1) * 256)));
      const py = Math.min(253, Math.max(2, Math.floor((yf % 1) * 256)));
      const veri = cizim.getImageData(px - 2, py - 2, 5, 5).data;
      sonuc = false;
      for (let i = 3; i < veri.length; i += 4) if (veri[i] > 40) { sonuc = true; break; }
    } catch (hata) {
      console.warn('Radar noktası okunamadı', hata);
    }
    if (istek !== this.radarIstek || !this.acik) return;
    this.radarYagis = sonuc;
    this.kartGoster();
  }

  /* Radar karosunu (CORS acik) yukler; ayni adres tekrar istenmez. */
  radarResmi(adres) {
    if (this.radarResimleri.size > 12) this.radarResimleri.clear();
    if (!this.radarResimleri.has(adres)) {
      this.radarResimleri.set(adres, new Promise((coz, red) => {
        const r = new Image();
        r.crossOrigin = 'anonymous';
        r.onload = () => coz(r);
        r.onerror = () => { this.radarResimleri.delete(adres); red(new Error('Radar karosu yüklenemedi')); };
        r.src = adres;
      }));
    }
    return this.radarResimleri.get(adres);
  }

  /* Haritanin ortasindaki konumun havasi; sure dolmadikca ve konum 8 km'den az degistiyse yeniden sormaz. */
  async havaGuncelle() {
    if (!this.acik || !this.secenek.havaGetir) return;
    const c = this.harita.getCenter();
    const konum = { lat: c.lat, lon: c.lng };
    const simdi = Date.now();
    const o = this.havaSon;
    if (o && simdi - o.t < o.bekle && mesafeM(o, konum) < AYAR.HAVA_TASIMA_M) return;
    this.havaSon = { t: simdi, ...konum, bekle: AYAR.HAVA_YENILE_MS };
    const istek = ++this.havaIstek;
    try {
      const veri = await this.secenek.havaGetir(konum.lat, konum.lon);
      if (istek === this.havaIstek) this.kartGoster(havaOzeti((veri.noktalar || [])[0]) || null);
    } catch (hata) {
      console.warn('Hava bilgisi alınamadı', hata);
      this.havaSon.bekle = AYAR.HAVA_HATA_MS;
      if (istek === this.havaIstek) this.kartGoster(null);
    }
  }
}
