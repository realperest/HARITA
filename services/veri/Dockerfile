# HARITA veri yukleyicisi: Turkiye il / ilce / mahalle-koy sinirlari ve yerlesim merkezlerini OSM'den PostGIS'e yukler,
# sonra aylik olarak (GUNCELLEME_GUN) kendini tazeler. Uzun sureli calisir; Coolify'da diger servisler gibi gorunur.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends osmium-tool ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /uygulama
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY yukle.py adres.py bina.py ./

CMD ["python", "-u", "yukle.py"]
