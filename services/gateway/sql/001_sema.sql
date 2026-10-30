-- HARITA anahtar kapisi semasi. Tek calistirmada kurulur; tekrar calistirmak zararsizdir (IF NOT EXISTS / ON CONFLICT).
-- Bir hata olursa islem geri alinir ve hata gorunur (psql: -v ON_ERROR_STOP=1; gateway acilisinda ayni mantik).
BEGIN;

-- Servis tanimlari (kod yerine id ile baglanir)
CREATE TABLE IF NOT EXISTS tnm_servis (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL
);

-- Izin seviyeleri: 1 goremez, 2 gorebilir (kullanir), 3 duzenleyebilir (yonetir)
CREATE TABLE IF NOT EXISTS tnm_izin_seviyesi (
    id   SMALLINT PRIMARY KEY,
    kod  TEXT NOT NULL UNIQUE,
    ad   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proje (
    id            BIGSERIAL PRIMARY KEY,
    ad            TEXT NOT NULL UNIQUE,
    aciklama      TEXT,
    aktif         BOOLEAN NOT NULL DEFAULT TRUE,
    dakika_limiti INTEGER NOT NULL DEFAULT 600 CHECK (dakika_limiti > 0),
    olusturma     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proje_anahtar (
    id            BIGSERIAL PRIMARY KEY,
    proje_id      BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    anahtar_ozeti TEXT NOT NULL UNIQUE,
    on_ek         TEXT NOT NULL,
    aktif         BOOLEAN NOT NULL DEFAULT TRUE,
    olusturma     TIMESTAMPTZ NOT NULL DEFAULT now(),
    son_kullanim  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_proje_anahtar_proje ON proje_anahtar (proje_id);

CREATE TABLE IF NOT EXISTS proje_servis_izni (
    proje_id         BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    servis_id        SMALLINT NOT NULL REFERENCES tnm_servis (id),
    izin_seviyesi_id SMALLINT NOT NULL REFERENCES tnm_izin_seviyesi (id),
    PRIMARY KEY (proje_id, servis_id)
);
CREATE INDEX IF NOT EXISTS ix_proje_servis_izni_servis ON proje_servis_izni (servis_id);
CREATE INDEX IF NOT EXISTS ix_proje_servis_izni_seviye ON proje_servis_izni (izin_seviyesi_id);

-- Tarayicidan kullanimda izinli kaynaklar (Origin). Bos ise tarayici kaynagi kisitlanmaz.
CREATE TABLE IF NOT EXISTS proje_kaynak (
    proje_id BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    kaynak   TEXT NOT NULL,
    PRIMARY KEY (proje_id, kaynak)
);

CREATE TABLE IF NOT EXISTS kullanim_gunluk (
    proje_id  BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    servis_id SMALLINT NOT NULL REFERENCES tnm_servis (id),
    gun       DATE NOT NULL,
    adet      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (proje_id, servis_id, gun)
);
CREATE INDEX IF NOT EXISTS ix_kullanim_gunluk_servis ON kullanim_gunluk (servis_id);

INSERT INTO tnm_servis (id, kod, ad) VALUES
    (1, 'rota', 'Rota ve OSRM uyumlu rota'),
    (2, 'matris', 'Sure / mesafe matrisi'),
    (3, 'arama', 'Adres ve yer arama, ters arama'),
    (4, 'yapilandirma', 'Harita yapilandirmasi (karo, yazi tipi adresleri)')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tnm_izin_seviyesi (id, kod, ad) VALUES
    (1, 'goremez', 'Goremez'),
    (2, 'gorebilir', 'Gorebilir'),
    (3, 'duzenleyebilir', 'Duzenleyebilir')
ON CONFLICT (id) DO NOTHING;

COMMIT;
