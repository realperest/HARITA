"""Polyline cozucu testi (senkron; asenkron test isaretinden ayri dosyada)."""

import pytest

from app.services.valhalla import polyline_coz


@pytest.mark.parametrize("metin,beklenen", [("_p~iF~ps|U_ulLnnqC_mqNvxq`@", [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]])])
def test_polyline5_cozme(metin, beklenen):
    cozulen = polyline_coz(metin, 5)
    assert [d for nokta in cozulen for d in nokta] == pytest.approx([d for nokta in beklenen for d in nokta])
