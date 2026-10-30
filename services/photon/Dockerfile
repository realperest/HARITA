# HARITA arama servisi: Photon (adres / yer arama, ters arama). Dizin ilk acilista gezegen dokumunden ULKE_KODLARI icin uretilir.
FROM eclipse-temurin:21-jre

ARG PHOTON_SURUMU=1.0.0
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates zstd \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /opt/photon.jar "https://github.com/komoot/photon/releases/download/${PHOTON_SURUMU}/photon-${PHOTON_SURUMU}.jar"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
WORKDIR /veri
EXPOSE 2322
ENTRYPOINT ["/entrypoint.sh"]
