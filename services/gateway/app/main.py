"""HARITA anahtar kapisi uygulamasi."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import cache, db
from app.config import ayarlar
from app.routers import adres, arama, osrm, rota, saglik, uyumlu, valhalla, veritabani, yapilandirma, yerlesim, yonetim
from app.services import http

logging.basicConfig(level=ayarlar.LOG_SEVIYESI, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def yasam_dongusu(_uygulama: FastAPI):
    """Acilista veritabani, Redis ve HTTP istemcisini hazirlar; kapanista kapatir."""
    await db.baslat()
    await cache.baslat()
    http.baslat()
    yield
    await http.kapat()
    await cache.kapat()
    await db.kapat()


app = FastAPI(title="HARITA", version="1.0.0", lifespan=yasam_dongusu, docs_url=None, redoc_url=None)

app.add_middleware(GZipMiddleware, minimum_size=1024)
# Tarayici kaynak kisitlamasi proje bazinda anahtar kapisinda uygulanir; burada onden kontrol (preflight) acik birakilir.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["*"], max_age=600)


@app.exception_handler(Exception)
async def beklenmeyen_hata(request: Request, hata: Exception) -> JSONResponse:
    """Beklenmeyen hatalarda teknik ayrinti yalniz loga yazilir."""
    log.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Beklenmeyen bir hata olustu."})


for yonlendirici in (saglik.router, rota.router, osrm.router, arama.router, yapilandirma.router, yerlesim.router,
                   adres.router, uyumlu.router, valhalla.router, yonetim.router, veritabani.router):
    app.include_router(yonlendirici)
