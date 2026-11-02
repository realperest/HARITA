/**
 * HARITA 3D bina katmani: HARITA karolarindaki "buildings" katmanini yukseltilmis bloklar olarak cizer.
 * Bagimliligi yoktur; herhangi bir MapLibre haritasiyla calisir (haritaOlustur ile kurulan vektor harita).
 *
 * Kullanim:
 *   import { ucBoyutDegistir, UcBoyutKontrolu } from './harita-3d.js';
 *   harita.addControl(new UcBoyutKontrolu({ tema: 'dark' }), 'top-right');   // hazir dugme
 *   ucBoyutDegistir(harita, { tema: 'dark' });                               // kendi dugmeniz icin: yeni durumu (acik mi) dondurur
 *
 * Kapaliyken hicbir katman, istek ya da animasyon yoktur; bina verisi zaten vektor karonun icinde gelir.
 * Not: Yalniz vektor haritada calisir (uydu/hibrit gibi resim haritalarda "buildings" kaynagi yoktur).
 * Veri notu (OSM): Turkiye'de binalarin yalniz bir kismi gercek yukseklige sahiptir (Ankara ~%27, Istanbul ~%4,
 * Izmir ~%1; 01.11.2026 olcumu). Yuksekligi olmayan ya da 3 m'den dusuk olan binalar VARSAYILAN_YUKSEKLIK ile cizilir.
 */

export const AYAR = {
  KAYNAK: 'harita',
  KAYNAK_KATMANI: 'buildings',
  KATMAN: 'bina-3d',
  EN_AZ_YAKINLIK: 14,
  VARSAYILAN_YUKSEKLIK: 9,
  EN_AZ_GECERLI_YUKSEKLIK: 3,
  EGIM: 55,
  SURE_MS: 600,
};

const RENKLER = { dark: '#313a47', black: '#262c36', light: '#cfcac0', white: '#dcdcdc', grayscale: '#b5b5b5' };

/** Bir binanin cizilecek yuksekligi (m): gecerli yukseklik varsa o, yoksa varsayilan. Katmandaki ifadeyle ayni kural. */
export function binaYuksekligi(ozellikler, varsayilan = AYAR.VARSAYILAN_YUKSEKLIK) {
  const h = ozellikler && typeof ozellikler.height === 'number' ? ozellikler.height : 0;
  return h >= AYAR.EN_AZ_GECERLI_YUKSEKLIK ? h : varsayilan;
}

/** fill-extrusion katman tanimi. tema: Protomaps tema adi (dark | light | white | grayscale | black). */
export function katmanTanimi({ tema = 'light', varsayilan = AYAR.VARSAYILAN_YUKSEKLIK } = {}) {
  const yukseklik = ['coalesce', ['get', 'height'], 0];
  return {
    id: AYAR.KATMAN,
    type: 'fill-extrusion',
    source: AYAR.KAYNAK,
    'source-layer': AYAR.KAYNAK_KATMANI,
    minzoom: AYAR.EN_AZ_YAKINLIK,
    paint: {
      'fill-extrusion-color': RENKLER[tema] || RENKLER.light,
      'fill-extrusion-height': ['case', ['>=', yukseklik, AYAR.EN_AZ_GECERLI_YUKSEKLIK], yukseklik, varsayilan],
      'fill-extrusion-base': ['coalesce', ['get', 'min_height'], 0],
      'fill-extrusion-opacity': 0.9,
      'fill-extrusion-vertical-gradient': true,
    },
  };
}

/** Harita 3D'yi destekliyor mu (HARITA vektor kaynagi var mi)? */
export function kullanilabilir(harita) {
  return !!harita.getSource(AYAR.KAYNAK);
}

/** 3D katman su an acik mi? */
export function acikMi(harita) {
  return !!harita.getLayer(AYAR.KATMAN);
}

/** Duz (2D) bina dolgu katmanlarinin gorunurlugunu degistirir; ust uste binmesin diye 3D acikken gizlenir. */
function duzBinalariGoster(harita, goster) {
  harita.getStyle().layers
    .filter((k) => k['source-layer'] === AYAR.KAYNAK_KATMANI && k.type === 'fill')
    .forEach((k) => harita.setLayoutProperty(k.id, 'visibility', goster ? 'visible' : 'none'));
}

/** 3D binalari acar ve haritayi egir. Vektor kaynak yoksa hicbir sey yapmaz ve false doner. */
export function ucBoyutAc(harita, { tema = 'light', varsayilan, egim = AYAR.EGIM, sure = AYAR.SURE_MS } = {}) {
  if (!kullanilabilir(harita)) return false;
  if (!acikMi(harita)) {
    const ilkYazi = harita.getStyle().layers.find((k) => k.type === 'symbol');
    harita.addLayer(katmanTanimi({ tema, varsayilan }), ilkYazi ? ilkYazi.id : undefined);
    duzBinalariGoster(harita, false);
  }
  harita.easeTo({ pitch: egim, duration: sure });
  return true;
}

/** 3D binalari kapatir: harita duzlesir, animasyon bitince katman kaldirilir. */
export function ucBoyutKapat(harita, { sure = AYAR.SURE_MS } = {}) {
  if (!acikMi(harita)) return;
  harita.easeTo({ pitch: 0, duration: sure });
  setTimeout(() => {
    if (harita.getPitch() > 0.5 || !harita.getLayer(AYAR.KATMAN)) return;
    harita.removeLayer(AYAR.KATMAN);
    duzBinalariGoster(harita, true);
  }, sure + 50);
}

/** Acik ise kapatir, kapali ise acar. Donus: yeni durum (true = 3D acik). */
export function ucBoyutDegistir(harita, secenek = {}) {
  if (acikMi(harita)) {
    ucBoyutKapat(harita, secenek);
    return false;
  }
  return ucBoyutAc(harita, secenek);
}

const KUTU_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" '
  + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/>'
  + '<path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>';

/** MapLibre kontrolu: harita kosesine kucuk bir "3D bina" simge dugmesi ekler. */
export class UcBoyutKontrolu {
  constructor(secenek = {}) {
    this.secenek = secenek;
  }

  onAdd(harita) {
    this.harita = harita;
    this.kap = document.createElement('div');
    this.kap.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    this.dugme = document.createElement('button');
    this.dugme.type = 'button';
    this.dugme.innerHTML = KUTU_SVG;
    this.dugme.addEventListener('click', () => this.degistir());
    this.kap.appendChild(this.dugme);
    this.acik = false;
    this.yaz(false);
    /* Stil degisince (setStyle) katmanlar silinir: 3D istenmisse yeni stilde yeniden kurulur, kurulamazsa kapali gosterilir. */
    this.stilOlayi = () => {
      if (!this.acik) return;
      if (ucBoyutAc(this.harita, { ...this.secenek, sure: 0 })) return;
      this.harita.setPitch(0);
      this.yaz(false);
    };
    harita.on('style.load', this.stilOlayi);
    return this.kap;
  }

  onRemove() {
    this.harita.off('style.load', this.stilOlayi);
    this.kap.remove();
    this.harita = null;
  }

  degistir() {
    if (!kullanilabilir(this.harita)) {
      this.dugme.title = '3D bina icin vektor harita gerekli';
      return;
    }
    this.yaz(ucBoyutDegistir(this.harita, this.secenek));
  }

  /** Dugmenin gorunumunu ve erisilebilir metnini gunceller. */
  yaz(acik) {
    this.acik = acik;
    const metin = '3D bina: ' + (acik ? 'acik' : 'kapali');
    this.dugme.title = metin;
    this.dugme.setAttribute('aria-label', metin);
    this.dugme.setAttribute('aria-pressed', acik ? 'true' : 'false');
    this.dugme.style.color = acik ? '#ff8a00' : '';
  }
}
