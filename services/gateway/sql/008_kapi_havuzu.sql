-- HARITA ortak kapi numarasi havuzu: OSM'de olmayan kapi numaralarini bagli projelerin teslimat / ziyaret konumlarindan ogrenir.
-- Her gozlem ayri tutulur; kapinin konumu gozlemlerin geometrik ortancasidir (tek hatali konum sonucu bozmaz).
-- Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS kapi_ogrenilen (
    id             BIGSERIAL PRIMARY KEY,
    sokak_id       BIGINT NOT NULL REFERENCES sokak (id) ON DELETE CASCADE,
    kapi_no        TEXT NOT NULL,
    kapi_no_arama  TEXT NOT NULL,
    konum          GEOGRAPHY(POINT, 4326) NOT NULL,
    gozlem_sayisi  INTEGER NOT NULL DEFAULT 0,
    proje_sayisi   INTEGER NOT NULL DEFAULT 0,
    olusturma      TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncelleme     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sokak_id, kapi_no_arama)
);
CREATE INDEX IF NOT EXISTS ix_kapi_ogrenilen_konum ON kapi_ogrenilen USING gist (konum);

CREATE TABLE IF NOT EXISTS kapi_gozlem (
    id                 BIGSERIAL PRIMARY KEY,
    kapi_ogrenilen_id  BIGINT NOT NULL REFERENCES kapi_ogrenilen (id) ON DELETE CASCADE,
    proje_id           BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    konum              GEOGRAPHY(POINT, 4326) NOT NULL,
    dogruluk_m         REAL,
    zaman              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_kapi_gozlem_kapi ON kapi_gozlem (kapi_ogrenilen_id);
CREATE INDEX IF NOT EXISTS ix_kapi_gozlem_proje ON kapi_gozlem (proje_id);

COMMIT;
