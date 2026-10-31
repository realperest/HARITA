-- HARITA canli konum ve bolge (geofence) olaylari. Tekrar calistirmak zararsizdir.
BEGIN;

INSERT INTO tnm_servis (id, kod, ad) VALUES (8, 'canli', 'Canli konum yayini (WebSocket) ve bolge giris / cikis olaylari')
ON CONFLICT (id) DO NOTHING;

-- Tek seferlik sema goclerinin kaydi (yonetici sonradan bir izni kaldirirsa her acilista geri eklenmesin)
CREATE TABLE IF NOT EXISTS sema_gocu (
    ad     TEXT PRIMARY KEY,
    zaman  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mevcut projeler: rota izni olanlara bir kez ayni seviyede canli izni
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sema_gocu WHERE ad = '011_canli_izni') THEN
        INSERT INTO proje_servis_izni (proje_id, servis_id, izin_seviyesi_id)
        SELECT proje_id, 8, izin_seviyesi_id FROM proje_servis_izni WHERE servis_id = 1
        ON CONFLICT (proje_id, servis_id) DO NOTHING;
        INSERT INTO sema_gocu (ad) VALUES ('011_canli_izni');
    END IF;
END $$;

-- Bolgeler proje + kanal basina: daire (merkez + yaricap) ya da poligon
CREATE TABLE IF NOT EXISTS canli_bolge (
    proje_id   BIGINT NOT NULL REFERENCES proje (id) ON DELETE CASCADE,
    kanal      TEXT NOT NULL,
    bolge_id   TEXT NOT NULL,
    ad         TEXT,
    tanim      JSONB NOT NULL,                  -- {"merkez": {lat, lon}, "yaricap_m": 150} | {"poligon": [[lat, lon], ...]}
    guncelleme TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (proje_id, kanal, bolge_id)
);

COMMIT;
