# Current Tasks

1. ~~**Restaurer la correction des coefficients par classe**~~ — **FAIT
   (2026-11-24)**.
   - Fusion manuelle HEAD + working tree réalisée (pas de `git checkout` :
     les ajouts `LEVEL_SUBJECT_RESTRICTIONS`, `CLASS_COEFF_OVERRIDES`,
     `_SUBJECT_ALIASES` sont préservés).
   - `_get_class_defaults()` renommé **`get_class_defaults()`** et
     reconnaît `TA1`, `TA2`, `1EREL1`, `1EREL2`, `2NDE1`, `2NDE2`
     (noms actuels) en plus de `TAI`, `TAII`, `1ERELI`… .
   - Physique-chimie = 2 en 4EME2, 5EME1, 5EME2, 6EME1, 6EME2, 6EME3 ;
     3 en 3EME1/3EME2/4EME1. ✓
   - Philosophie : jamais Collège ni 2nde ; 4 en TA1/TA2, 2 en 1ère et
     TD. ✓
   - Migration à usage unique par base (settings
     `coeff_defaults_version = "2026-09-20"`), exécutée sur les 8 bases
     `LYCEE/*/data/bulletin.db` (sauvegardes dans `data/.backups/`).
   - Port Rust terminé et vérifié par diff de parité
     (`scripts/parity_coefficients.py` ↔
     `bulletin-rs/crates/bulletin-core/tests/parity_dump.rs`).
   - Voir : `memory/decisions/coefficients-par-classe.md`.

2. **Point d'attention** : les `.xlsx` sources du tableau (cellule C4)
   ont été supprimés — `memory/decisions/coefficients-par-classe.md`
   reste l'**unique trace complète** des valeurs.

3. **Espaces disque** : le disque système a atteint 100 % pendant la
   session ; `bulletin-rs/target` et `cockpit-tools-main/target` ont été
   nettoyés (7,8 Go libérés). Penser à `cargo clean` avant les gros
   builds si ça se reproduit.
