-- Ek servis tanimlari: Valhalla'nin tum API'sine tam erisim. Tekrar calistirmak zararsizdir.
BEGIN;

INSERT INTO tnm_servis (id, kod, ad) VALUES (7, 'valhalla', 'Valhalla tam API (izokron, harita eslestirme, optimize rota vb.)')
ON CONFLICT (id) DO NOTHING;

COMMIT;
