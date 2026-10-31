-- Hicbir mahalle / koy sinirina dusmeyen sokaklar ilceye dogrudan baglanir (acilir listede "ilceye bagli yollar",
-- ilce filtresiyle aramada bulunabilme). Veri yukleyici yeni kayitlarda ilce_id'yi kendisi doldurur.
-- Tekrar calistirmak zararsizdir.
ALTER TABLE sokak ADD COLUMN IF NOT EXISTS ilce_id BIGINT REFERENCES yerlesim (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_sokak_ilce ON sokak (ilce_id);

-- Kaynak anahtariyla toplu esleme (SIPARIS gecisi: osm:node:.. / osm:way:..) icin dizinler UNIQUE kisitlarindan gelir.
