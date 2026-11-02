#!/bin/bash
# Yenilemeden sonraki acilis kontrolu: bekleyen degisim isareti varsa yeni dosyayi calisan sunucudan okur.
# Basariliysa isareti siler ve ayi damgalar; degilse yedegi geri koyar ve sunucuyu yeniden baslatir.
set -uo pipefail
. /ortak.sh

[ -f "$BEKLEYEN" ] || exit 0

# Sunucu hazir olana kadar bekle (en fazla ~2 dk)
for _ in $(seq 1 60); do
    curl -fs --max-time 3 http://127.0.0.1:8081/turkiye.json > /dev/null && break
    sleep 2
done

tamam=1
for kontrol in $KONTROL_KAROLARI; do
    bayt=$(curl -fs --max-time 10 "http://127.0.0.1:8081/turkiye/$kontrol.mvt" 2>/dev/null | wc -c)
    if [ "$bayt" -lt 200 ]; then
        gunluk "ACILIS KONTROLU: $kontrol karosu okunamadi ($bayt bayt)"
        tamam=0
    fi
done

if [ "$tamam" = 1 ]; then
    date -u +%Y%m > "$DAMGA"
    rm -f "$BEKLEYEN" "$DENEME"
    gunluk "Acilis kontrolu tamam: yeni karolar canli. Yedek duruyor: $YEDEK"
    exit 0
fi

gunluk "Yeni dosya sorunlu; yedek geri konuyor."
if [ -s "$YEDEK" ]; then
    mv "$DOSYA" "$DOSYA.bozuk"
    cp "$YEDEK" "$DOSYA"
    rm -f "$BEKLEYEN"
    # Bu ay yeniden denenmesin: damga basarisiz olsa da ay icin bir sonraki gune kadar bekler
    gunluk "Yedek geri yuklendi (bozuk dosya: $DOSYA.bozuk). Sunucu yeniden baslatiliyor."
    sunucuyu_yeniden_baslat
else
    gunluk "HATA: yedek yok, geri alinamadi."
fi
