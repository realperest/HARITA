#!/bin/bash
# Karo servisi ortak islevleri (entrypoint.sh, yenile.sh ve acilis-kontrol.sh tarafindan kaynak alinir).

VERI_DIZINI="${VERI_DIZINI:-/veri}"
DOSYA="$VERI_DIZINI/turkiye.pmtiles"
YEDEK="$VERI_DIZINI/turkiye.pmtiles.yedek"
YENI="$VERI_DIZINI/turkiye.pmtiles.yeni"
BEKLEYEN="$VERI_DIZINI/.karo_degisim_bekliyor"
DAMGA="$VERI_DIZINI/.karo_son_ay"
DENEME="$VERI_DIZINI/.karo_deneme"
KAPSAM_KUTUSU="${KAPSAM_KUTUSU:-25.6,35.8,44.9,42.2}"
MAKS_YAKINLASTIRMA="${MAKS_YAKINLASTIRMA:-15}"
# Yeni dosyanin boyutu mevcut dosyaya gore bu yuzde araliginda olmali (yarim ya da bozuk indirmeyi eler)
KARO_EN_AZ_ORAN="${KARO_EN_AZ_ORAN:-80}"
KARO_EN_COK_ORAN="${KARO_EN_COK_ORAN:-250}"
# Dogrulamada okunacak karolar (z/x/y): Istanbul ve Ankara, z10
KONTROL_KAROLARI="${KONTROL_KAROLARI:-10/594/383 10/605/388}"

gunluk() {
    echo "[karo $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# En yeni gunluk yapiyi bul (bugunden geriye 10 gun denenir)
en_yeni_yapi() {
    local gun tarih adres
    for gun in $(seq 0 10); do
        tarih=$(date -u -d "-${gun} day" +%Y%m%d)
        adres="https://build.protomaps.com/${tarih}.pmtiles"
        if curl -fsI --max-time 20 "$adres" > /dev/null; then
            echo "$adres"
            return 0
        fi
    done
    return 1
}

# karo_dogrula YENI_DOSYA [MEVCUT_DOSYA]: boyut orani, pmtiles yapi denetimi ve ornek karolarin okunmasi. 0 = gecti.
karo_dogrula() {
    local yeni="$1" eski="${2:-}" boyut eski_boyut oran kontrol bayt
    [ -s "$yeni" ] || { gunluk "DOGRULAMA: yeni dosya yok ya da bos"; return 1; }
    boyut=$(stat -c %s "$yeni")
    if [ -n "$eski" ] && [ -s "$eski" ]; then
        eski_boyut=$(stat -c %s "$eski")
        oran=$((boyut * 100 / eski_boyut))
        if [ "$oran" -lt "$KARO_EN_AZ_ORAN" ] || [ "$oran" -gt "$KARO_EN_COK_ORAN" ]; then
            gunluk "DOGRULAMA: boyut orani %$oran (izinli %$KARO_EN_AZ_ORAN-%$KARO_EN_COK_ORAN), yeni=$boyut eski=$eski_boyut"
            return 1
        fi
    fi
    if ! timeout 3600 pmtiles verify "$yeni" > /dev/null 2>&1; then
        gunluk "DOGRULAMA: pmtiles verify basarisiz"
        return 1
    fi
    for kontrol in $KONTROL_KAROLARI; do
        IFS=/ read -r z x y <<< "$kontrol"
        bayt=$(pmtiles tile "$yeni" "$z" "$x" "$y" 2>/dev/null | wc -c)
        if [ "$bayt" -lt 200 ]; then
            gunluk "DOGRULAMA: $kontrol karosu bos ya da okunamadi ($bayt bayt)"
            return 1
        fi
    done
    gunluk "DOGRULAMA: tamam (boyut $boyut bayt)"
    return 0
}

# Calisan karo sunucusunu durdurur; entrypoint kapanir ve Coolify konteyneri yeniden baslatir.
sunucuyu_yeniden_baslat() {
    kill "$(cat /tmp/pmtiles.pid 2>/dev/null)" 2>/dev/null || gunluk "UYARI: pmtiles serve sureci bulunamadi"
}
