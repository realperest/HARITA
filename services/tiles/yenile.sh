#!/bin/bash
# Aylik karo yenileme zamanlayicisi. Her ayin 1'inde 05:00'ten (Turkiye saati = 02:00 UTC) itibaren:
#   1) en yeni Protomaps yapisindan Turkiye kesitini yan dosyaya indirir (yayin etkilenmez),
#   2) boyut, pmtiles yapisi ve ornek karolarla dogrular,
#   3) eski dosyayi .yedek olarak ayirip yenisini yerine koyar, sunucuyu yeniden baslatir (acilis-kontrol.sh sonucu denetler).
# Basarisiz olursa canli dosyaya dokunulmaz; 3 saat arayla en cok 4 kez denenir. Yedek bir sonraki yenilemeye kadar durur.
set -uo pipefail
. /ortak.sh

KONTROL_ARALIK="${YENILEME_KONTROL_SANIYE:-600}"
DENEME_ARALIK="${YENILEME_DENEME_BEKLEME_SANIYE:-10800}"
EN_COK_DENEME=4

ay_simdi() { date -u +%Y%m; }

zamanlama_geldi() {
    local gun saat
    gun=$((10#$(date -u +%d)))
    saat=$((10#$(date -u +%H)))
    [ "$gun" -gt 1 ] || [ "$saat" -ge 2 ]
}

yenile() {
    local adres
    rm -f "$YENI" "$YENI.indiriliyor"
    adres=$(en_yeni_yapi) || { gunluk "HATA: Protomaps yapisi bulunamadi"; return 1; }
    gunluk "Yeni kesit indiriliyor: $adres kutu=$KAPSAM_KUTUSU en fazla z$MAKS_YAKINLASTIRMA"
    if ! pmtiles extract "$adres" "$YENI.indiriliyor" --bbox="$KAPSAM_KUTUSU" --maxzoom="$MAKS_YAKINLASTIRMA"; then
        gunluk "HATA: indirme basarisiz"
        rm -f "$YENI.indiriliyor"
        return 1
    fi
    mv "$YENI.indiriliyor" "$YENI"
    if ! karo_dogrula "$YENI" "$DOSYA"; then
        gunluk "Yeni dosya dogrulamayi gecemedi; canli dosya degismedi."
        rm -f "$YENI"
        return 1
    fi
    # Yedek: bir onceki yedek silinir, mevcut dosya yedek olur, yeni dosya yerine gecer (hepsi ayni hacimde, yeniden adlandirma)
    if [ -d "$VERI_DIZINI/paket" ]; then
        rm -rf "$VERI_DIZINI/paket.yedek"
        cp -al "$VERI_DIZINI/paket" "$VERI_DIZINI/paket.yedek" || gunluk "UYARI: paket yedegi alinamadi"
    fi
    rm -f "$YEDEK"
    mv "$DOSYA" "$YEDEK"
    mv "$YENI" "$DOSYA"
    echo "$(date -u +%Y%m%d%H%M%S)" > "$BEKLEYEN"
    gunluk "Yeni dosya yerine kondu, yedek: $YEDEK. Sunucu yeniden baslatiliyor; acilis kontrolu sonucu denetleyecek."
    sunucuyu_yeniden_baslat
    # Konteyner yeniden baslayana kadar bekle (bu surec ile birlikte sonlanir)
    sleep 600
    return 0
}

# Ilk acilista damga yoksa bu ay "yapildi" sayilir; ilk yenileme bir sonraki ayin 1'inde olur.
[ -f "$DAMGA" ] || ay_simdi > "$DAMGA"

while true; do
    if [ "${YENILEME_ZORLA:-0}" = "1" ] || { [ "$(cat "$DAMGA" 2>/dev/null)" != "$(ay_simdi)" ] && zamanlama_geldi; }; then
        deneme_ay=$(cut -d: -f1 "$DENEME" 2>/dev/null || true)
        deneme_say=$(cut -d: -f2 "$DENEME" 2>/dev/null || echo 0)
        [ "$deneme_ay" = "$(ay_simdi)" ] || deneme_say=0
        son_deneme=$(stat -c %Y "$DENEME" 2>/dev/null || echo 0)
        bekle_bitti=$(( $(date +%s) - son_deneme >= DENEME_ARALIK ))
        if [ "${YENILEME_ZORLA:-0}" = "1" ] || { [ "$deneme_say" -lt "$EN_COK_DENEME" ] && [ "$bekle_bitti" = 1 ]; }; then
            deneme_say=$((deneme_say + 1))
            echo "$(ay_simdi):$deneme_say" > "$DENEME"
            gunluk "Aylik karo yenilemesi basliyor (deneme $deneme_say/$EN_COK_DENEME)"
            yenile || gunluk "Karo yenilemesi basarisiz; $((DENEME_ARALIK / 3600)) saat sonra yeniden denenecek."
        fi
    fi
    [ "${YENILEME_ZORLA:-0}" = "1" ] && [ -n "${YENILEME_TEK_SEFER:-}" ] && exit 0
    sleep "$KONTROL_ARALIK"
done
