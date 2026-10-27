# FlowForge Backend

API et moteur d’exécution des workflows FlowForge AI. Le backend est construit avec FastAPI, SQLAlchemy, PostgreSQL, Redis et ARQ.

> Le dépôt contient du code, des migrations, des tests et une configuration Docker Compose. Les documents de conception dans `docs/` peuvent encore décrire des éléments prévus et ne remplacent pas le comportement du code actuel. Les tests n’ont pas été exécutés dans le cadre de cette mise à jour du README.

## Fonctionnalités présentes dans le code

| Domaine | Implémentation |
|---|---|
| Authentification | Inscription et connexion JWT |
| Workflows | Création, lecture, modification, suppression et lancement |
| Exécutions | Enqueue via ARQ, exécution des nœuds et consultation de l’historique |
| Déclencheurs | Manuel, webhook et planification |
| Intégrations | HTTP, Gmail, Telegram et prédiction ML |
| Credentials | Stockage chiffré et endpoints de gestion |
| Base de données | Modèles SQLAlchemy et migrations Alembic |
| Exécution locale | API, worker, PostgreSQL et Redis via Docker Compose |

La présence de code ne signifie pas que toutes les intégrations ont été vérifiées en conditions réelles. Consultez les tests existants dans `tests/` et la documentation de conception dans `docs/`.

## Structure

```text
app/          API, configuration, modèles, services, moteur, intégrations et worker
migrations/   Migrations Alembic
tests/        Tests unitaires et d’intégration
docs/         Documentation de conception et d’exploitation
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
```

## Prérequis

- Python 3.11+
- PostgreSQL 15+ et Redis 7+, ou Docker avec Docker Compose
- Les identifiants Google OAuth et le token Telegram uniquement si vous utilisez ces intégrations

## Installation locale

Depuis `FlowForge-Backend` :

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Éditez `.env` pour configurer les services et les secrets nécessaires. Les valeurs de développement par défaut ne conviennent pas à un déploiement public. N’ajoutez jamais votre `.env` au dépôt.

Démarrez PostgreSQL et Redis, puis appliquez les migrations et lancez l’API :

```powershell
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Dans un second terminal, lancez le worker ARQ :

```powershell
python -m app.workers.main
```

L’API répond sur `http://localhost:8000`; Swagger est disponible sur `/docs` et le contrôle de santé sur `/health`.

## Démarrage avec Docker Compose

Configurez `.env`, puis lancez les services :

```powershell
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose up --build
```

Compose démarre l’API, le worker, PostgreSQL, Redis ainsi qu’une base PostgreSQL séparée pour les tests. Pour arrêter les services sans supprimer les données :

```powershell
docker compose down
```

`docker compose down -v` supprime aussi les volumes de données.

## Tests

Les tests sont dans `tests/unit/` et `tests/integration/`. Les tests d’intégration ont besoin de la base PostgreSQL de test configurée dans `docker-compose.yml`.

```powershell
python -m pytest
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest --cov=app --cov-report=html
```

## Configuration

Les paramètres sont chargés par `app/config/settings.py` depuis l’environnement et le fichier `.env`. Les principaux paramètres sont :

| Variable | Usage |
|---|---|
| `DATABASE_URL` | Connexion PostgreSQL |
| `REDIS_URL` | Connexion Redis utilisée par ARQ |
| `SECRET_KEY` | Signature des JWT |
| `ALGORITHM` | Algorithme JWT (par défaut `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie du jeton |
| `ENCRYPTION_KEY` | Chiffrement des credentials |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth Google |
| `GOOGLE_REDIRECT_URI`, `FRONTEND_URL` | Redirection OAuth et URL du frontend |
| `TELEGRAM_BOT_TOKEN` | Intégration Telegram |
| `FLOWFORGE_ML_URL` | URL du service FlowForge ML |
| `ENVIRONMENT`, `LOG_LEVEL`, `APP_VERSION` | Environnement et paramètres de l’application |

Voir `.env.example` pour les valeurs par défaut de développement.

## Documentation

- [AI Agent with Ollama](docs/OLLAMA_AGENT.md)
- [Google Sheets workflow action](docs/GOOGLE_SHEETS.md)

- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Moteur de workflows](docs/WORKFLOW_ENGINE.md)
- [Intégrations](docs/INTEGRATIONS.md)
- [Base de données](docs/DATABASE.md)
- [Sécurité](docs/SECURITY.md)
- [Tests](docs/TESTING.md)
- [Déploiement](docs/DEPLOYMENT.md)

Ces documents ont été rédigés à l’origine comme spécifications. Vérifiez les routes et comportements dans `app/` lorsqu’une différence avec l’implémentation est possible.
