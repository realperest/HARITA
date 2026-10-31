#!/bin/bash
# Rota servisi baslaticisi: Valhalla servis sinirlarini yukseltir, aylik yenilemeyi arka planda calistirir ve Valhalla'yi
# cocuk surec olarak yonetir (yenileme yeni grafi koyunca yalniz Valhalla yeniden baslatilir, konteyner kapanmaz).
#
# Valhalla varsayilan sinirlari Turkiye icin dar: motosiklet rotasi 500 km, matris (grup varis suresi, optimize sira)
# arac 400 km / motosiklet 200 km. Mevcut valhalla.json her acilista korunur; sinirlar baslamadan once yukseltilir.
# Ilk kurulumda dosya henuz yoktur: kurulum bitince servis bir kez yeniden baslatilinca sinirlar uygulanir.
set -uo pipefail

f=/custom_files/valhalla.json
if [ -f "$f" ]; then
    jq '.service_limits.auto.max_matrix_distance = 2500000
        | .service_limits.motorcycle.max_distance = 2500000 | .service_limits.motorcycle.max_matrix_distance = 2500000
        | .service_limits.bicycle.max_distance = 1000000 | .service_limits.bicycle.max_matrix_distance = 500000
        | .service_limits.auto.max_locations = 50 | .service_limits.motorcycle.max_locations = 50
        | .service_limits.bicycle.max_locations = 50 | .service_limits.pedestrian.max_locations = 50' "$f" | sponge "$f"
    echo "HARITA: servis sinirlari yukseltildi"
fi

if [ "${AYLIK_YENILEME:-True}" = "True" ]; then
    /rota-yenile.sh &
fi

KAPANIYOR=0
trap 'KAPANIYOR=1; kill -TERM "$(cat /tmp/valhalla.pid 2>/dev/null)" 2>/dev/null' TERM INT

while true; do
    /valhalla/scripts/docker-entrypoint.sh "$@" &
    echo $! > /tmp/valhalla.pid
    wait "$(cat /tmp/valhalla.pid)"
    kod=$?
    if [ "$KAPANIYOR" = 1 ]; then
        exit "$kod"
    fi
    if [ -f /tmp/rota_yeniden_baslat ]; then
        rm -f /tmp/rota_yeniden_baslat
        echo "HARITA: Valhalla yeni graf ile yeniden baslatiliyor"
        # Yeniden baslatmada zorla yeniden kurma bayragi uygulanmaz (aksi halde her seferinde graf bastan kurulur)
        export force_rebuild=False
        continue
    fi
    exit "$kod"
done
