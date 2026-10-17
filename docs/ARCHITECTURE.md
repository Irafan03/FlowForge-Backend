# Architecture — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Ce document décrit l'architecture **prévue**. Aucun code n'a encore été implémenté.
> Source : `Prompt 2B.md`. Statut de chaque module : ⬜ Non implémenté.

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Structure des répertoires](#structure-des-répertoires)
- [Modules et responsabilités](#modules-et-responsabilités)
- [Dépendances inter-modules](#dépendances-inter-modules)
- [Cycle de vie d'une exécution](#cycle-de-vie-dune-exécution)
- [Flux de données](#flux-de-données)
- [Composants infrastructure](#composants-infrastructure)
- [Décisions d'architecture](#décisions-darchitecture)

---

## Vue d'ensemble

FlowForge Backend est une application Python orientée services, organisée en couches clairement délimitées :

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                            │
│         FastAPI Routers  ·  Auth Middleware  ·  Schemas     │
├─────────────────────────────────────────────────────────────┤
│                     Service Layer                           │
│      WorkflowService  ·  ExecutionService  ·  AuthService   │
├─────────────────────────────────────────────────────────────┤
│                    Repository Layer                         │
│   WorkflowRepo  ·  ExecutionRepo  ·  CredentialRepo  ·  … │
├─────────────────────────────────────────────────────────────┤
│                     Domain Layer                            │
│       SQLAlchemy Models  ·  Pydantic Schemas  ·  Engine     │
├─────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                       │
│      PostgreSQL  ·  Redis  ·  Async Workers  ·  Alembic     │
└─────────────────────────────────────────────────────────────┘
```

---

## Structure des répertoires

```
flowforge-backend/
│
├── app/
│   ├── main.py                   # Point d'entrée FastAPI, montage des routers
│   ├── dependencies.py           # Dépendances partagées (get_db, get_current_user)
│   │
│   ├── api/                      # Routeurs FastAPI
│   │   ├── auth.py               # POST /auth/register, POST /auth/login
│   │   ├── workflows.py          # CRUD /workflows
│   │   ├── executions.py         # POST /workflows/{id}/execute, GET /executions
│   │   ├── triggers.py           # Webhook endpoint, Schedule management
│   │   ├── integrations.py       # OAuth callbacks, credential management
│   │   └── health.py             # GET /health
│   │
│   ├── config/
│   │   └── settings.py           # Pydantic BaseSettings, chargement .env
│   │
│   ├── models/                   # Modèles SQLAlchemy
│   │   ├── user.py               # User
│   │   ├── workflow.py           # Workflow
│   │   ├── execution.py          # WorkflowExecution, NodeExecution
│   │   ├── trigger.py            # Trigger (webhook, schedule)
│   │   └── credential.py        # Credential (chiffré)
│   │
│   ├── schemas/                  # Schémas Pydantic (validation I/O)
│   │   ├── auth.py               # RegisterRequest, LoginRequest, TokenResponse
│   │   ├── workflow.py           # WorkflowCreate, WorkflowRead, WorkflowGraph
│   │   ├── execution.py          # ExecutionCreate, ExecutionRead, NodeLog
│   │   ├── node.py               # NodeDefinition, NodeConfig, NodeOutput
│   │   └── credential.py        # CredentialCreate, CredentialRead
│   │
│   ├── repositories/             # Accès DB (CRUD pur, pas de logique métier)
│   │   ├── user_repo.py
│   │   ├── workflow_repo.py
│   │   ├── execution_repo.py
│   │   └── credential_repo.py
│   │
│   ├── services/                 # Logique métier
│   │   ├── auth_service.py       # Hash MDP, création JWT, vérification
│   │   ├── workflow_service.py   # Validation graphe, activation, désactivation
│   │   ├── execution_service.py  # Création exécution, dispatch worker, annulation
│   │   └── credential_service.py # Chiffrement/déchiffrement Fernet
│   │
│   ├── engine/                   # Moteur d'exécution des workflows
│   │   ├── runner.py             # Orchestration : topo sort, boucle de nœuds
│   │   ├── context.py            # ExecutionContext : state, outputs par nœud
│   │   ├── node_executor.py      # Dispatch vers l'handler approprié par type
│   │   └── validators.py         # Validation graphe avant exécution
│   │
│   ├── triggers/                 # Handlers de déclenchement
│   │   ├── manual.py             # Déclenchement immédiat via API
│   │   ├── webhook.py            # Réception HTTP → dispatch
│   │   └── schedule.py           # APScheduler / cron → dispatch
│   │
│   ├── integrations/             # Nœuds d'intégration externes
│   │   ├── http_request.py       # HTTP générique + protection SSRF
│   │   ├── gmail.py              # OAuth 2.0, send/receive
│   │   ├── telegram.py           # Bot API, send/receive
│   │   └── ml_prediction.py      # Appel flowforge-ml API
│   │
│   └── workers/                  # Workers asynchrones
│       ├── main.py               # Point d'entrée worker
│       └── execution_worker.py   # Consomme tâches Redis, appelle engine.runner
│
├── migrations/                   # Alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                 # Fichiers de migration générés
│
├── tests/
│   ├── unit/
│   │   ├── test_engine.py
│   │   ├── test_validators.py
│   │   ├── test_auth_service.py
│   │   └── test_integrations.py
│   └── integration/
│       ├── test_workflows_api.py
│       ├── test_executions_api.py
│       └── test_triggers.py
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── .env.example
└── README.md
```

---

## Modules et responsabilités

### `app/api/` — Couche API ⬜

Responsabilité unique : recevoir les requêtes HTTP, valider les entrées via Pydantic, appeler les services, retourner les réponses.

- Aucune logique métier dans les routers.
- Authentification via dépendance `get_current_user` injectée.
- Isolation utilisateur : chaque router filtre par `user_id` extrait du JWT.

### `app/config/settings.py` — Configuration ⬜

Module basé sur `pydantic-settings`. Charge les variables depuis `.env` ou l'environnement. Unique source de vérité pour tous les paramètres.

```python
# Exemple de structure attendue (non implémenté)
class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str  # Fernet key
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    FLOWFORGE_ML_URL: str = ""

    class Config:
        env_file = ".env"
```

### `app/models/` — Modèles SQLAlchemy ⬜

Voir [docs/DATABASE.md](DATABASE.md) pour le détail complet des tables et relations.

### `app/schemas/` — Schémas Pydantic ⬜

Séparation stricte entre les schémas d'entrée (`*Create`, `*Update`) et de sortie (`*Read`). Les schémas de sortie **ne doivent jamais exposer** les champs sensibles (mots de passe, clés chiffrées).

### `app/repositories/` — Couche Repository ⬜

Abstraction de l'accès à la base de données. Chaque méthode prend une `Session` SQLAlchemy et retourne des modèles ORM. Aucune logique métier ici.

Patterns attendus :
- `get_by_id(db, id, user_id)` — toujours filtrer par `user_id`
- `create(db, data)` → commit + refresh
- `update(db, model, data)` → commit + refresh
- `delete(db, model)` → soft delete ou hard delete selon le cas

### `app/services/` — Couche Service ⬜

Logique métier : validation, orchestration d'appels à plusieurs repositories, gestion des erreurs métier.

| Service | Responsabilité |
|---|---|
| `AuthService` | Hash bcrypt, JWT creation/validation |
| `WorkflowService` | Validation graphe JSON, CRUD avec règles métier |
| `ExecutionService` | Création d'exécution, dispatch vers worker, annulation |
| `CredentialService` | Chiffrement/déchiffrement Fernet |

### `app/engine/` — Moteur d'exécution ⬜

Voir [docs/WORKFLOW_ENGINE.md](WORKFLOW_ENGINE.md) pour la documentation complète.

Composants prévus :

| Fichier | Rôle |
|---|---|
| `runner.py` | Trie les nœuds topologiquement, exécute en ordre, transmet les outputs |
| `context.py` | Maintient l'état de l'exécution en cours (outputs, statuts par nœud) |
| `node_executor.py` | Dispatch vers l'intégration appropriée selon `node.type` |
| `validators.py` | Vérifie que le graphe est un DAG valide avant exécution |

### `app/triggers/` — Triggers ⬜

| Trigger | Mécanisme |
|---|---|
| Manual | Endpoint `POST /workflows/{id}/execute` → enqueue direct |
| Webhook | Endpoint `POST /webhooks/{token}` → lookup workflow → enqueue |
| Schedule | APScheduler ou Celery Beat → enqueue selon expression cron |

### `app/integrations/` — Intégrations ⬜

Voir [docs/INTEGRATIONS.md](INTEGRATIONS.md) pour la documentation complète.

### `app/workers/` — Workers asynchrones ⬜

Un worker consomme les tâches en attente dans Redis, instancie l'engine.runner, et persiste les résultats.

---

## Dépendances inter-modules

```
api/
 └─► services/
      ├─► repositories/  ──────────────► models/
      ├─► engine/         ──────────────► integrations/
      │    └─► context/
      └─► triggers/

workers/
 └─► engine/runner
      └─► node_executor
           └─► integrations/

config/settings  ◄──── tous les modules
```

Règle de dépendance : **aucune couche ne peut importer depuis une couche supérieure**. Les repositories n'importent pas les services. Les modèles n'importent pas les schemas. Les intégrations n'importent pas l'engine.

---

## Cycle de vie d'une exécution

```
1. Trigger reçu
   │
   ▼
2. ExecutionService.create_execution()
   → INSERT WorkflowExecution (status=queued)
   → Enqueue tâche Redis (execution_id)
   │
   ▼
3. Worker consomme la tâche
   → UPDATE status=running
   │
   ▼
4. engine.runner.run(execution)
   → engine.validators.validate_graph(workflow.graph)
   → Tri topologique des nœuds
   → Pour chaque nœud :
       ├── engine.node_executor.execute(node, context)
       │     → appel intégration appropriée
       │     → INSERT NodeExecution (status, output, duration)
       │     → UPDATE ExecutionContext.outputs[node_id]
       ├── Si nœud IF : évaluation condition → sélection branche
       └── Si erreur : UPDATE NodeExecution(status=failed), propagation
   │
   ▼
5. Fin de graphe
   → UPDATE WorkflowExecution (status=success|failed)
   → Calcul durée totale
   │
   ▼
6. Résultat disponible via GET /executions/{id}
```

---

## Flux de données

```
HTTP Request
    │
    ▼
FastAPI Router (validation Pydantic)
    │
    ▼
Service Layer (logique métier)
    │
    ├──► Repository Layer ──► PostgreSQL (SQLAlchemy + Alembic)
    │
    └──► ExecutionService ──► Redis Queue
                                    │
                                    ▼
                              Worker Process
                                    │
                                    ▼
                              Engine Runner
                              (context en RAM)
                                    │
                                    ▼
                           Node Executor
                           (HTTP, Gmail, Telegram, ML…)
                                    │
                                    ▼
                           NodeExecution logs ──► PostgreSQL
```

---

## Composants infrastructure

| Composant | Rôle | Version prévue |
|---|---|---|
| PostgreSQL | Persistance principale (workflows, exécutions, users, creds) | 15+ |
| Redis | File de tâches asynchrones, état transitoire des workers | 7+ |
| Alembic | Migrations de schéma DB | latest |
| FastAPI | Framework API REST | 0.111+ |
| SQLAlchemy | ORM + gestion des sessions | 2.0+ |
| Pydantic v2 | Validation des données | 2.x |
| python-jose / PyJWT | JWT | latest |
| cryptography (Fernet) | Chiffrement des credentials | latest |
| APScheduler | Schedule triggers (cron) | 3.x |
| httpx | Appels HTTP dans les intégrations | latest |
| pytest | Tests | latest |

---

## Décisions d'architecture

### Séparation workers/API

L'API ne bloque jamais sur une exécution. Toute exécution est **asynchrone** : l'API enregistre la tâche et retourne immédiatement un `execution_id`. Le worker est un processus séparé qui consomme la file Redis.

Avantage : scalabilité horizontale des workers, résilience (le worker peut redémarrer sans affecter l'API).

### Isolation utilisateur

Chaque table possède un `user_id` (foreign key vers `users`). Toutes les requêtes de repository filtrent **systématiquement** par `user_id`. Aucun accès cross-user n'est possible au niveau de la couche repository.

### No-code execution

Le moteur **n'exécute jamais de code Python arbitraire fourni par l'utilisateur**. Les nœuds sont des types prédéfinis (`http_request`, `set_data`, `if_condition`, `gmail_send`, etc.) avec des paramètres validés par Pydantic.

### Chiffrement des credentials

Les credentials externes (tokens OAuth, clés API, tokens Telegram) sont chiffrés via Fernet (clé symétrique AES-128) avant insertion en base. La clé Fernet est stockée uniquement en variable d'environnement (`ENCRYPTION_KEY`), jamais en base.

---

> Ce document sera mis à jour à chaque phase d'implémentation. Aucune architecture n'est figée avant que le code correspondant n'existe et ne soit testé.
