"""Metin yardimcilari: arama icin Turkce karakter katlama."""

_KATLAMA = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
                          "Ö": "o", "ö": "o", "Ş": "s", "ş": "s", "Ü": "u", "ü": "u"})


def ad_katla(metin: str) -> str:
    """Kucuk harfe cevirir, Turkce karakterleri ASCII'ye katlar ve bosluklari sadelestirir (yukleyici ile ayni kural)."""
    return " ".join(metin.translate(_KATLAMA).lower().split())
