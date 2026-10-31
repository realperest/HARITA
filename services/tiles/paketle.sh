#!/bin/bash
# Cevrimdisi harita paketleri: Turkiye karolarindan il il PMTiles kesitleri uretir (/veri/paket/<kod>.pmtiles) ve liste.json yazar.
# Ana dosya yenilenince paketler de yenilenir. Karo sunumunu bekletmemek icin arka planda calisir; hata olursa loglar, sunum surer.
set -uo pipefail

KAYNAK=/veri/turkiye.pmtiles
HEDEF=/veri/paket
LISTE=/etc/harita/paketler.csv
MAKS="${PAKET_MAKS_YAKINLASTIRMA:-14}"
mkdir -p "$HEDEF"

uretilen=0
while IFS=';' read -r kod ad kutu; do
    [[ -z "$kod" || "$kod" == \#* ]] && continue
    dosya="$HEDEF/$kod.pmtiles"
    if [ -s "$dosya" ] && [ "$dosya" -nt "$KAYNAK" ]; then
        continue
    fi
    if pmtiles extract "$KAYNAK" "$dosya.yapiliyor" --bbox="$kutu" --maxzoom="$MAKS" > /dev/null 2>&1; then
        mv "$dosya.yapiliyor" "$dosya"
        uretilen=$((uretilen + 1))
    else
        echo "[paket] HATA: $kod paketlenemedi" >&2
        rm -f "$dosya.yapiliyor"
    fi
done < "$LISTE"

# liste.json: kod, ad, kutu, boyut, tarih (istemciler indirme oncesi boyutu gosterir)
{
    echo '{"maks_yakinlastirma": '"$MAKS"', "varlik": "varlik.tar.gz", "paketler": ['
    ilk=1
    while IFS=';' read -r kod ad kutu; do
        [[ -z "$kod" || "$kod" == \#* ]] && continue
        dosya="$HEDEF/$kod.pmtiles"
        [ -s "$dosya" ] || continue
        boyut=$(stat -c %s "$dosya")
        tarih=$(date -u -r "$dosya" +%Y-%m-%dT%H:%M:%SZ)
        [ $ilk -eq 1 ] || echo ','
        ilk=0
        printf '{"kod": "%s", "ad": "%s", "kutu": [%s], "boyut": %s, "tarih": "%s", "dosya": "%s.pmtiles"}' "$kod" "$ad" "$kutu" "$boyut" "$tarih" "$kod"
    done < "$LISTE"
    echo ']}'
} > "$HEDEF/liste.json.yeni" && mv "$HEDEF/liste.json.yeni" "$HEDEF/liste.json"
echo "[paket] Tamam: $uretilen paket uretildi, liste guncel."
