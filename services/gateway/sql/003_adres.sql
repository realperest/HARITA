-- HARITA adres katmani: sokak / cadde, onemli yerler (yer isareti) ve kapi numaralari (tum Turkiye, OSM).
-- Veri services/veri yukleyicisi tarafindan doldurulur; bu betik yalniz sema kurar. Tekrar calistirmak zararsizdir.
BEGIN;

CREATE TABLE IF NOT EXISTS tnm_yol_sinifi (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL,
    sira SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS tnm_yer_turu (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL,
    sira SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS adres_surum (
    id            BIGSERIAL PRIMARY KEY,
    kaynak_tarihi TIMESTAMPTZ,
    durum_id      SMALLINT NOT NULL REFERENCES tnm_islem_durumu (id),
    baslama       TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis         TIMESTAMPTZ,
    sokak_adet    INTEGER NOT NULL DEFAULT 0,
    yer_adet      INTEGER NOT NULL DEFAULT 0,
    kapi_adet     INTEGER NOT NULL DEFAULT 0,
    hata_mesaji   TEXT
);
CREATE INDEX IF NOT EXISTS ix_adres_surum_durum ON adres_surum (durum_id);

-- Bir mahalle / koydeki ayni adli yol parcalari tek sokak olarak birlestirilir
CREATE TABLE IF NOT EXISTS sokak (
    id              BIGSERIAL PRIMARY KEY,
    kaynak_anahtari TEXT NOT NULL UNIQUE,                -- sokak:<mahalle_id>:<ad_arama>
    ad              TEXT NOT NULL,
    ad_arama        TEXT NOT NULL,
    sinif_id        SMALLINT NOT NULL REFERENCES tnm_yol_sinifi (id),
    mahalle_id      BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL,
    cizgi           GEOGRAPHY(MULTILINESTRING, 4326) NOT NULL,
    merkez          GEOGRAPHY(POINT, 4326) NOT NULL,
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES adres_surum (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_sokak_mahalle ON sokak (mahalle_id);
CREATE INDEX IF NOT EXISTS ix_sokak_sinif ON sokak (sinif_id);
CREATE INDEX IF NOT EXISTS ix_sokak_surum ON sokak (surum_id);
CREATE INDEX IF NOT EXISTS ix_sokak_cizgi ON sokak USING gist (cizgi);
CREATE INDEX IF NOT EXISTS ix_sokak_merkez ON sokak USING gist (merkez);
CREATE INDEX IF NOT EXISTS ix_sokak_ad_arama ON sokak USING gin (ad_arama gin_trgm_ops);

CREATE TABLE IF NOT EXISTS yer_isareti (
    id              BIGSERIAL PRIMARY KEY,
    tur_id          SMALLINT NOT NULL REFERENCES tnm_yer_turu (id),
    kaynak_anahtari TEXT NOT NULL UNIQUE,                -- osm:node:123 / osm:way:456
    ad              TEXT NOT NULL,
    ad_arama        TEXT NOT NULL,
    konum           GEOGRAPHY(POINT, 4326) NOT NULL,
    mahalle_id      BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL,
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES adres_surum (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_yer_isareti_tur ON yer_isareti (tur_id);
CREATE INDEX IF NOT EXISTS ix_yer_isareti_mahalle ON yer_isareti (mahalle_id);
CREATE INDEX IF NOT EXISTS ix_yer_isareti_surum ON yer_isareti (surum_id);
CREATE INDEX IF NOT EXISTS ix_yer_isareti_konum ON yer_isareti USING gist (konum);
CREATE INDEX IF NOT EXISTS ix_yer_isareti_ad_arama ON yer_isareti USING gin (ad_arama gin_trgm_ops);

CREATE TABLE IF NOT EXISTS kapi_numarasi (
    id              BIGSERIAL PRIMARY KEY,
    kaynak_anahtari TEXT NOT NULL UNIQUE,                -- osm:node:123 / osm:way:456
    kapi_no         TEXT NOT NULL,
    kapi_no_arama   TEXT NOT NULL,                       -- kucuk harf, bosluksuz
    sokak_ad        TEXT,                                -- OSM addr:street (yoksa en yakin sokak adi baglanir)
    sokak_id        BIGINT REFERENCES sokak (id) ON DELETE SET NULL,
    konum           GEOGRAPHY(POINT, 4326) NOT NULL,
    mahalle_id      BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL,
    aktif_mi        BOOLEAN NOT NULL DEFAULT TRUE,
    surum_id        BIGINT REFERENCES adres_surum (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_kapi_numarasi_sokak ON kapi_numarasi (sokak_id, kapi_no_arama);
CREATE INDEX IF NOT EXISTS ix_kapi_numarasi_mahalle ON kapi_numarasi (mahalle_id);
CREATE INDEX IF NOT EXISTS ix_kapi_numarasi_surum ON kapi_numarasi (surum_id);
CREATE INDEX IF NOT EXISTS ix_kapi_numarasi_konum ON kapi_numarasi USING gist (konum);

INSERT INTO tnm_yol_sinifi (id, kod, ad, sira) VALUES
    (1, 'motorway', 'Otoyol', 1),
    (2, 'trunk', 'Ana karayolu', 2),
    (3, 'primary', 'Birinci derece yol', 3),
    (4, 'secondary', 'Ikinci derece yol', 4),
    (5, 'tertiary', 'Ucuncu derece yol', 5),
    (6, 'unclassified', 'Siniflandirilmamis yol', 6),
    (7, 'residential', 'Mahalle ici sokak', 7),
    (8, 'living_street', 'Yasam sokagi', 8),
    (9, 'pedestrian', 'Yaya yolu', 9)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_yer_turu (id, kod, ad, sira) VALUES
    (1, 'eczane', 'Eczane', 1),
    (2, 'saglik', 'Saglik kurulusu', 2),
    (3, 'egitim', 'Egitim kurumu', 3),
    (4, 'ibadet', 'Ibadet yeri', 4),
    (5, 'kamu', 'Kamu kurumu', 5),
    (6, 'banka', 'Banka', 6),
    (7, 'akaryakit', 'Akaryakit istasyonu', 7),
    (8, 'yeme_icme', 'Yeme icme', 8),
    (9, 'market', 'Market', 9),
    (10, 'firin', 'Firin / pastane', 10),
    (11, 'otel', 'Otel', 11),
    (12, 'dukkan', 'Dukkan', 12)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_servis (id, kod, ad) VALUES (6, 'adres', 'Sokak, kapi numarasi, onemli yerler ve adres arama')
ON CONFLICT (id) DO NOTHING;

COMMIT;
