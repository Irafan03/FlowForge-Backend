# Base de données — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucun modèle ni migration n'est implémenté. Source : `Prompt 2B.md`.

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Modèles SQLAlchemy](#modèles-sqlalchemy)
- [Relations entre tables](#relations-entre-tables)
- [Stratégie de persistance](#stratégie-de-persistance)
- [Migrations Alembic](#migrations-alembic)
- [Index et performances](#index-et-performances)

---

## Vue d'ensemble

FlowForge utilise **PostgreSQL 15+** comme base de données principale. L'ORM est **SQLAlchemy 2.0** en mode synchrone (async envisageable en phase 2). Les migrations sont gérées par **Alembic**.

**Schéma prévu (6 tables) :**

```
users
  └─► workflows
        └─► triggers
        └─► workflow_executions
              └─► node_executions
  └─► credentials
```

---

## Modèles SQLAlchemy

### Table `users` ⬜

```python
# Pseudocode — non implémenté
class User(Base):
    __tablename__ = "users"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password: str = Column(String(255), nullable=False)
    full_name: str = Column(String(255), nullable=True)
    is_active: bool = Column(Boolean, default=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), onupdate=func.now())

    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="user", cascade="all, delete-orphan")
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK, default uuid4 |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL, INDEX |
| `hashed_password` | VARCHAR(255) | NOT NULL |
| `full_name` | VARCHAR(255) | nullable |
| `is_active` | BOOLEAN | default true |
| `created_at` | TIMESTAMPTZ | server default now() |
| `updated_at` | TIMESTAMPTZ | auto-update |

---

### Table `workflows` ⬜

```python
# Pseudocode — non implémenté
class Workflow(Base):
    __tablename__ = "workflows"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: UUID = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=True)
    graph: dict = Column(JSONB, nullable=False)       # Graphe JSON complet
    is_active: bool = Column(Boolean, default=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="workflows")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")
    trigger = relationship("Trigger", back_populates="workflow", uselist=False, cascade="all, delete-orphan")
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK users.id, NOT NULL, INDEX |
| `name` | VARCHAR(255) | NOT NULL |
| `description` | TEXT | nullable |
| `graph` | JSONB | NOT NULL |
| `is_active` | BOOLEAN | default false |
| `created_at` | TIMESTAMPTZ | server default now() |
| `updated_at` | TIMESTAMPTZ | auto-update |

> Le champ `graph` est de type **JSONB** (PostgreSQL natif) pour permettre des requêtes et index GIN sur le contenu JSON.

---

### Table `triggers` ⬜

```python
# Pseudocode — non implémenté
class Trigger(Base):
    __tablename__ = "triggers"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: UUID = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), unique=True, nullable=False)
    type: str = Column(String(50), nullable=False)   # webhook, schedule, gmail, telegram
    config: dict = Column(JSONB, nullable=False, default={})
    webhook_token: str = Column(String(255), unique=True, nullable=True, index=True)
    cron_expression: str = Column(String(100), nullable=True)
    timezone: str = Column(String(100), nullable=True)
    next_run_at: datetime = Column(DateTime(timezone=True), nullable=True)
    is_active: bool = Column(Boolean, default=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK |
| `workflow_id` | UUID | FK workflows.id, UNIQUE |
| `type` | VARCHAR(50) | NOT NULL |
| `config` | JSONB | default {} |
| `webhook_token` | VARCHAR(255) | UNIQUE, nullable, INDEX |
| `cron_expression` | VARCHAR(100) | nullable |
| `timezone` | VARCHAR(100) | nullable |
| `next_run_at` | TIMESTAMPTZ | nullable |
| `is_active` | BOOLEAN | default true |

---

### Table `workflow_executions` ⬜

```python
# Pseudocode — non implémenté
class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: UUID = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False, index=True)
    user_id: UUID = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status: str = Column(String(20), nullable=False, default="queued")  # queued/running/success/failed/cancelled
    trigger_type: str = Column(String(50), nullable=False)
    input_data: dict = Column(JSONB, nullable=True, default={})
    error: str = Column(Text, nullable=True)
    started_at: datetime = Column(DateTime(timezone=True), nullable=True)
    finished_at: datetime = Column(DateTime(timezone=True), nullable=True)
    duration_ms: int = Column(Integer, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("Workflow", back_populates="executions")
    node_executions = relationship("NodeExecution", back_populates="execution", cascade="all, delete-orphan")
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK |
| `workflow_id` | UUID | FK workflows.id, INDEX |
| `user_id` | UUID | FK users.id, INDEX |
| `status` | VARCHAR(20) | NOT NULL, default "queued" |
| `trigger_type` | VARCHAR(50) | NOT NULL |
| `input_data` | JSONB | nullable |
| `error` | TEXT | nullable |
| `started_at` | TIMESTAMPTZ | nullable |
| `finished_at` | TIMESTAMPTZ | nullable |
| `duration_ms` | INTEGER | nullable |
| `created_at` | TIMESTAMPTZ | server default now() |

---

### Table `node_executions` ⬜

```python
# Pseudocode — non implémenté
class NodeExecution(Base):
    __tablename__ = "node_executions"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: UUID = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id"), nullable=False, index=True)
    node_id: str = Column(String(255), nullable=False)       # ID dans le graphe JSON
    node_type: str = Column(String(100), nullable=False)
    status: str = Column(String(20), nullable=False)         # running/success/failed/skipped
    output: dict = Column(JSONB, nullable=True)
    error: str = Column(Text, nullable=True)
    started_at: datetime = Column(DateTime(timezone=True), nullable=True)
    finished_at: datetime = Column(DateTime(timezone=True), nullable=True)
    duration_ms: int = Column(Integer, nullable=True)

    execution = relationship("WorkflowExecution", back_populates="node_executions")
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK |
| `execution_id` | UUID | FK workflow_executions.id, INDEX |
| `node_id` | VARCHAR(255) | NOT NULL |
| `node_type` | VARCHAR(100) | NOT NULL |
| `status` | VARCHAR(20) | NOT NULL |
| `output` | JSONB | nullable |
| `error` | TEXT | nullable |
| `started_at` | TIMESTAMPTZ | nullable |
| `finished_at` | TIMESTAMPTZ | nullable |
| `duration_ms` | INTEGER | nullable |

> ⚠️ Le champ `output` peut contenir des données sensibles (résultat d'un appel HTTP). Veiller à ne pas y stocker des secrets ou données personnelles trop volumineuses.

---

### Table `credentials` ⬜

```python
# Pseudocode — non implémenté
class Credential(Base):
    __tablename__ = "credentials"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: UUID = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    type: str = Column(String(50), nullable=False)   # api_key, oauth2_google, telegram_bot, http_header
    encrypted_data: bytes = Column(LargeBinary, nullable=False)   # Fernet-encrypted JSON
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="credentials")
```

| Colonne | Type | Contraintes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK users.id, INDEX |
| `name` | VARCHAR(255) | NOT NULL |
| `type` | VARCHAR(50) | NOT NULL |
| `encrypted_data` | BYTEA | NOT NULL |
| `created_at` | TIMESTAMPTZ | server default now() |
| `updated_at` | TIMESTAMPTZ | auto-update |

> Le champ `encrypted_data` contient le JSON des secrets (clés API, tokens OAuth) chiffré via Fernet. **Jamais en clair en base.**

---

## Relations entre tables

```
users (1)
  ├── (N) workflows
  │       ├── (1) triggers
  │       └── (N) workflow_executions
  │                   └── (N) node_executions
  └── (N) credentials
```

Toutes les suppressions sont en **cascade** : supprimer un utilisateur supprime tous ses workflows, exécutions, logs et credentials.

---

## Stratégie de persistance

### Sessions SQLAlchemy

- Une session par requête HTTP (via dépendance FastAPI `get_db`).
- Commit explicite après chaque opération d'écriture.
- Rollback automatique en cas d'exception.

```python
# Pseudocode — non implémenté
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

### Transactions pour les exécutions

Le cycle d'une exécution implique plusieurs transactions distinctes (pas une seule grande transaction) :

1. `INSERT workflow_execution (status=queued)` → commit → enqueue Redis
2. Worker : `UPDATE workflow_execution (status=running)` → commit
3. Pour chaque nœud : `INSERT node_execution` → commit (immédiat pour les logs en temps réel)
4. Fin : `UPDATE workflow_execution (status=success|failed)` → commit

Cette approche garantit que les logs de nœuds sont visibles en temps réel, même si le workflow est encore en cours.

### Soft delete

Prévu uniquement pour les workflows (champ `is_active`). Les autres entités sont supprimées définitivement (hard delete avec cascade).

---

## Migrations Alembic

### Initialisation ⬜

```bash
# À exécuter une seule fois
alembic init migrations

# Générer une première migration depuis les modèles
alembic revision --autogenerate -m "initial schema"

# Appliquer les migrations
alembic upgrade head
```

### Workflow de migration ⬜

```bash
# Créer une nouvelle migration après modification des modèles
alembic revision --autogenerate -m "add retry_count to node_executions"

# Vérifier le SQL généré
alembic upgrade head --sql

# Appliquer
alembic upgrade head

# Revenir en arrière d'une migration
alembic downgrade -1
```

### Configuration `alembic.ini` ⬜

```ini
[alembic]
script_location = migrations
sqlalchemy.url = %(DATABASE_URL)s
```

La valeur de `DATABASE_URL` est lue depuis les variables d'environnement dans `migrations/env.py`.

---

## Index et performances

Index prévus (au-delà des clés primaires et étrangères) :

| Table | Colonne(s) | Type | Justification |
|---|---|---|---|
| `users` | `email` | BTREE UNIQUE | Lookup login |
| `workflows` | `user_id` | BTREE | Filtrage par utilisateur |
| `workflow_executions` | `workflow_id` | BTREE | Historique d'un workflow |
| `workflow_executions` | `user_id` | BTREE | Liste toutes exécutions user |
| `workflow_executions` | `status` | BTREE | Filtrage par statut |
| `node_executions` | `execution_id` | BTREE | Logs d'une exécution |
| `triggers` | `webhook_token` | BTREE UNIQUE | Lookup webhook |
| `credentials` | `user_id` | BTREE | Liste credentials user |

Index GIN sur `workflows.graph` (optionnel, pour requêtes JSONB avancées) :
```sql
CREATE INDEX idx_workflows_graph ON workflows USING GIN (graph);
```

---

> Ce document sera mis à jour lors de chaque migration Alembic. Les modèles ci-dessus sont des **pseudocode de spécification**, pas du code fonctionnel.
