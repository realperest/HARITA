#!/bin/sh
# nginx acilisinda calisir: ortam degiskenlerinden tarayicinin okuyacagi yapilandirma.json dosyasini uretir.
set -eu

HEDEF=/usr/share/nginx/html/yapilandirma.json
# Ortam degiskeni degerinde kalmis tirnak, bosluk ve satir sonlarini temizle
temizle() { printf '%s' "$1" | tr -d "'\" 
"; }
MAPTILER_ANAHTAR=$(temizle "${MAPTILER_ANAHTAR:-}")
HARITA_ANAHTAR=$(temizle "${HARITA_ANAHTAR:-}")
printf '{"mtAnahtar": "%s", "anahtar": "%s"}
' "${MAPTILER_ANAHTAR:-}" "${HARITA_ANAHTAR:-}" > "$HEDEF"
echo "yapilandirma.json uretildi (MapTiler: $( [ -n "${MAPTILER_ANAHTAR:-}" ] && echo tanimli || echo yok ), HARITA: $( [ -n "${HARITA_ANAHTAR:-}" ] && echo tanimli || echo yok ))"
