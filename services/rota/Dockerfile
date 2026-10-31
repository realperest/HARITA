# HARITA rota servisi: Valhalla (valhalla-scripted) + aylik graf yenileme (rota-yenile.sh).
# Sunucu sinirlari yukseltilir; her ayin 1'inde 05:00'ten (Turkiye saati) yeni graf yan klasorde kurulur, dogrulanir, degistirilir.
FROM ghcr.io/valhalla/valhalla-scripted:3.9.1

COPY entrypoint.sh /harita-entrypoint.sh
COPY rota-yenile.sh /rota-yenile.sh
RUN chmod +x /harita-entrypoint.sh /rota-yenile.sh

ENTRYPOINT ["/harita-entrypoint.sh"]
