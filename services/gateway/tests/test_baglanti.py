"""Harita baglantisi ayristirma testleri (senkron; asenkron test isaretinden ayri dosyada)."""

import pytest

from app.routers.yol import koordinatlari_cikar


@pytest.mark.parametrize("adres,beklenen", [
    ("https://www.google.com/maps/dir/41.0082,28.9784/40.9909,29.0237/", [(41.0082, 28.9784), (40.9909, 29.0237)]),
    ("https://www.google.com/maps/dir/?api=1&origin=41.1,29.0&destination=40.98,29.02&waypoints=41.0,28.95|40.99,29.01",
     [(41.1, 29.0), (41.0, 28.95), (40.99, 29.01), (40.98, 29.02)]),
    ("https://www.google.com/maps/place/Galata/@41.0256,28.9741,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d41.025658!4d28.974155",
     [(41.025658, 28.974155)]),
    ("https://www.google.com/maps?q=41.0082,28.9784", [(41.0082, 28.9784)]),
    ("https://yandex.com.tr/harita/?rtext=~41.01,28.97~40.99,29.02&rtt=auto", [(41.01, 28.97), (40.99, 29.02)]),
    ("https://yandex.com.tr/harita/?ll=28.97,41.01&z=14", [(41.01, 28.97)]),
    ("https://waze.com/ul?ll=40.99,29.02&navigate=yes", [(40.99, 29.02)]),
    ("https://maps.apple.com/?daddr=40.99,29.02", [(40.99, 29.02)]),
    ("https://www.openstreetmap.org/?mlat=41.0&mlon=29.0#map=15/41.0/29.0", [(41.0, 29.0)]),
    ("https://www.google.com/maps/search/kadikoy", []),
])
def test_baglanti_koordinatlari(adres, beklenen):
    assert [(n["lat"], n["lon"]) for n in koordinatlari_cikar(adres)] == beklenen
