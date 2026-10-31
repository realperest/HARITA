-- HARITA trafik profili: bagli projelerin anonim GPS izlerinden (kurye / surus) yol parcasi bazinda haftanin saatine gore ortalama hiz.
-- Cihaz, kisi ya da iz saklanmaz; yalniz OSM yol kimligi + haftanin saati basina ornek sayisi ve ortalama hiz tutulur.
-- Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS trafik_hiz (
    osm_yol_id  BIGINT NOT NULL,
    saat        SMALLINT NOT NULL CHECK (saat BETWEEN 0 AND 167),   -- haftanin saati (Pazartesi 00:00 = 0, Turkiye saati)
    ornek       INTEGER NOT NULL DEFAULT 0,
    ortalama    DOUBLE PRECISION NOT NULL,                          -- km/sa
    guncelleme  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (osm_yol_id, saat)
);
CREATE INDEX IF NOT EXISTS ix_trafik_hiz_guncelleme ON trafik_hiz (guncelleme);

COMMIT;
