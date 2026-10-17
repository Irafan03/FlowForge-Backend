# API Reference — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucun endpoint n'est implémenté. Ce document décrit le contrat API **prévu**.
> Source : `Prompt 2B.md`. Tous les endpoints sont au statut ⬜ Non implémenté.

---

## Table des matières

- [Authentification](#authentification)
- [Conventions générales](#conventions-générales)
- [Codes d'erreur](#codes-derreur)
- [Endpoints Auth](#endpoints-auth)
- [Endpoints Workflows](#endpoints-workflows)
- [Endpoints Executions](#endpoints-executions)
- [Endpoints Triggers](#endpoints-triggers)
- [Endpoints Credentials](#endpoints-credentials)
- [Endpoints Health](#endpoints-health)

---

## Authentification

L'API utilise **JWT Bearer tokens**. Le token est obtenu via `POST /auth/login` et doit être inclus dans le header de toutes les requêtes protégées :

```
Authorization: Bearer <token>
```

- Algorithme : HS256 (configurable via `ALGORITHM`)
- Durée de vie : `ACCESS_TOKEN_EXPIRE_MINUTES` (défaut : 30 min)
- Payload du token : `{ "sub": "<user_id>", "exp": <timestamp> }`

Tous les endpoints listés ici (sauf `/auth/*`, `/health`, et `POST /webhooks/{token}`) requièrent ce header. Une requête sans token valide retourne `401 Unauthorized`.

---

## Conventions générales

- **Base URL** : `http://localhost:8000`
- **Format** : JSON (`Content-Type: application/json`)
- **Pagination** : paramètres `skip` (offset, défaut 0) et `limit` (max 100, défaut 20)
- **IDs** : UUID v4 (string)
- **Timestamps** : ISO 8601 UTC (`2026-10-16T19:00:00Z`)
- **Isolation** : chaque ressource est filtrée par `user_id` extrait du JWT. Un utilisateur ne peut jamais accéder aux ressources d'un autre.

---

## Codes d'erreur

| Code HTTP | Signification | Corps de réponse |
|---|---|---|
| 400 | Requête invalide (validation Pydantic échouée) | `{"detail": "..."}` |
| 401 | Token manquant ou expiré | `{"detail": "Not authenticated"}` |
| 403 | Ressource d'un autre utilisateur | `{"detail": "Forbidden"}` |
| 404 | Ressource introuvable | `{"detail": "Not found"}` |
| 409 | Conflit (ex. email déjà utilisé) | `{"detail": "..."}` |
| 422 | Erreur de validation Pydantic (détail champ par champ) | `{"detail": [...]}` |
| 500 | Erreur serveur interne | `{"detail": "Internal server error"}` |

---

## Endpoints Auth

### `POST /auth/register` ⬜

Crée un nouveau compte utilisateur.

**Corps de la requête :**
```json
{
  "email": "user@example.com",
  "password": "strongpassword123",
  "full_name": "Alice Dupont"
}
```

**Réponse 201 :**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "Alice Dupont",
  "created_at": "2026-10-16T19:00:00Z"
}
```

**Erreurs :**
- `409` : email déjà enregistré
- `422` : email invalide ou mot de passe trop court

---

### `POST /auth/login` ⬜

Authentifie un utilisateur et retourne un JWT.

**Corps de la requête :**
```json
{
  "email": "user@example.com",
  "password": "strongpassword123"
}
```

**Réponse 200 :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Erreurs :**
- `401` : email ou mot de passe incorrect

---

### `GET /auth/me` ⬜ 🔒

Retourne le profil de l'utilisateur connecté.

**Réponse 200 :**
```json
{
  "id": "550e8400-...",
  "email": "user@example.com",
  "full_name": "Alice Dupont",
  "created_at": "2026-10-16T19:00:00Z"
}
```

---

## Endpoints Workflows

### `POST /workflows` ⬜ 🔒

Crée un nouveau workflow.

**Corps de la requête :**
```json
{
  "name": "Mon premier workflow",
  "description": "Workflow de test",
  "graph": {
    "nodes": [
      {
        "id": "node_1",
        "type": "manual_trigger",
        "config": {}
      },
      {
        "id": "node_2",
        "type": "http_request",
        "config": {
          "url": "https://api.example.com/data",
          "method": "GET"
        }
      }
    ],
    "edges": [
      {
        "source": "node_1",
        "target": "node_2"
      }
    ]
  }
}
```

**Réponse 201 :**
```json
{
  "id": "wf_550e...",
  "name": "Mon premier workflow",
  "description": "Workflow de test",
  "is_active": false,
  "graph": { "..." },
  "created_at": "2026-10-16T19:00:00Z",
  "updated_at": "2026-10-16T19:00:00Z",
  "user_id": "550e8400-..."
}
```

**Erreurs :**
- `422` : graphe JSON invalide (nœuds manquants, cycle détecté, type de nœud inconnu)

---

### `GET /workflows` ⬜ 🔒

Liste tous les workflows de l'utilisateur.

**Paramètres de query :**
| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `skip` | int | 0 | Offset de pagination |
| `limit` | int | 20 | Nombre max de résultats (max 100) |
| `is_active` | bool | — | Filtrer par statut actif/inactif |

**Réponse 200 :**
```json
{
  "items": [ { "..." } ],
  "total": 42,
  "skip": 0,
  "limit": 20
}
```

---

### `GET /workflows/{workflow_id}` ⬜ 🔒

Récupère un workflow par son ID.

**Réponse 200 :** Objet workflow complet (même structure que la création).

**Erreurs :**
- `404` : workflow introuvable
- `403` : appartient à un autre utilisateur

---

### `PUT /workflows/{workflow_id}` ⬜ 🔒

Met à jour un workflow existant.

**Corps de la requête :** Mêmes champs que la création (tous optionnels).

**Réponse 200 :** Objet workflow mis à jour.

**Erreurs :**
- `404` / `403` : idem
- `422` : graphe invalide
- `409` : workflow en cours d'exécution (impossible de modifier)

---

### `DELETE /workflows/{workflow_id}` ⬜ 🔒

Supprime un workflow (et ses exécutions associées).

**Réponse 204 :** No Content.

**Erreurs :**
- `404` / `403`
- `409` : workflow en cours d'exécution

---

### `POST /workflows/{workflow_id}/activate` ⬜ 🔒

Active un workflow (rend ses triggers actifs).

**Réponse 200 :**
```json
{ "id": "wf_...", "is_active": true }
```

---

### `POST /workflows/{workflow_id}/deactivate` ⬜ 🔒

Désactive un workflow (suspend les triggers).

**Réponse 200 :**
```json
{ "id": "wf_...", "is_active": false }
```

---

## Endpoints Executions

### `POST /workflows/{workflow_id}/execute` ⬜ 🔒

Déclenche manuellement l'exécution d'un workflow.

**Corps de la requête (optionnel) :**
```json
{
  "input_data": {
    "key": "value"
  }
}
```

**Réponse 202 :**
```json
{
  "execution_id": "exec_abc123",
  "status": "queued",
  "workflow_id": "wf_...",
  "created_at": "2026-10-16T19:00:00Z"
}
```

Le status `202 Accepted` indique que l'exécution est **enqueued** mais pas encore terminée. Utiliser `GET /executions/{execution_id}` pour surveiller la progression.

**Erreurs :**
- `404` : workflow introuvable
- `403` : accès interdit
- `422` : workflow inactif ou graphe invalide

---

### `GET /executions` ⬜ 🔒

Liste toutes les exécutions de l'utilisateur.

**Paramètres de query :**
| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `workflow_id` | uuid | — | Filtrer par workflow |
| `status` | string | — | `queued`, `running`, `success`, `failed`, `cancelled` |
| `skip` | int | 0 | Offset |
| `limit` | int | 20 | Max résultats |

**Réponse 200 :**
```json
{
  "items": [
    {
      "id": "exec_abc123",
      "workflow_id": "wf_...",
      "status": "success",
      "started_at": "2026-10-16T19:00:01Z",
      "finished_at": "2026-10-16T19:00:03Z",
      "duration_ms": 2100,
      "trigger_type": "manual",
      "error": null
    }
  ],
  "total": 5,
  "skip": 0,
  "limit": 20
}
```

---

### `GET /executions/{execution_id}` ⬜ 🔒

Récupère les détails complets d'une exécution, incluant les logs par nœud.

**Réponse 200 :**
```json
{
  "id": "exec_abc123",
  "workflow_id": "wf_...",
  "status": "success",
  "started_at": "2026-10-16T19:00:01Z",
  "finished_at": "2026-10-16T19:00:03Z",
  "duration_ms": 2100,
  "trigger_type": "manual",
  "input_data": {},
  "error": null,
  "node_executions": [
    {
      "node_id": "node_1",
      "node_type": "manual_trigger",
      "status": "success",
      "started_at": "2026-10-16T19:00:01Z",
      "finished_at": "2026-10-16T19:00:01Z",
      "duration_ms": 5,
      "output": { "triggered_at": "2026-10-16T19:00:01Z" },
      "error": null
    },
    {
      "node_id": "node_2",
      "node_type": "http_request",
      "status": "success",
      "started_at": "2026-10-16T19:00:01Z",
      "finished_at": "2026-10-16T19:00:03Z",
      "duration_ms": 2090,
      "output": { "status_code": 200, "body": { "..." } },
      "error": null
    }
  ]
}
```

---

### `POST /executions/{execution_id}/cancel` ⬜ 🔒

Annule une exécution en cours.

**Réponse 200 :**
```json
{ "id": "exec_abc123", "status": "cancelled" }
```

**Erreurs :**
- `409` : exécution déjà terminée (success, failed) ou pas encore démarrée

---

## Endpoints Triggers

### `POST /webhooks/{webhook_token}` ⬜ (public)

Endpoint public pour déclencher un workflow via webhook. Le `webhook_token` est un token unique associé au workflow lors de sa configuration.

**Corps de la requête :** Payload libre (transmis comme `input_data` au workflow).

**Réponse 202 :**
```json
{ "execution_id": "exec_abc123", "status": "queued" }
```

**Erreurs :**
- `404` : token inconnu ou workflow inactif
- `429` : trop de requêtes (rate limiting prévu)

---

### `GET /workflows/{workflow_id}/webhook-url` ⬜ 🔒

Retourne l'URL de webhook associée au workflow.

**Réponse 200 :**
```json
{
  "webhook_url": "https://api.flowforge.ai/webhooks/abc123def456",
  "token": "abc123def456"
}
```

---

### `POST /workflows/{workflow_id}/schedule` ⬜ 🔒

Configure ou met à jour une planification cron.

**Corps de la requête :**
```json
{
  "cron_expression": "0 9 * * MON-FRI",
  "timezone": "Europe/Paris"
}
```

**Réponse 200 :**
```json
{
  "id": "sched_...",
  "workflow_id": "wf_...",
  "cron_expression": "0 9 * * MON-FRI",
  "timezone": "Europe/Paris",
  "next_run_at": "2026-10-17T09:00:00+02:00",
  "is_active": true
}
```

**Erreurs :**
- `422` : expression cron invalide, timezone inconnue

---

### `DELETE /workflows/{workflow_id}/schedule` ⬜ 🔒

Supprime la planification d'un workflow.

**Réponse 204** : No Content.

---

## Endpoints Credentials

### `POST /credentials` ⬜ 🔒

Enregistre un credential externe (chiffré avant persistance).

**Corps de la requête :**
```json
{
  "name": "Mon token API",
  "type": "api_key",
  "data": {
    "api_key": "sk-..."
  }
}
```

Types supportés : `api_key`, `oauth2_google`, `telegram_bot`, `http_header`.

**Réponse 201 :**
```json
{
  "id": "cred_...",
  "name": "Mon token API",
  "type": "api_key",
  "created_at": "2026-10-16T19:00:00Z"
}
```

> ⚠️ Le champ `data` (contenant les secrets) **n'est jamais retourné** dans les réponses.

---

### `GET /credentials` ⬜ 🔒

Liste les credentials de l'utilisateur (sans les valeurs secrètes).

**Réponse 200 :**
```json
{
  "items": [
    { "id": "cred_...", "name": "Mon token API", "type": "api_key", "created_at": "..." }
  ]
}
```

---

### `DELETE /credentials/{credential_id}` ⬜ 🔒

Supprime un credential.

**Réponse 204** : No Content.

---

## Endpoints Health

### `GET /health` ⬜ (public)

Vérifie l'état du service.

**Réponse 200 :**
```json
{
  "status": "ok",
  "db": "connected",
  "redis": "connected",
  "version": "0.1.0"
}
```

**Réponse 503 :** si DB ou Redis est inaccessible.

---

> 🔒 = endpoint protégé (JWT requis)
> ⬜ = non implémenté
>
> Ce contrat API sera figé et versionné à partir de la première release stable.
