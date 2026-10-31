#!/bin/bash
# Aylik rota grafi yenileme. Her ayin 1'inde 05:00'ten (Turkiye saati = 02:00 UTC) itibaren:
#   1) yeni OSM Turkiye verisini yan klasore indirir ve orada yeni grafi kurar (calisan servis etkilenmez),
#   2) yan graf ile gecici bir Valhalla calistirip ornek rotalari dener (uzunluk araliklari + canli servisle karsilastirma),
#   3) eski grafi .yedek olarak ayirip yenisini yerine koyar, yalniz Valhalla'yi yeniden baslatir,
#   4) yeniden basladiktan sonra ayni rotalari canli servisten dener; sorun varsa yedegi geri koyar.
# Basarisiz olursa canli graf degismez; 3 saat arayla en cok 4 kez denenir. Yedek bir sonraki yenilemeye kadar durur.
set -uo pipefail

CF=/custom_files
CONFIG="$CF/valhalla.json"
STAGE="$CF/yeni_kurulum"
DAMGA="$CF/.rota_son_ay"
DENEME="$CF/.rota_deneme"
CANLI_PORT="${ROTA_CANLI_PORT:-8002}"
YENI_PORT=8012
KONTROL_ARALIK="${YENILEME_KONTROL_SANIYE:-600}"
DENEME_ARALIK="${YENILEME_DENEME_BEKLEME_SANIYE:-10800}"
EN_COK_DENEME=4
IS_PARCACIGI="${ROTA_YENILEME_IS_PARCACIGI:-2}"
# Ornek rotalar: enlem1,boylam1,enlem2,boylam2,costing,en_az_km,en_cok_km (noktalı virgülle ayrilir)
KONTROL_ROTALARI="${ROTA_KONTROL_ROTALARI:-41.0082,28.9784,39.9334,32.8597,auto,380,520;41.0082,28.9784,39.9334,32.8597,motorcycle,380,520;41.0166,28.9712,41.0054,28.9768,pedestrian,0.3,3}"
KARSILASTIRMA_YUZDE="${ROTA_KARSILASTIRMA_YUZDE:-10}"
PBF_EN_AZ_ORAN="${ROTA_PBF_EN_AZ_ORAN:-70}"

gunluk() {
    echo "[rota-yenile $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

ay_simdi() { date -u +%Y%m; }

zamanlama_geldi() {
    local gun saat
    gun=$((10#$(date -u +%d)))
    saat=$((10#$(date -u +%H)))
    [ "$gun" -gt 1 ] || [ "$saat" -ge 2 ]
}

# Baska bir graf kurulumu (ilk kurulum ya da rakim yeniden kurulumu) calisiyor mu?
kurulum_calisiyor() {
    local c
    for c in /proc/[0-9]*/cmdline; do
        if tr '\0' ' ' < "$c" 2>/dev/null | grep -q "valhalla_build_\(tiles\|elevation\|admins\|extract\)" ; then
            # kendi yan kurulumumuzu sayma
            tr '\0' ' ' < "$c" 2>/dev/null | grep -q "$STAGE" && continue
            return 0
        fi
    done
    return 1
}

# rota_uzunluk PORT ENLEM1 BOYLAM1 ENLEM2 BOYLAM2 COSTING: km cinsinden uzunluk (bos = hata)
rota_uzunluk() {
    curl -fs --max-time 90 "http://127.0.0.1:$1/route" \
        -d "{\"locations\":[{\"lat\":$2,\"lon\":$3},{\"lat\":$4,\"lon\":$5}],\"costing\":\"$6\"}" 2>/dev/null \
        | jq -r '.trip.summary.length // empty' 2>/dev/null
}

servis_bekle() {
    local port="$1" sn="$2" i
    for i in $(seq 1 "$sn"); do
        curl -fs --max-time 3 "http://127.0.0.1:$port/status" > /dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

# rotalari_dene YENI_PORT [KARSILASTIRMA_PORTU]: tum ornek rotalar aralikta mi (ve karsilastirma portuyla uyumlu mu)? 0 = gecti
rotalari_dene() {
    local port="$1" karsi="${2:-}" satir a1 o1 a2 o2 cost en_az en_cok uz ref
    IFS=';' read -ra rotalar <<< "$KONTROL_ROTALARI"
    for satir in "${rotalar[@]}"; do
        IFS=, read -r a1 o1 a2 o2 cost en_az en_cok <<< "$satir"
        uz=$(rota_uzunluk "$port" "$a1" "$o1" "$a2" "$o2" "$cost")
        if [ -z "$uz" ]; then
            gunluk "DOGRULAMA: rota hesaplanamadi ($cost $a1,$o1 -> $a2,$o2)"
            return 1
        fi
        if ! awk -v u="$uz" -v a="$en_az" -v b="$en_cok" 'BEGIN { exit !(u >= a && u <= b) }'; then
            gunluk "DOGRULAMA: $cost rota uzunlugu $uz km aralik disi ($en_az-$en_cok)"
            return 1
        fi
        if [ -n "$karsi" ]; then
            ref=$(rota_uzunluk "$karsi" "$a1" "$o1" "$a2" "$o2" "$cost")
            if [ -n "$ref" ] && ! awk -v u="$uz" -v r="$ref" -v y="$KARSILASTIRMA_YUZDE" 'BEGIN { d = (u - r) / r * 100; if (d < 0) d = -d; exit !(d <= y) }'; then
                gunluk "DOGRULAMA: $cost rota uzunlugu canli servisten %$KARSILASTIRMA_YUZDE'den fazla farkli (yeni=$uz canli=$ref)"
                return 1
            fi
        fi
        gunluk "DOGRULAMA: $cost $uz km tamam"
    done
    return 0
}

yan_servisi_durdur() {
    [ -n "${YAN_PID:-}" ] && kill "$YAN_PID" 2>/dev/null && wait "$YAN_PID" 2>/dev/null
    YAN_PID=""
}

valhalla_yeniden_baslat() {
    touch /tmp/rota_yeniden_baslat
    kill -TERM "$(cat /tmp/valhalla.pid 2>/dev/null)" 2>/dev/null || gunluk "UYARI: Valhalla sureci bulunamadi"
}

geri_al() {
    gunluk "Yedek geri konuyor."
    local d
    for d in valhalla_tiles valhalla_tiles.tar admins.sqlite; do
        if [ -e "$CF/$d.yedek" ]; then
            rm -rf "$CF/$d.bozuk"
            [ -e "$CF/$d" ] && mv "$CF/$d" "$CF/$d.bozuk"
            mv "$CF/$d.yedek" "$CF/$d"
        fi
    done
    valhalla_yeniden_baslat
}

yenile() {
    local url pbf eski_pbf eski_boyut yeni_boyut oran gerekli bos
    # Baska bir kurulum bitene kadar bekle (en cok 4 saat)
    for _ in $(seq 1 48); do
        kurulum_calisiyor || break
        gunluk "Baska bir graf kurulumu suruyor, bekleniyor..."
        sleep 300
    done
    kurulum_calisiyor && { gunluk "HATA: baska kurulum bitmedi"; return 1; }

    url=$(echo "${tile_urls:-https://download.geofabrik.de/europe/turkey-latest.osm.pbf}" | awk '{print $1}')
    eski_pbf=$(ls "$CF"/*.pbf 2>/dev/null | head -1)

    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    pbf="$STAGE/$(basename "$url")"

    # Disk: mevcut graf boyutunun ~1,5 kati + PBF payi bos olmali
    gerekli=$(( $(du -sb "$CF/valhalla_tiles" 2>/dev/null | cut -f1) * 3 / 2 + 2000000000 ))
    bos=$(df --output=avail -B1 "$CF" | tail -1)
    if [ "$bos" -lt "$gerekli" ] && [ "${ROTA_DISK_KONTROL:-1}" = 1 ]; then
        gunluk "HATA: bos disk yetersiz ($bos bayt, gerekli ~$gerekli)"
        return 1
    fi

    gunluk "OSM verisi indiriliyor: $url"
    if ! curl -fL --retry 3 --retry-delay 30 --silent --show-error -o "$pbf.tmp" "$url"; then
        gunluk "HATA: indirme basarisiz"
        return 1
    fi
    mv "$pbf.tmp" "$pbf"
    if ! head -c 200 "$pbf" | grep -aq "OSMHeader"; then
        gunluk "HATA: indirilen dosya bir PBF degil"
        return 1
    fi
    if [ -n "$eski_pbf" ]; then
        eski_boyut=$(stat -c %s "$eski_pbf")
        yeni_boyut=$(stat -c %s "$pbf")
        oran=$((yeni_boyut * 100 / eski_boyut))
        if [ "$oran" -lt "$PBF_EN_AZ_ORAN" ]; then
            gunluk "HATA: yeni PBF eskisinin %$oran'i (en az %$PBF_EN_AZ_ORAN olmali)"
            return 1
        fi
    fi

    # Yan yapilandirma: canli yapilandirmanin kopyasi, yollar ve ag adresleri yan kuruluma cevrilir
    jq --arg t "$STAGE/valhalla_tiles" --arg x "$STAGE/valhalla_tiles.tar" --arg a "$STAGE/admins.sqlite" \
       --argjson c "$IS_PARCACIGI" --arg l "tcp://*:$YENI_PORT" \
       '.mjolnir.tile_dir = $t | .mjolnir.tile_extract = $x | .mjolnir.admin = $a | .mjolnir.concurrency = $c
        | .httpd.service.listen = $l
        | (.. | select(type == "string" and startswith("ipc://"))) |= (. + "_yeni")' "$CONFIG" > "$STAGE/valhalla.json" \
        || { gunluk "HATA: yan yapilandirma uretilemedi"; return 1; }

    gunluk "Yan graf kuruluyor (admin, graf, yukseklik, zenginlestirme)"
    valhalla_build_admins --config "$STAGE/valhalla.json" "$pbf" || { gunluk "HATA: admin veritabani"; return 1; }
    valhalla_build_tiles -c "$STAGE/valhalla.json" -e build "$pbf" || { gunluk "HATA: graf kurulumu"; return 1; }
    if [ "${build_elevation:-False}" = "True" ]; then
        valhalla_build_elevation --from-tiles --decompress -c "$STAGE/valhalla.json" -v || { gunluk "HATA: yukseklik"; return 1; }
    fi
    valhalla_build_tiles -c "$STAGE/valhalla.json" -s enhance "$pbf" || { gunluk "HATA: graf zenginlestirme"; return 1; }
    if [ -e "$CF/valhalla_tiles.tar" ]; then
        valhalla_build_extract -c "$STAGE/valhalla.json" -v || { gunluk "HATA: tar cikarimi"; return 1; }
    fi

    # Dogrulama: yan graf ile gecici servis
    gunluk "Yan graf dogrulaniyor (gecici servis, port $YENI_PORT)"
    valhalla_service "$STAGE/valhalla.json" 1 > "$STAGE/servis.log" 2>&1 &
    YAN_PID=$!
    if ! servis_bekle "$YENI_PORT" 300; then
        gunluk "HATA: yan servis acilmadi"
        yan_servisi_durdur
        return 1
    fi
    if ! rotalari_dene "$YENI_PORT" "$CANLI_PORT"; then
        yan_servisi_durdur
        return 1
    fi
    yan_servisi_durdur

    # Degisim: eskiler .yedek olur (onceki yedek silinir), yeniler yerine gecer
    gunluk "Degisim yapiliyor; eski graf .yedek olarak saklanacak"
    local d
    for d in valhalla_tiles valhalla_tiles.tar admins.sqlite; do
        rm -rf "$CF/$d.yedek"
        [ -e "$CF/$d" ] && mv "$CF/$d" "$CF/$d.yedek"
        [ -e "$STAGE/$d" ] && mv "$STAGE/$d" "$CF/$d"
    done
    if [ -n "$eski_pbf" ]; then
        rm -f "$eski_pbf.yedek"
        mv "$eski_pbf" "$eski_pbf.yedek"
    fi
    mv "$pbf" "$CF/$(basename "$pbf")"
    rm -rf "$STAGE"
    valhalla_yeniden_baslat

    # Yeniden basladiktan sonra canli servisi dene; sorun varsa geri al
    sleep 10
    if servis_bekle "$CANLI_PORT" 600 && rotalari_dene "$CANLI_PORT"; then
        gunluk "Yenileme tamam: yeni graf canli. Yedek duruyor: $CF/valhalla_tiles.yedek"
        ay_simdi > "$DAMGA"
        rm -f "$DENEME"
        return 0
    fi
    gunluk "HATA: yeni graf canlida dogrulanamadi"
    geri_al
    servis_bekle "$CANLI_PORT" 600 && gunluk "Yedek graf yeniden canli." || gunluk "UYARI: yedek graf sonrasi servis yanit vermedi"
    return 1
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
            gunluk "Aylik rota yenilemesi basliyor (deneme $deneme_say/$EN_COK_DENEME)"
            yenile || { gunluk "Rota yenilemesi basarisiz; canli graf degismedi ya da geri alindi."; rm -rf "$STAGE"; }
        fi
    fi
    [ "${YENILEME_ZORLA:-0}" = "1" ] && [ -n "${YENILEME_TEK_SEFER:-}" ] && exit 0
    sleep "$KONTROL_ARALIK"
done
