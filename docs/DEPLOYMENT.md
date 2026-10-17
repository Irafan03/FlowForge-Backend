# Déploiement — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucun fichier Docker ni configuration de déploiement n'existe encore.

---

## Table des matières

- [Docker Compose local](#docker-compose-local)
- [Dockerfile](#dockerfile)
- [Variables d'environnement](#variables-denvironnement)
- [Services et dépendances](#services-et-dépendances)
- [Workers](#workers)
- [Migrations en déploiement](#migrations-en-déploiement)
- [Logs](#logs)
- [Healthchecks](#healthchecks)
- [Considérations production](#considérations-production)

---

## Docker Compose local ⬜

### `docker-compose.yml` prévu

```yaml
# Non implémenté — structure prévue

version: "3.9"

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: flowforge
      POSTGRES_USER: flowforge
      POSTGRES_PASSWORD: flowforge_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U flowforge"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --save 60 1 --loglevel warning
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app  # dev: hot-reload
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: python -m app.workers.main
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Commandes

```bash
# Démarrer tous les services
docker compose up --build

# En arrière-plan
docker compose up -d --build

# Voir les logs
docker compose logs -f api
docker compose logs -f worker

# Arrêter
docker compose down

# Arrêter et supprimer les volumes (DESTRUCTIF)
docker compose down -v

# Rebuild d'un seul service
docker compose up --build api
```

---

## Dockerfile ⬜

```dockerfile
# Non implémenté — structure prévue

FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Utilisateur non-root (sécurité)
RUN useradd -m -u 1000 flowforge
USER flowforge

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Variables d'environnement

Toutes les variables sont documentées dans [`.env.example`](../.env.example).

### Variables obligatoires

| Variable | Exemple | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@db:5432/flowforge` | Connexion PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | Connexion Redis |
| `SECRET_KEY` | `changeme-in-production-use-strong-key` | Clé de signature JWT |
| `ENCRYPTION_KEY` | `(Fernet key)` | Clé de chiffrement des credentials |

### Variables optionnelles avec défaut

| Variable | Défaut | Description |
|---|---|---|
| `ALGORITHM` | `HS256` | Algorithme JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Durée de vie du token |
| `LOG_LEVEL` | `INFO` | Niveau de log |
| `WORKERS_COUNT` | `1` | Nombre de workers Uvicorn |

### Variables conditionnelles (selon les intégrations activées)

| Variable | Requise pour |
|---|---|
| `GOOGLE_CLIENT_ID` | Gmail OAuth |
| `GOOGLE_CLIENT_SECRET` | Gmail OAuth |
| `GOOGLE_REDIRECT_URI` | Gmail OAuth |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot |
| `FLOWFORGE_ML_URL` | ML Prediction |

---

## Services et dépendances

### Ordre de démarrage

```
PostgreSQL → Redis → API (migrations auto) → Worker
```

L'API attend que PostgreSQL et Redis soient `healthy` avant de démarrer (via `depends_on` avec `condition: service_healthy`).

### Dépendances réseau

| Service | Dépendances |
|---|---|
| `api` | `db` (PostgreSQL), `redis` |
| `worker` | `db` (PostgreSQL), `redis` |
| `db` | aucune |
| `redis` | aucune |

---

## Workers ⬜

### Architecture

Les workers sont des processus séparés qui consomment les tâches depuis Redis. Ils partagent la même image Docker que l'API mais exécutent une commande différente :

```bash
# API
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Worker
python -m app.workers.main
```

### Scalabilité horizontale

Pour augmenter la capacité de traitement, lancer plusieurs instances du worker :

```yaml
worker:
  ...
  deploy:
    replicas: 3  # 3 workers en parallèle
```

### Gestion des crashs

Le worker est configuré avec `restart: unless-stopped`. En cas de crash, Docker le redémarre automatiquement.

**Problème connu (non résolu)** : si un worker crash pendant l'exécution d'un workflow, ce workflow reste en statut `running` indéfiniment. Un job de réconciliation est prévu mais pas encore spécifié.

---

## Migrations en déploiement ⬜

### Approche recommandée

Les migrations Alembic doivent être exécutées **avant** le démarrage de l'API. Options :

**Option 1 : Commande séparée (recommandée)**
```bash
# Avant docker compose up
docker compose run --rm api alembic upgrade head
```

**Option 2 : Init container**
```yaml
# Dans docker-compose.yml
migrate:
  build: .
  command: alembic upgrade head
  env_file: .env
  depends_on:
    db:
      condition: service_healthy
```

**Option 3 : Startup de l'API (déconseillé en production)**
```python
# Dans app/main.py — déconseillé car non idempotent avec plusieurs instances
@app.on_event("startup")
async def startup():
    run_migrations()
```

---

## Logs ⬜

### Format prévu

Logs structurés JSON pour faciliter l'agrégation (ELK, CloudWatch, etc.) :

```json
{
  "timestamp": "2026-10-16T19:00:00Z",
  "level": "INFO",
  "service": "api",
  "message": "Workflow execution started",
  "execution_id": "exec_abc123",
  "workflow_id": "wf_xyz",
  "user_id": "user_123"
}
```

### Niveaux de log

| Niveau | Usage |
|---|---|
| `DEBUG` | Détails d'exécution (désactivé en prod) |
| `INFO` | Démarrage des services, exécutions créées |
| `WARNING` | Retries, tokens bientôt expirés |
| `ERROR` | Nœuds en échec, erreurs non récupérées |
| `CRITICAL` | Panne de base de données, impossible de démarrer |

### Règles de sécurité

- Jamais de secrets dans les logs (tokens, clés, mots de passe)
- Pas de données personnelles dans les logs de niveau INFO+ sans consentement
- Les messages d'erreur des nœuds sont tronqués à 500 caractères avant logging

---

## Healthchecks ⬜

### Endpoint `GET /health`

```json
{
  "status": "ok",
  "db": "connected",
  "redis": "connected",
  "version": "0.1.0"
}
```

Retourne `503 Service Unavailable` si PostgreSQL ou Redis est inaccessible.

### Docker healthcheck

```yaml
api:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

---

## Considérations production ⬜

### Ce qui manque avant un déploiement production

| Élément | Statut |
|---|---|
| HTTPS / TLS termination (nginx ou load balancer) | ⬜ Non prévu |
| Secrets management (Vault, AWS Secrets Manager) | ⬜ Non prévu |
| Monitoring / alerting (Prometheus, Grafana) | ⬜ Non prévu |
| Centralisation des logs | ⬜ Non prévu |
| Backup automatique PostgreSQL | ⬜ Non prévu |
| Job de réconciliation des exécutions bloquées | ⬜ Non prévu |
| Rate limiting global (nginx / API Gateway) | ⬜ Non prévu |
| CI/CD pipeline | ⬜ Non prévu |

### Variables à changer impérativement en production

```
SECRET_KEY        → Générer avec: python -c "import secrets; print(secrets.token_hex(32))"
ENCRYPTION_KEY    → Générer avec: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATABASE_URL      → Utiliser un mot de passe fort, ne pas utiliser "flowforge_password"
```

---

> Ce document sera complété lorsqu'un `docker-compose.yml` et un `Dockerfile` réels seront créés et testés.
