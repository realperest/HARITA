# HARITA karo servisi: PMTiles (vektor karolar) + yazi tipleri + simgeler, nginx onunde (CORS, onbellek basliklari).
# Ilk acilista Protomaps gunluk yapisindan KAPSAM_KUTUSU kesitini indirir (/veri kalici hacimde saklanir).

FROM debian:bookworm-slim AS hazirlik
ARG PMTILES_SURUMU=1.31.2
ARG VARLIK_SURUMU=028c18f713baecad011301ff7a69acc39bcc2ae7
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /derle
RUN curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_SURUMU}/go-pmtiles_${PMTILES_SURUMU}_Linux_x86_64.tar.gz" \
    | tar -xz pmtiles
# Yazi tipleri (fonts) ve simgeler (sprites): sabit bir surume kilitlenir
RUN git clone https://github.com/protomaps/basemaps-assets.git varlik \
 && git -C varlik checkout "${VARLIK_SURUMU}" \
 && rm -rf varlik/.git

FROM nginx:1.27-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=hazirlik /derle/pmtiles /usr/local/bin/pmtiles
COPY --from=hazirlik /derle/varlik /usr/share/harita/assets
COPY nginx.conf.template /etc/nginx/harita.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/pmtiles
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
