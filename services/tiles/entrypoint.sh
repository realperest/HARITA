#!/bin/bash
# Karo servisi baslaticisi: veri yoksa Protomaps gunluk yapisindan Turkiye kesitini indirir, sonra pmtiles + nginx'i calistirir.
# Aylik yenileme (yenile.sh) ve yenileme sonrasi acilis kontrolu (acilis-kontrol.sh) arka planda calisir.
set -euo pipefail
. /ortak.sh

export IZINLI_KOKEN_REGEX="${IZINLI_KOKEN_REGEX:-.*}"

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
echo "$PMTILES_PID" > /tmp/pmtiles.pid
nginx -g 'daemon off;' &
NGINX_PID=$!

# Aylik yenileme zamanlayicisi (AYLIK_YENILEME=False ile kapatilir) ve yenileme sonrasi acilis kontrolu
if [ "${AYLIK_YENILEME:-True}" = "True" ]; then
    /yenile.sh &
fi
/acilis-kontrol.sh &

# Biri olurse konteyner kapanir ve Coolify yeniden baslatir
wait -n "$PMTILES_PID" "$NGINX_PID"
echo "[karo] Bir surec durdu, kapaniyor." >&2
exit 1
