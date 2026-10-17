# Tests — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucun test n'existe. Ce document décrit la stratégie et les scénarios **prévus**.

---

## Table des matières

- [Stratégie de test](#stratégie-de-test)
- [Structure des tests](#structure-des-tests)
- [Configuration Pytest](#configuration-pytest)
- [Tests unitaires](#tests-unitaires)
- [Tests d'intégration](#tests-dintégration)
- [Scénarios d'échec](#scénarios-déchec)
- [Commandes](#commandes)
- [Couverture minimale attendue](#couverture-minimale-attendue)

---

## Stratégie de test ⬜

### Pyramid de tests prévue

```
        ▲ E2E (optionnel, phase 3)
       ███
      ██████  Intégration (API + DB en test)
     ██████████████ Unitaires (moteur, services, validators)
```

### Règle principale

**Aucune intégration n'est déclarée terminée sans test qui passe.** Cette règle est énoncée explicitement dans `Prompt 2B.md`.

### Environnement de test

- Base de données : PostgreSQL de test (Docker Compose `test` profile) ou SQLite en mémoire pour les tests unitaires purs
- Redis : instance de test ou mock
- Services externes (Gmail, Telegram, ML) : **toujours mockés** en test

---

## Structure des tests

```
tests/
├── conftest.py               # Fixtures partagées (db, client, users)
├── unit/
│   ├── test_engine.py        # Moteur d'exécution (runner, context, node_executor)
│   ├── test_validators.py    # Validation des graphes
│   ├── test_auth_service.py  # Hash MDP, JWT
│   ├── test_credential_service.py  # Chiffrement Fernet
│   ├── test_workflow_service.py    # Validation métier
│   └── test_integrations.py  # HTTP Request (SSRF, headers, body)
└── integration/
    ├── test_auth_api.py       # POST /auth/register, POST /auth/login
    ├── test_workflows_api.py  # CRUD /workflows
    ├── test_executions_api.py # POST /execute, GET /executions
    ├── test_triggers_api.py   # Webhook, Schedule
    └── test_isolation.py      # Isolation inter-utilisateurs
```

---

## Configuration Pytest ⬜

### `pyproject.toml` ou `pytest.ini`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
env = [
    "DATABASE_URL=postgresql://test:test@localhost:5433/flowforge_test",
    "REDIS_URL=redis://localhost:6380/1",
    "SECRET_KEY=test-secret-key-not-for-production",
    "ENCRYPTION_KEY=test-fernet-key-32-bytes-long====",
    "ALGORITHM=HS256",
]
```

### `tests/conftest.py` (prévu)

```python
# Pseudocode — non implémenté
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Base
from app.dependencies import get_db

TEST_DATABASE_URL = "postgresql://test:test@localhost:5433/flowforge_test"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)

@pytest.fixture
def user_token(client):
    client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    })
    response = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123"
    })
    return response.json()["access_token"]

@pytest.fixture
def auth_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}
```

---

## Tests unitaires

### `test_validators.py` ⬜

```python
# Scénarios prévus — non implémentés

def test_validate_graph_valid_dag():
    """Un graphe valide avec un trigger et un nœud HTTP passe la validation."""

def test_validate_graph_no_trigger():
    """Un graphe sans nœud trigger lève GraphValidationError."""

def test_validate_graph_multiple_triggers():
    """Un graphe avec deux triggers lève GraphValidationError."""

def test_validate_graph_cycle_detected():
    """Un graphe avec un cycle (A→B→A) lève GraphValidationError."""

def test_validate_graph_unknown_node_in_edge():
    """Une arête référençant un node_id inexistant lève GraphValidationError."""

def test_validate_graph_if_missing_branches():
    """Un nœud if_condition sans branche true ou false lève GraphValidationError."""

def test_validate_graph_invalid_node_config():
    """Un nœud http_request sans 'url' lève NodeConfigError."""
```

### `test_engine.py` ⬜

```python
# Scénarios prévus — non implémentés

def test_engine_runs_simple_graph():
    """Manual trigger → HTTP request s'exécute dans l'ordre topologique."""

def test_engine_transmits_output_between_nodes():
    """L'output du nœud A est accessible dans le template du nœud B."""

def test_engine_if_true_branch():
    """Le nœud IF évalue 'true' et exécute uniquement la branche true."""

def test_engine_if_false_branch():
    """Le nœud IF évalue 'false' et exécute uniquement la branche false."""

def test_engine_skips_inactive_branch():
    """Les nœuds sur la branche inactive ont le statut SKIPPED."""

def test_engine_marks_failed_on_node_error():
    """Si un nœud lève une exception, le workflow passe en FAILED."""

def test_engine_resolves_template_references():
    """{{node_1.body.user_id}} est résolu correctement depuis le contexte."""

def test_engine_raises_on_unresolved_template():
    """Un template référençant un nœud non exécuté lève TemplateError."""
```

### `test_auth_service.py` ⬜

```python
def test_hash_password_not_equal_to_original():
    """Le hash bcrypt n'est pas égal au mot de passe en clair."""

def test_verify_password_correct():
    """La vérification du bon mot de passe retourne True."""

def test_verify_password_incorrect():
    """La vérification d'un mauvais mot de passe retourne False."""

def test_create_token_contains_user_id():
    """Le JWT créé contient le sub=user_id."""

def test_expired_token_raises():
    """Un token expiré lève une exception à la vérification."""
```

### `test_credential_service.py` ⬜

```python
def test_encrypt_decrypt_roundtrip():
    """Chiffrer puis déchiffrer retourne les données originales."""

def test_encrypted_data_differs_from_plaintext():
    """Les données chiffrées ne contiennent pas le secret en clair."""

def test_wrong_key_raises_on_decrypt():
    """Déchiffrer avec la mauvaise clé lève une exception."""
```

### `test_integrations.py` ⬜

```python
def test_ssrf_blocks_private_ip():
    """Une URL vers 192.168.1.1 lève SSRFProtectionError."""

def test_ssrf_blocks_localhost():
    """Une URL vers http://localhost:5432 est bloquée."""

def test_ssrf_blocks_aws_metadata():
    """Une URL vers http://169.254.169.254 est bloquée."""

def test_ssrf_allows_public_url():
    """Une URL vers https://api.example.com est autorisée."""

def test_ssrf_blocks_file_scheme():
    """Une URL avec schéma file:// est bloquée."""
```

---

## Tests d'intégration

### `test_auth_api.py` ⬜

```python
def test_register_success(client):
    """POST /auth/register crée un utilisateur et retourne 201."""

def test_register_duplicate_email(client):
    """POST /auth/register avec email existant retourne 409."""

def test_login_success(client):
    """POST /auth/login retourne un token JWT valide."""

def test_login_wrong_password(client):
    """POST /auth/login avec mauvais mot de passe retourne 401."""

def test_get_me_authenticated(client, auth_headers):
    """GET /auth/me avec token valide retourne le profil."""

def test_get_me_unauthenticated(client):
    """GET /auth/me sans token retourne 401."""
```

### `test_workflows_api.py` ⬜

```python
def test_create_workflow_success(client, auth_headers):
    """POST /workflows crée un workflow et retourne 201."""

def test_create_workflow_invalid_graph(client, auth_headers):
    """POST /workflows avec graphe sans trigger retourne 422."""

def test_list_workflows_empty(client, auth_headers):
    """GET /workflows retourne une liste vide pour un nouvel utilisateur."""

def test_get_workflow_not_found(client, auth_headers):
    """GET /workflows/{id} avec ID inexistant retourne 404."""

def test_delete_workflow_success(client, auth_headers):
    """DELETE /workflows/{id} supprime le workflow et retourne 204."""
```

### `test_isolation.py` ⬜

```python
def test_user_cannot_access_other_user_workflow(client):
    """L'utilisateur B ne peut pas GET le workflow de l'utilisateur A → 404."""

def test_user_cannot_execute_other_user_workflow(client):
    """L'utilisateur B ne peut pas POST /execute sur le workflow de A → 404."""

def test_user_cannot_access_other_user_execution(client):
    """L'utilisateur B ne peut pas GET l'exécution de A → 404."""

def test_user_cannot_access_other_user_credentials(client):
    """L'utilisateur B ne peut pas GET les credentials de A."""
```

### `test_executions_api.py` ⬜

```python
def test_execute_manual_trigger_returns_202(client, auth_headers):
    """POST /workflows/{id}/execute retourne 202 avec execution_id."""

def test_execution_status_queued_initially(client, auth_headers):
    """GET /executions/{id} retourne status=queued juste après le déclenchement."""

def test_execution_has_node_logs(client, auth_headers):
    """GET /executions/{id} contient node_executions après traitement."""

def test_cancel_running_execution(client, auth_headers):
    """POST /executions/{id}/cancel retourne 200 avec status=cancelled."""
```

---

## Scénarios d'échec

Ces scénarios testent la robustesse du moteur face aux erreurs :

| Scénario | Comportement attendu |
|---|---|
| Nœud HTTP : URL injoignable (timeout) | `node.status=failed`, `workflow.status=failed`, message d'erreur sans URL interne |
| Nœud HTTP : URL SSRF bloquée | Nœud `failed` avec message "SSRF protection: blocked" |
| Credential invalide ou expiré | Nœud `failed`, pas de token dans les logs |
| Graphe avec cycle (détecté à l'exécution) | Workflow `failed` avant démarrage |
| Worker crash en cours d'exécution | Workflow reste `running` → nécessite un job de réconciliation |
| Execution_id Redis consommé deux fois | Idempotence : second traitement ignoré |
| Template non résolu | Nœud `failed` avec "Unresolved reference: {node_id}" |
| Timeout global du workflow | `workflow.status=failed`, nœud en cours marqué `failed` |

---

## Commandes

```bash
# Installer les dépendances de test
pip install -r requirements-dev.txt

# Tous les tests
pytest

# Avec rapport de couverture HTML
pytest --cov=app --cov-report=html --cov-report=term-missing

# Tests unitaires uniquement
pytest tests/unit/ -v

# Tests d'intégration uniquement
pytest tests/integration/ -v

# Un fichier spécifique
pytest tests/unit/test_engine.py -v

# Filtre par nom de test
pytest -k "test_ssrf" -v

# Arrêter au premier échec
pytest -x

# Verbose avec affichage des prints
pytest -v -s
```

---

## Couverture minimale attendue

| Module | Couverture cible |
|---|---|
| `app/engine/` | 90% |
| `app/engine/validators.py` | 95% |
| `app/services/` | 85% |
| `app/api/` | 80% |
| `app/integrations/` | 80% |
| `app/repositories/` | 75% |

> Ces cibles sont indicatives. La priorité est la **couverture des chemins critiques** (sécurité, isolation, SSRF) plutôt que le pourcentage global.

---

> Aucun test n'existe à ce jour. Ce document sera mis à jour au fur et à mesure de l'implémentation.
> La règle est : **tout code fusionné doit avoir des tests qui passent.**
