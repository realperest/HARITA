#!/bin/bash
# Arama servisi baslaticisi: dizin yoksa gezegen dokumunden ULKE_KODLARI icin uretir (uzun surer), sonra Photon'u sunar.
set -euo pipefail

cd /veri
ULKE_KODLARI="${ULKE_KODLARI:-TR}"
DIL_KODLARI="${DIL_KODLARI:-tr,en}"
PHOTON_BELLEK="${PHOTON_BELLEK:-2g}"
DOKUM_ADRESI="${DOKUM_ADRESI:-https://download1.graphhopper.com/public/photon-dump-planet-1.0-latest.jsonl.zst}"

if [ ! -f /veri/.hazir ]; then
    # Ortak sunucuda bellek tepesini ayirmak icin: rota servisi hazir olana kadar bekle (en fazla ~6 saat)
    if [ -n "${ROTA_BEKLE_ADRESI:-}" ]; then
        echo "[arama] Rota servisinin hazir olmasi bekleniyor..."
        for _ in $(seq 1 720); do
            curl -fs --max-time 5 "$ROTA_BEKLE_ADRESI" > /dev/null && break
            sleep 30
        done
    fi
    echo "[arama] Dizin yok, uretiliyor: ulke=$ULKE_KODLARI dil=$DIL_KODLARI (saatler surebilir, bir kereye mahsus)..."
    rm -rf /veri/photon_data
    curl -fsSL "$DOKUM_ADRESI" | zstd -d --stdout \
        | java -Xms512m -Xmx"$PHOTON_BELLEK" -jar /opt/photon.jar import -import-file - \
            -country-codes "$ULKE_KODLARI" -languages "$DIL_KODLARI"
    touch /veri/.hazir
    echo "[arama] Dizin hazir."
fi

exec java -Xms512m -Xmx"$PHOTON_BELLEK" -jar /opt/photon.jar serve -listen-ip 0.0.0.0 -listen-port 2322
