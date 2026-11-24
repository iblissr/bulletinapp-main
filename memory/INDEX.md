# Memory Index

Last updated: 2026-11-24 04:40

## Decisions
- [coefficients-par-classe](decisions/coefficients-par-classe.md)
  Tableau complet des coefficients par matière et par classe (17 classes),
  lecture du 2026-09-20. Source de vérité — les `.xlsx` d'origine ont
  été supprimés.

## Lessons
- (aucune)

## Sessions
- 2026-09-20 `ses_f40bdbf6effecy4jIkq4EGo4Ro` — correction initiale des
  coefficients distincts par classe (CLASS_DEFAULTS).
- 2026-11-24 `ses_df504adc9ffewQnigRXnGSVT5L` — test permissions / synchro.
- 2026-11-24 `ses_df4de4a58ffe4YyLkjS0rIUsAE` — session courante : rappel
  des coefficients.

## Open Context
1. Restaurer la correction des coefficients (working tree l'a perdue).
2. Fusionner HEAD (CLASS_DEFAULTS) + working tree (restrictions Philo,
   alias matières) sans écraser l'un l'autre.
3. Corriger les noms `TA1`/`TA2`/`1EREL1` non reconnus par
   `_get_class_defaults()`.
4. Physique-chimie = 2 pour 4EME2, 5EME1, 5EME2, 6EME1, 6EME2, 6EME3.
