# FlowForge Backend

> ⚠️ **STATUT : SPÉCIFICATION — Aucun code n'a encore été implémenté.**
> Ce repository ne contient que les fichiers de spécification (`Prompt 2A.md`, `Prompt 2B.md`).
> Toute la documentation ci-dessous décrit l'architecture **prévue**, pas le code existant.

---

## Table des matières

- [Présentation](#présentation)
- [Architecture globale](#architecture-globale)
- [Prérequis](#prérequis)
- [Installation locale](#installation-locale)
- [Configuration](#configuration)
- [Lancement](#lancement)
- [Tests](#tests)
- [Docker](#docker)
- [Documentation complémentaire](#documentation-complémentaire)
- [État d'implémentation](#état-dimplémentation)

---

## Présentation

**FlowForge Backend** est le moteur d'automatisation de la plateforme FlowForge AI. Il permet aux utilisateurs de créer, configurer et exécuter des workflows visuels composés de nœuds interconnectés : triggers (déclencheurs), transformations de données, appels HTTP, intégrations (Gmail, Telegram) et prédictions ML.

Le backend expose une API REST en FastAPI, persiste les workflows et leurs historiques d'exécution dans PostgreSQL, et délègue les exécutions à des workers asynchrones via Redis.

### Fonctionnalités prévues

| Fonctionnalité | Statut |
|---|---|
| Authentification JWT + isolation utilisateur | ⬜ Non implémenté |
| CRUD des workflows (graphe JSON) | ⬜ Non implémenté |
| Validation des nœuds et connexions | ⬜ Non implémenté |
| Moteur d'exécution (graphe + branches IF) | ⬜ Non implémenté |
| Statuts : queued / running / success / failed / cancelled | ⬜ Non implémenté |
| Manual Trigger | ⬜ Non implémenté |
| Webhook Trigger | ⬜ Non implémenté |
| Schedule Trigger (cron) | ⬜ Non implémenté |
| Gmail Trigger + Send (OAuth 2.0) | ⬜ Non implémenté |
| Telegram Trigger + Send (Bot API) | ⬜ Non implémenté |
| HTTP Request (+ protection SSRF) | ⬜ Non implémenté |
| ML Prediction (via flowforge-ml) | ⬜ Non implémenté |
| Historique d'exécution + logs par nœud | ⬜ Non implémenté |
| Gestion sécurisée des credentials | ⬜ Non implémenté |
| Migrations Alembic | ⬜ Non implémenté |
| Docker Compose (API + DB + Redis + Worker) | ⬜ Non implémenté |

---

## Architecture globale

```
flowforge-backend/
├── app/
│   ├── api/              # Routeurs FastAPI (endpoints REST)
│   ├── config/           # Settings Pydantic, variables d'env
│   ├── models/           # Modèles SQLAlchemy (ORM)
│   ├── schemas/          # Schémas Pydantic (validation E/S)
│   ├── repositories/     # Accès base de données (CRUD)
│   ├── services/         # Logique métier
│   ├── engine/           # Moteur d'exécution des workflows
│   ├── triggers/         # Manual, Webhook, Schedule
│   ├── integrations/     # Gmail, Telegram, HTTP, ML
│   └── workers/          # Workers asynchrones (Redis)
├── migrations/           # Scripts Alembic
├── tests/                # Tests unitaires et d'intégration
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour le détail des dépendances inter-modules.

---

## Prérequis

> Ces prérequis sont basés sur la **spécification prévue**. Ils seront à valider lors de l'implémentation.

- Python **3.11+**
- PostgreSQL **15+**
- Redis **7+**
- Docker + Docker Compose (pour le déploiement conteneurisé)
- Compte Google Cloud Project (pour Gmail OAuth 2.0)
- Token Telegram Bot (pour les intégrations Telegram)

---

## Installation locale

> ⚠️ Ces commandes sont indicatives. Le projet n'étant pas encore implémenté, elles ne sont pas exécutables dans l'état actuel.

### 1. Cloner le repository

```bash
git clone https://github.com/your-org/flowforge-backend.git
cd flowforge-backend
```

### 2. Créer un environnement virtuel

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos valeurs
```

### 5. Appliquer les migrations

```bash
alembic upgrade head
```

---

## Configuration

Toutes les configurations passent par des variables d'environnement, chargées via un module `config/settings.py` basé sur `pydantic-settings`.

Les variables minimales requises sont documentées dans [`.env.example`](.env.example).

Variables principales :

| Variable | Description |
|---|---|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `REDIS_URL` | URL Redis pour les tâches async |
| `SECRET_KEY` | Clé JWT de signature des tokens |
| `ALGORITHM` | Algorithme JWT (ex. `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie des tokens |
| `ENCRYPTION_KEY` | Clé Fernet pour le chiffrement des credentials |
| `GOOGLE_CLIENT_ID` | Client ID OAuth Google |
| `GOOGLE_CLIENT_SECRET` | Secret OAuth Google |
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram |
| `FLOWFORGE_ML_URL` | URL du service flowforge-ml |

---

## Lancement

### Mode développement

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Lancer un worker asynchrone

```bash
# Commande exacte à définir selon l'implémentation (Celery, ARQ, RQ, etc.)
python -m app.workers.main
```

L'API sera disponible sur `http://localhost:8000`.
La documentation interactive Swagger sera sur `http://localhost:8000/docs`.

---

## Tests

> ⚠️ Aucun test n'existe encore. La suite ci-dessous décrit les **commandes prévues**.

```bash
# Tous les tests
pytest

# Avec couverture
pytest --cov=app --cov-report=html

# Tests unitaires uniquement
pytest tests/unit/

# Tests d'intégration uniquement
pytest tests/integration/

# Tests d'un module spécifique
pytest tests/unit/test_engine.py -v
```

Voir [docs/TESTING.md](docs/TESTING.md) pour les scénarios détaillés.

---

## Docker

> ⚠️ Le fichier `docker-compose.yml` n'a pas encore été créé.

### Lancer l'ensemble des services

```bash
docker compose up --build
```

### Services du Docker Compose prévu

| Service | Image | Port exposé |
|---|---|---|
| `api` | `flowforge-backend` (Dockerfile local) | `8000` |
| `db` | `postgres:15-alpine` | `5432` |
| `redis` | `redis:7-alpine` | `6379` |
| `worker` | `flowforge-backend` (même image) | — |

### Arrêter et nettoyer

```bash
docker compose down -v
```

Voir [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) pour la configuration complète.

---

## Documentation complémentaire

| Document | Contenu |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, dépendances, flux de données |
| [docs/API.md](docs/API.md) | Endpoints, paramètres, réponses, erreurs |
| [docs/WORKFLOW_ENGINE.md](docs/WORKFLOW_ENGINE.md) | Format JSON, validation, exécution, IF |
| [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) | Gmail, Telegram, Webhook, Schedule, HTTP, ML |
| [docs/DATABASE.md](docs/DATABASE.md) | Modèles, relations, migrations |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth, isolation, chiffrement, SSRF |
| [docs/TESTING.md](docs/TESTING.md) | Stratégie de test, scénarios, commandes |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, variables, logs, production |

---

## État d'implémentation

**À la date du 16 octobre 2026, ce repository ne contient aucun code source.**

Les deux fichiers présents (`Prompt 2A.md`, `Prompt 2B.md`) sont des spécifications destinées à guider l'implémentation. L'ensemble de la documentation reflète l'architecture *prévue* et doit être mis à jour au fur et à mesure que le code est écrit et testé.

La règle stricte est : **aucune fonctionnalité ne peut être marquée comme implémentée sans fichier de code correspondant et test qui passe.**
