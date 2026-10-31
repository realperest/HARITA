# HARITA deneme sayfasi: statik dosyalar + acilista Coolify ortam degiskenlerinden yapilandirma.json uretimi.
# MAPTILER_ANAHTAR (tarayici anahtari, izinli adreslere kisitli) Coolify'da tutulur; depoya yazilmaz.
FROM nginx:1.27-alpine

COPY index.html deneme.css deneme.js veritabani.html veritabani.css veritabani.js navigasyon.html navigasyon.css navigasyon.js surum.json /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY yapilandirma-uret.sh /docker-entrypoint.d/40-yapilandirma-uret.sh
RUN chmod +x /docker-entrypoint.d/40-yapilandirma-uret.sh

EXPOSE 80
