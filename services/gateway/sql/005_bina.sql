-- HARITA site / bina katmani: adli site (konut, ticari, sanayi alani) ve bina poligonlari (OSM).
-- Veri services/veri yukleyicisi tarafindan doldurulur; bu betik yalniz sema kurar. Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS tnm_bina_turu (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tnm_bina_kullanimi (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bina_surum (
    id            BIGSERIAL PRIMARY KEY,
    kaynak_tarihi TIMESTAMPTZ,
    durum_id      SMALLINT NOT NULL REFERENCES tnm_islem_durumu (id),
    baslama       TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis         TIMESTAMPTZ,
    adet          INTEGER NOT NULL DEFAULT 0,
    hata_mesaji   TEXT
);
CREATE INDEX IF NOT EXISTS ix_bina_surum_durum ON bina_surum (durum_id);

CREATE TABLE IF NOT EXISTS bina (
    id              BIGSERIAL PRIMARY KEY,
    tur_id          SMALLINT NOT NULL REFERENCES tnm_bina_turu (id),
    kullanim_id     SMALLINT REFERENCES tnm_bina_kullanimi (id),
    kaynak_anahtari TEXT NOT NULL UNIQUE,                -- osm:way:123
    ad              TEXT NOT NULL,
    ad_arama        TEXT NOT NULL,
    sinir           GEOGRAPHY(POLYGON, 4326) NOT NULL,
    merkez          GEOGRAPHY(POINT, 4326) NOT NULL,
    mahalle_id      BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL,
    sokak_id        BIGINT REFERENCES sokak (id) ON DELETE SET NULL,
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES bina_surum (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_bina_tur ON bina (tur_id);
CREATE INDEX IF NOT EXISTS ix_bina_kullanim ON bina (kullanim_id);
CREATE INDEX IF NOT EXISTS ix_bina_mahalle ON bina (mahalle_id);
CREATE INDEX IF NOT EXISTS ix_bina_sokak ON bina (sokak_id);
CREATE INDEX IF NOT EXISTS ix_bina_surum ON bina (surum_id);
CREATE INDEX IF NOT EXISTS ix_bina_sinir ON bina USING gist (sinir);
CREATE INDEX IF NOT EXISTS ix_bina_merkez ON bina USING gist (merkez);
CREATE INDEX IF NOT EXISTS ix_bina_ad_arama ON bina USING gin (ad_arama gin_trgm_ops);

INSERT INTO tnm_bina_turu (id, kod, ad) VALUES (1, 'site', 'Site / alan'), (2, 'bina', 'Bina')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_bina_kullanimi (id, kod, ad) VALUES
    (1, 'apartments', 'Apartman'),
    (2, 'residential', 'Konut'),
    (3, 'commercial', 'Ticari'),
    (4, 'office', 'Ofis'),
    (5, 'retail', 'Perakende'),
    (6, 'industrial', 'Sanayi'),
    (7, 'dormitory', 'Yurt'),
    (8, 'hotel', 'Otel')
ON CONFLICT (id) DO NOTHING;

COMMIT;
