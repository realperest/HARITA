-- HARITA yerlesim katmani: il, ilce, mahalle / koy sinirlari ve sehir, kasaba, koy, mezra, semt merkezleri (tum Turkiye).
-- Kaynak OpenStreetMap (ODbL). Veri services/veri yukleyicisi tarafindan doldurulur; bu betik yalniz sema kurar.
-- Tekrar calistirmak zararsizdir. Hata olursa islem geri alinir.
BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS tnm_yerlesim_turu (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL,
    sira SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS tnm_islem_durumu (
    id  SMALLINT PRIMARY KEY,
    kod TEXT NOT NULL UNIQUE,
    ad  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS yerlesim_surum (
    id            BIGSERIAL PRIMARY KEY,
    kaynak        TEXT NOT NULL DEFAULT 'osm',
    kaynak_tarihi TIMESTAMPTZ,
    durum_id      SMALLINT NOT NULL REFERENCES tnm_islem_durumu (id),
    baslama       TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis         TIMESTAMPTZ,
    adet          INTEGER NOT NULL DEFAULT 0,
    hata_mesaji   TEXT
);
CREATE INDEX IF NOT EXISTS ix_yerlesim_surum_durum ON yerlesim_surum (durum_id);

CREATE TABLE IF NOT EXISTS yerlesim (
    id              BIGSERIAL PRIMARY KEY,
    tur_id          SMALLINT NOT NULL REFERENCES tnm_yerlesim_turu (id),
    ust_id          BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL,
    kaynak_anahtari TEXT NOT NULL UNIQUE,            -- osm:relation:123 / osm:node:456
    ad              TEXT NOT NULL,
    ad_arama        TEXT NOT NULL,                   -- kucuk harf + ASCII katlanmis arama metni
    merkez          GEOGRAPHY(POINT, 4326) NOT NULL,
    sinir           GEOGRAPHY(MULTIPOLYGON, 4326),   -- il / ilce / mahalle-koy icin
    nufus           INTEGER,
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES yerlesim_surum (id) ON DELETE SET NULL,
    olusturma       TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncelleme      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_yerlesim_tur_ust ON yerlesim (tur_id, ust_id);
CREATE INDEX IF NOT EXISTS ix_yerlesim_ust ON yerlesim (ust_id);
CREATE INDEX IF NOT EXISTS ix_yerlesim_surum ON yerlesim (surum_id);
CREATE INDEX IF NOT EXISTS ix_yerlesim_merkez ON yerlesim USING gist (merkez);
CREATE INDEX IF NOT EXISTS ix_yerlesim_sinir ON yerlesim USING gist (sinir);
CREATE INDEX IF NOT EXISTS ix_yerlesim_ad_arama ON yerlesim USING gin (ad_arama gin_trgm_ops);

INSERT INTO tnm_yerlesim_turu (id, kod, ad, sira) VALUES
    (1, 'il', 'Il', 1),
    (2, 'ilce', 'Ilce', 2),
    (3, 'mahalle_koy', 'Mahalle / Koy (idari sinir)', 3),
    (4, 'sehir', 'Sehir merkezi', 4),
    (5, 'kasaba', 'Kasaba merkezi', 5),
    (6, 'koy', 'Koy merkezi', 6),
    (7, 'mezra', 'Mezra / mevki', 7),
    (8, 'semt', 'Semt / mahalle merkezi', 8)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_islem_durumu (id, kod, ad) VALUES
    (1, 'calisiyor', 'Calisiyor'),
    (2, 'tamam', 'Tamamlandi'),
    (3, 'hata', 'Hata')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_servis (id, kod, ad) VALUES (5, 'yerlesim', 'Il, ilce, mahalle / koy ve merkez sorgulari')
ON CONFLICT (id) DO NOTHING;

COMMIT;
