#!/bin/sh
# nginx acilisinda calisir: ortam degiskenlerinden tarayicinin okuyacagi yapilandirma.json dosyasini uretir.
set -eu

HEDEF=/usr/share/nginx/html/yapilandirma.json
printf '{"mtAnahtar": "%s"}\n' "${MAPTILER_ANAHTAR:-}" > "$HEDEF"
echo "yapilandirma.json uretildi (MapTiler anahtari: $( [ -n "${MAPTILER_ANAHTAR:-}" ] && echo tanimli || echo yok ))"
