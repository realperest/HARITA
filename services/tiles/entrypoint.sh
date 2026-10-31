#!/bin/bash
# Karo servisi baslaticisi: veri yoksa Protomaps gunluk yapisindan Turkiye kesitini indirir, sonra pmtiles + nginx'i calistirir.
set -euo pipefail

VERI_DIZINI=/veri
DOSYA="$VERI_DIZINI/turkiye.pmtiles"
KAPSAM_KUTUSU="${KAPSAM_KUTUSU:-25.6,35.8,44.9,42.2}"
MAKS_YAKINLASTIRMA="${MAKS_YAKINLASTIRMA:-15}"
export IZINLI_KOKEN_REGEX="${IZINLI_KOKEN_REGEX:-.*}"

# En yeni gunluk yapiyi bul (bugunden geriye 10 gun denenir)
en_yeni_yapi() {
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

if [ ! -s "$DOSYA" ]; then
    echo "[karo] Turkiye karolari yok, indiriliyor (bir kereye mahsus, birkac GB)..."
    adres=$(en_yeni_yapi) || { echo "[karo] HATA: Protomaps yapisi bulunamadi." >&2; exit 1; }
    echo "[karo] Kaynak: $adres kutu: $KAPSAM_KUTUSU en fazla z$MAKS_YAKINLASTIRMA"
    pmtiles extract "$adres" "$DOSYA.indiriliyor" --bbox="$KAPSAM_KUTUSU" --maxzoom="$MAKS_YAKINLASTIRMA"
    mv "$DOSYA.indiriliyor" "$DOSYA"
    echo "[karo] Indirme tamam."
fi

# Cevrimdisi il paketleri arka planda (CEVRIMDISI_PAKET=False ile kapatilir)
if [ "${CEVRIMDISI_PAKET:-True}" = "True" ]; then
    /paketle.sh &
fi

envsubst '${IZINLI_KOKEN_REGEX}' < /etc/nginx/harita.conf.template > /etc/nginx/nginx.conf

# TileJSON (/tiles/turkiye.json) icin genel adres gerekir
pmtiles serve "$VERI_DIZINI" --port=8081 --public-url="${KARO_GENEL_ADRESI:-http://localhost:8080}/tiles" &
PMTILES_PID=$!
nginx -g 'daemon off;' &
NGINX_PID=$!

# Biri olurse konteyner kapanir ve Coolify yeniden baslatir
wait -n "$PMTILES_PID" "$NGINX_PID"
echo "[karo] Bir surec durdu, kapaniyor." >&2
exit 1
