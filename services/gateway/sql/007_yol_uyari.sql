-- HARITA yol uyarilari: hiz kamerasi ve hiz kesici (kasis) noktalari (OSM highway=speed_camera, traffic_calming).
-- Veri services/veri yukleyicisi tarafindan doldurulur; bu betik yalniz sema kurar. Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS tnm_yol_uyari_turu (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS yol_uyari_surum (
    id            BIGSERIAL PRIMARY KEY,
    kaynak_tarihi TIMESTAMPTZ,
    durum_id      SMALLINT NOT NULL REFERENCES tnm_islem_durumu (id),
    baslama       TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis         TIMESTAMPTZ,
    adet          INTEGER NOT NULL DEFAULT 0,
    hata_mesaji   TEXT
);
CREATE INDEX IF NOT EXISTS ix_yol_uyari_surum_durum ON yol_uyari_surum (durum_id);

CREATE TABLE IF NOT EXISTS yol_uyari (
    id              BIGSERIAL PRIMARY KEY,
    tur_id          SMALLINT NOT NULL REFERENCES tnm_yol_uyari_turu (id),
    kaynak_anahtari TEXT NOT NULL UNIQUE,                -- osm:node:123
    konum           GEOGRAPHY(POINT, 4326) NOT NULL,
    hiz_siniri      SMALLINT,                            -- km/sa (maxspeed etiketi varsa)
    yon             SMALLINT,                            -- derece (direction etiketi sayisal ise)
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES yol_uyari_surum (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_yol_uyari_tur ON yol_uyari (tur_id);
CREATE INDEX IF NOT EXISTS ix_yol_uyari_surum ON yol_uyari (surum_id);
CREATE INDEX IF NOT EXISTS ix_yol_uyari_konum ON yol_uyari USING gist (konum);

INSERT INTO tnm_yol_uyari_turu (id, kod, ad) VALUES
    (1, 'hiz_kamerasi', 'Hiz kamerasi'),
    (2, 'hiz_kesici', 'Hiz kesici (kasis)')
ON CONFLICT (id) DO NOTHING;

COMMIT;
