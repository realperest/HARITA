-- HARITA rota paylasim kodlari: duraklar ve profil kisa bir kodla paylasilir (or. navigasyon ?kod=K7M2P9QX). Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS rota_paylasim (
    kod            TEXT PRIMARY KEY,
    proje_id       BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    veri           JSONB NOT NULL,                 -- {ad, profil, duraklar: [{lat, lon, ad}]}
    olusturma      TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis          TIMESTAMPTZ NOT NULL,
    acilma_sayisi  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_rota_paylasim_proje ON rota_paylasim (proje_id);
CREATE INDEX IF NOT EXISTS ix_rota_paylasim_bitis ON rota_paylasim (bitis);

COMMIT;
