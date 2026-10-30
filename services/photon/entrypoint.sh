#!/bin/bash
# Arama servisi baslaticisi: dizin yoksa gezegen dokumunden ULKE_KODLARI icin uretir (uzun surer), sonra Photon'u sunar.
# Photon 1.0 "-import-file -" (stdin) kabul etmez; dokum, adli boru (FIFO) uzerinden dosya gibi okutulur.
set -euo pipefail

cd /veri
ULKE_KODLARI="${ULKE_KODLARI:-TR}"
DIL_KODLARI="${DIL_KODLARI:-tr,en}"
PHOTON_BELLEK="${PHOTON_BELLEK:-2g}"
DOKUM_ADRESI="${DOKUM_ADRESI:-https://download1.graphhopper.com/public/photon-dump-planet-1.0-latest.jsonl.zst}"
BORU=/tmp/dokum.jsonl

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
    rm -rf /veri/photon_data "$BORU"
    mkfifo "$BORU"
    # Indirme + acma arka planda boruya yazar; hata olursa durumu dosyaya birakir
    ( curl -fsSL "$DOKUM_ADRESI" | zstd -d -q > "$BORU" ) &
    URETICI=$!
    java -Xms512m -Xmx"$PHOTON_BELLEK" -jar /opt/photon.jar import -import-file "$BORU" \
        -country-codes "$ULKE_KODLARI" -languages "$DIL_KODLARI"
    if ! wait "$URETICI"; then
        echo "[arama] HATA: dokum indirilemedi veya acilamadi, indeks gecersiz sayildi." >&2
        rm -rf /veri/photon_data
        exit 1
    fi
    touch /veri/.hazir
    echo "[arama] Dizin hazir."
fi

exec java -Xms512m -Xmx"$PHOTON_BELLEK" -jar /opt/photon.jar serve -listen-ip 0.0.0.0 -listen-port 2322
