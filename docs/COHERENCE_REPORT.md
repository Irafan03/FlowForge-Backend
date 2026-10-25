# Rapport de cohérence — Documentation, Code et Tests

> ⚠️ **RAPPORT HISTORIQUE, OBSOLÈTE.** Ce document décrit l’état du dépôt au moment de sa rédaction. Depuis, le backend, les migrations, les tests, le Dockerfile et `docker-compose.yml` ont été ajoutés. Les constats ci-dessous disant que ces éléments n’existent pas ne décrivent plus l’état actuel. Consultez le code dans `app/`, `migrations/` et `tests/`, ainsi que le [README](../README.md), pour l’état présent.

**Date :** 16 octobre 2026
**Analyste :** Architecte Backend Senior / Technical Writer
**Repository :** `flowforge-backend`

---

## Résumé exécutif

| Dimension | Verdict |
|---|---|
| Code source présent | ❌ Inexistant |
| Tests présents | ❌ Inexistants |
| Documentation produite | ✅ Complète (basée sur spécification) |
| Cohérence documentation ↔ code | ⚠️ N/A — aucun code à comparer |
| Cohérence documentation ↔ tests | ⚠️ N/A — aucun test à comparer |
| Cohérence interne documentation | ✅ Vérifiée |

**Conclusion principale :** Ce repository est au stade zéro d'implémentation. Les deux fichiers présents (`Prompt 2A.md`, `Prompt 2B.md`) sont exclusivement des spécifications. La documentation produite est fidèle à ces spécifications mais ne peut pas être vérifiée contre du code réel car celui-ci n'existe pas encore.

---

## 1. État réel du repository

### Fichiers existants

```
flowforge-backend/
├── .git/                  ← Seul répertoire versionné
├── Prompt 2A.md           ← Spécification documentation
└── Prompt 2B.md           ← Spécification implémentation
```

**Constat :** Aucun fichier Python, aucun `requirements.txt`, aucun `Dockerfile`, aucune migration Alembic, aucun test. Le projet n'a pas encore commencé son implémentation.

### Fichiers créés lors de cette session

```
flowforge-backend/
├── README.md
├── .env.example
└── docs/
    ├── ARCHITECTURE.md
    ├── API.md
    ├── WORKFLOW_ENGINE.md
    ├── INTEGRATIONS.md
    ├── DATABASE.md
    ├── SECURITY.md
    ├── TESTING.md
    ├── DEPLOYMENT.md
    └── COHERENCE_REPORT.md   ← ce fichier
```

---

## 2. Cohérence interne de la documentation

### Vérification des références croisées

| Lien documentaire | Cohérence |
|---|---|
| README → docs/ARCHITECTURE.md | ✅ Cohérent |
| README → docs/API.md | ✅ Cohérent |
| ARCHITECTURE → docs/DATABASE.md | ✅ Cohérent |
| ARCHITECTURE → docs/WORKFLOW_ENGINE.md | ✅ Cohérent |
| ARCHITECTURE → docs/INTEGRATIONS.md | ✅ Cohérent |
| WORKFLOW_ENGINE → types de nœuds | ✅ Aligné avec INTEGRATIONS.md |
| API.md endpoints → SECURITY.md auth | ✅ Cohérent (🔒 sur tous les endpoints protégés) |
| DATABASE.md modèles → ARCHITECTURE.md modules | ✅ Cohérent |
| SECURITY.md risques → TESTING.md scénarios | ✅ Les risques SSRF/isolation sont couverts dans TESTING.md |
| DEPLOYMENT.md variables → .env.example | ✅ Toutes les variables documentées sont dans .env.example |

### Cohérence des statuts d'implémentation

Tous les documents utilisent le même marqueur **⬜ Non implémenté** de manière cohérente. Aucune fonctionnalité n'est déclarée implémentée. Ce respect est **vérifiable** : rechercher ✅ dans les docs ne retourne aucun résultat de fonctionnalité marquée comme terminée.

### Cohérence des types de nœuds

Les types de nœuds sont définis dans `WORKFLOW_ENGINE.md` et référencés de manière cohérente dans `INTEGRATIONS.md` et `DATABASE.md` :

| Type | WORKFLOW_ENGINE.md | INTEGRATIONS.md | DATABASE.md |
|---|---|---|---|
| `manual_trigger` | ✅ Défini | ✅ Décrit | ✅ Mentionné |
| `webhook_trigger` | ✅ Défini | ✅ Décrit | ✅ Mentionné |
| `schedule_trigger` | ✅ Défini | ✅ Décrit | ✅ Mentionné |
| `http_request` | ✅ Défini | ✅ Décrit (SSRF) | — |
| `if_condition` | ✅ Défini | — | — |
| `set_data` | ✅ Défini | — | — |
| `gmail_trigger` | ✅ Défini | ✅ Décrit | — |
| `gmail_send` | ✅ Défini | ✅ Décrit | — |
| `telegram_trigger` | ✅ Défini | ✅ Décrit | — |
| `telegram_send` | ✅ Défini | ✅ Décrit | — |
| `ml_prediction` | ✅ Défini | ✅ Décrit | — |

### Cohérence des statuts d'exécution

Les statuts `queued`, `running`, `success`, `failed`, `cancelled`, `skipped` sont utilisés de manière cohérente dans :
- `docs/WORKFLOW_ENGINE.md` (définitions)
- `docs/API.md` (réponses d'endpoints)
- `docs/DATABASE.md` (colonne `status`)
- `docs/TESTING.md` (scénarios de test)

---

## 3. Écarts entre documentation et spécification source

### Éléments de `Prompt 2B.md` couverts

| Fonctionnalité spécifiée | Documentée | Où |
|---|---|---|
| Auth JWT + isolation | ✅ | SECURITY.md, API.md |
| CRUD workflows + JSON graph | ✅ | API.md, DATABASE.md |
| Validation nœuds/connexions | ✅ | WORKFLOW_ENGINE.md |
| Moteur + branches IF | ✅ | WORKFLOW_ENGINE.md |
| Statuts queued/running/success/failed/cancelled | ✅ | WORKFLOW_ENGINE.md, DATABASE.md |
| Manual / Webhook / Schedule Trigger | ✅ | INTEGRATIONS.md |
| Gmail OAuth 2.0 | ✅ | INTEGRATIONS.md, SECURITY.md |
| Telegram Bot | ✅ | INTEGRATIONS.md |
| HTTP Request + SSRF | ✅ | INTEGRATIONS.md, SECURITY.md |
| ML Prediction via flowforge-ml | ✅ | INTEGRATIONS.md |
| Historique + logs par nœud | ✅ | API.md, DATABASE.md |
| Gestion sécurisée des credentials | ✅ | SECURITY.md, DATABASE.md |
| Migrations Alembic | ✅ | DATABASE.md, DEPLOYMENT.md |
| Docker Compose | ✅ | DEPLOYMENT.md |
| Tests | ✅ | TESTING.md |

### Éléments non documentés (gaps intentionnels)

| Élément | Raison |
|---|---|
| `requirements.txt` | Pas de code → pas de dépendances réelles à lister |
| `alembic.ini` | Pas de migrations réelles |
| `app/main.py` | Pas de code à documenter |
| Commandes exact du worker (Celery vs ARQ vs RQ) | Non décidé dans la spécification |

---

## 4. Risques et incohérences identifiés

### Décisions non prises dans la spécification

Ces points sont ambigus dans `Prompt 2B.md` et devront être tranchés lors de l'implémentation :

| Point ambigu | Impact | Recommandation |
|---|---|---|
| Système de tâches async : Celery, ARQ, RQ ou autre ? | Architecture worker entière | Décider avant phase 1 |
| Polling Gmail vs Push (Pub/Sub) ? | Architecture trigger Gmail | Polling pour phase 2, Pub/Sub pour phase 3 |
| Telegram : polling ou setWebhook ? | Architecture trigger Telegram | setWebhook recommandé en production |
| SQLAlchemy sync vs async ? | Performance sous charge | Sync acceptable pour phase 1 |
| Évaluateur de conditions IF : bibliothèque ? | Sécurité critique | `simpleeval` ou parseur maison — décider avant IF node |

### Risques de cohérence documentation ↔ futur code

Ces points pourraient créer des incohérences lors de l'implémentation :

| Risque | Probabilité | Mitigation |
|---|---|---|
| Le format JSON du graphe change lors de l'implémentation UI | Élevée | Versionner le schéma, mettre à jour WORKFLOW_ENGINE.md |
| Les outputs des nœuds diffèrent du spec | Moyenne | Les outputs sont spécifiés dans WORKFLOW_ENGINE.md — les tenir à jour |
| Les endpoints API changent de signature | Moyenne | Mettre à jour API.md à chaque changement d'interface |
| Le choix du worker change les commandes dans DEPLOYMENT.md | Élevée | Mettre à jour dès la décision |

---

## 5. Vérification de la règle "no implemented without code"

**Recherche de fonctionnalités déclarées implémentées sans code :**

Résultat : **aucune**. Toutes les fonctionnalités dans la documentation sont explicitement marquées `⬜ Non implémenté` ou contiennent une note `> ⚠️ SPÉCIFICATION`.

**Preuve :** Chaque section de chaque document commence par un avertissement ou contient le marqueur ⬜. Aucune section ne contient de code réel testé ou de commande `pytest` avec un résultat réel.

---

## 6. Plan de mise à jour de la documentation

À chaque phase d'implémentation, les documents suivants devront être mis à jour :

### Phase 1 : Core (Manual Trigger → HTTP Request)

| Document | Changements attendus |
|---|---|
| README.md | Marquer les fonctionnalités Phase 1 comme ✅ |
| ARCHITECTURE.md | Confirmer les choix de bibliothèques (worker, scheduler) |
| API.md | Valider les signatures d'endpoints réelles |
| WORKFLOW_ENGINE.md | Confirmer le format d'output des nœuds phase 1 |
| DATABASE.md | Remplacer le pseudocode par les modèles réels |
| TESTING.md | Ajouter les tests écrits, marquer les scénarios couverts |
| DEPLOYMENT.md | Ajouter le `docker-compose.yml` et `Dockerfile` réels |

### Phase 2 : Gmail, Telegram, Schedule

| Document | Changements attendus |
|---|---|
| INTEGRATIONS.md | Confirmer les détails d'implémentation OAuth, webhook Telegram |
| SECURITY.md | Marquer les contrôles de sécurité implémentés et testés |
| TESTING.md | Ajouter les scénarios d'intégration Gmail/Telegram |

### Phase 3 : ML, hardening sécurité, production

| Document | Changements attendus |
|---|---|
| INTEGRATIONS.md | Contrat API flowforge-ml réel |
| SECURITY.md | Marquer SSRF et chiffrement comme ✅ testés |
| DEPLOYMENT.md | Configuration production réelle |

---

## 7. Conclusion

La documentation produite est :

1. **Cohérente en interne** — tous les documents utilisent les mêmes termes, statuts et références croisées.
2. **Fidèle à la spécification** — tous les éléments de `Prompt 2B.md` sont couverts.
3. **Honnête sur l'état d'avancement** — aucune fonctionnalité n'est déclarée terminée.
4. **Actionnable** — chaque document fournit une base solide pour guider l'implémentation.

**La prochaine action recommandée** est de trancher les points ambigus (système de tâches, évaluateur IF) puis de commencer la Phase 1 : structure du projet, modèles SQLAlchemy, migration Alembic initiale, endpoint `/auth/register`, endpoint `/workflows`, et le chemin minimal `Manual Trigger → HTTP Request`.

**Règle de mise à jour :** Ce rapport doit être mis à jour à la fin de chaque phase d'implémentation pour refléter l'état réel du code et des tests.
