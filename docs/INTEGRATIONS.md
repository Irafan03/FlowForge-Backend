# Intégrations — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucune intégration n'est implémentée. Source : `Prompt 2B.md`.

---

## Table des matières

- [Manual Trigger](#manual-trigger)
- [Webhook Trigger](#webhook-trigger)
- [Schedule Trigger](#schedule-trigger)
- [HTTP Request](#http-request)
- [Gmail OAuth 2.0](#gmail-oauth-20)
- [Telegram Bot](#telegram-bot)
- [ML Prediction](#ml-prediction)

---

## Manual Trigger ⬜

Déclenche un workflow immédiatement via l'API REST.

**Endpoint :** `POST /workflows/{workflow_id}/execute`

**Config du nœud :**
```json
{ "type": "manual_trigger", "config": {} }
```

**Output :**
```json
{ "triggered_at": "2026-10-16T19:00:00Z", "input_data": {} }
```

Aucune configuration externe requise. Le trigger reçoit optionnellement un `input_data` dans le corps de la requête, transmis au premier nœud du graphe.

---

## Webhook Trigger ⬜

Expose une URL HTTP unique permettant à un système externe de déclencher un workflow.

**URL générée :** `POST /webhooks/{webhook_token}`

**Config du nœud :**
```json
{
  "type": "webhook_trigger",
  "config": {
    "method": "POST",
    "secret_header": "X-Webhook-Secret"
  }
}
```

**Output :**
```json
{
  "method": "POST",
  "headers": { "content-type": "application/json" },
  "body": { "event": "user.created", "user_id": "123" },
  "query_params": {}
}
```

**Sécurité prévue :**
- Le `webhook_token` est un UUID v4 généré à la création du trigger, non prévisible.
- Option : validation d'un secret partagé (`X-Webhook-Secret`) en HMAC-SHA256.
- Le workflow doit être actif (`is_active=true`) pour accepter les requêtes.
- Rate limiting prévu : 100 requêtes/minute par token.

**Variable d'environnement :** aucune spécifique. Le token est stocké en base.

---

## Schedule Trigger ⬜

Déclenche un workflow automatiquement selon une expression cron.

**Config du nœud :**
```json
{
  "type": "schedule_trigger",
  "config": {
    "cron": "0 9 * * MON-FRI",
    "timezone": "Europe/Paris"
  }
}
```

**Output :**
```json
{
  "triggered_at": "2026-10-17T09:00:00+02:00",
  "cron": "0 9 * * MON-FRI",
  "timezone": "Europe/Paris"
}
```

**Implémentation prévue :** APScheduler (3.x) avec job store Redis pour la persistance des planifications entre redémarrages.

**Expressions cron supportées :** Standard POSIX 5 champs + extension APScheduler.

| Exemple | Signification |
|---|---|
| `0 9 * * MON-FRI` | Tous les jours ouvrés à 9h |
| `*/15 * * * *` | Toutes les 15 minutes |
| `0 0 1 * *` | Le 1er de chaque mois à minuit |

**Idempotence :** Si un worker manque une exécution planifiée (downtime), le scheduler ne rattrape pas les exécutions manquées par défaut (`misfire_grace_time` configurable).

---

## HTTP Request ⬜

Effectue une requête HTTP sortante vers n'importe quelle URL externe.

**Config du nœud :**
```json
{
  "type": "http_request",
  "config": {
    "url": "https://api.example.com/data",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer {{credentials.api_key}}"
    },
    "body": {
      "user_id": "{{trigger.input_data.user_id}}"
    },
    "timeout_seconds": 30
  }
}
```

**Méthodes supportées :** GET, POST, PUT, PATCH, DELETE.

**Output :**
```json
{
  "status_code": 200,
  "headers": { "content-type": "application/json" },
  "body": { "result": "ok" },
  "duration_ms": 312
}
```

### Protection SSRF ⬜

La protection SSRF (Server-Side Request Forgery) est **obligatoire** et doit être implémentée avant tout déploiement.

**Règles de blocage prévues :**

| Catégorie | Exemples bloqués |
|---|---|
| Plages IP privées RFC 1918 | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` |
| Loopback | `127.0.0.1`, `::1`, `localhost` |
| Link-local | `169.254.0.0/16` (AWS metadata) |
| Métadonnées cloud | `169.254.169.254` (AWS IMDSv1), `metadata.google.internal` |
| Schémas non-HTTP | `file://`, `ftp://`, `gopher://` |

**Algorithme prévu :**
1. Parser l'URL → extraire le hostname
2. Résoudre le hostname en IP (DNS lookup)
3. Vérifier l'IP contre la liste de blocage
4. Si bloqué → `NodeExecutionError("SSRF protection: blocked IP range")`
5. Suivre les redirections → revérifier chaque IP intermédiaire

> ⚠️ **Non implémenté** — Sans cette protection, un attaquant peut atteindre des services internes. Bloquer impérativement avant mise en production.

**Bibliothèque recommandée :** `httpx` avec hook de validation pré-requête.

---

## Gmail OAuth 2.0 ⬜

### Gmail Trigger

Surveille une boîte Gmail et déclenche le workflow à chaque nouvel email correspondant au filtre.

**Config du nœud :**
```json
{
  "type": "gmail_trigger",
  "config": {
    "credential_id": "cred_google_xyz",
    "filter": "from:boss@company.com subject:urgent",
    "polling_interval_seconds": 60
  }
}
```

**Output :**
```json
{
  "message_id": "18abc...",
  "from": "boss@company.com",
  "subject": "Urgent: report needed",
  "body_text": "...",
  "received_at": "2026-10-16T18:55:00Z",
  "labels": ["INBOX", "UNREAD"]
}
```

### Gmail Send

**Config du nœud :**
```json
{
  "type": "gmail_send",
  "config": {
    "credential_id": "cred_google_xyz",
    "to": "recipient@example.com",
    "subject": "Rapport automatique",
    "body_html": "<p>Bonjour, voici le rapport : {{ml_node.prediction}}</p>",
    "cc": "",
    "attachments": []
  }
}
```

**Output :**
```json
{ "message_id": "18abc...", "sent_at": "2026-10-16T19:00:01Z" }
```

### Flux OAuth 2.0 prévu

```
1. Utilisateur → GET /integrations/google/auth
   → Redirect vers Google OAuth consent screen

2. Google → GET /integrations/google/callback?code=...
   → Échange code contre access_token + refresh_token
   → Chiffrement Fernet des tokens
   → Stockage en Credential (type=oauth2_google)

3. Lors de l'exécution du nœud Gmail :
   → Déchiffrement du credential
   → Si access_token expiré → refresh automatique
   → Appel Gmail API v1
```

**Variables d'environnement requises :**
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI` (ex. `https://api.flowforge.ai/integrations/google/callback`)

**Scopes OAuth requis :**
- `https://www.googleapis.com/auth/gmail.readonly` (trigger)
- `https://www.googleapis.com/auth/gmail.send` (send)

**Sécurité :**
- Les tokens OAuth sont chiffrés en base (Fernet). Voir [SECURITY.md](SECURITY.md).
- Le refresh token n'est jamais exposé dans les réponses API.
- Révocation possible via `DELETE /credentials/{id}`.

---

## Telegram Bot ⬜

### Telegram Trigger

Reçoit des messages envoyés au bot Telegram configuré.

**Config du nœud :**
```json
{
  "type": "telegram_trigger",
  "config": {
    "credential_id": "cred_telegram_xyz",
    "allowed_chat_ids": ["-100123456789"]
  }
}
```

**Mécanisme prévu :** Webhook Telegram (bot.setWebhook) ou long-polling selon la configuration.

**Output :**
```json
{
  "message_id": 42,
  "chat_id": "-100123456789",
  "from_user": { "id": 999, "username": "alice" },
  "text": "/start",
  "received_at": "2026-10-16T19:00:00Z"
}
```

### Telegram Send

**Config du nœud :**
```json
{
  "type": "telegram_send",
  "config": {
    "credential_id": "cred_telegram_xyz",
    "chat_id": "-100123456789",
    "text": "Alerte : {{http_node.body.message}}",
    "parse_mode": "Markdown"
  }
}
```

**Output :**
```json
{ "message_id": 43, "sent_at": "2026-10-16T19:00:02Z" }
```

**Variable d'environnement requise :** `TELEGRAM_BOT_TOKEN`

**Sécurité :**
- Le token du bot est stocké chiffré dans la table `credentials`.
- Le `allowed_chat_ids` limite les chats autorisés à déclencher le workflow.
- Les messages Telegram ne doivent pas être loggés intégralement (peuvent contenir des données personnelles).

---

## ML Prediction ⬜

Appelle le service externe `flowforge-ml` pour effectuer une prédiction.

**Config du nœud :**
```json
{
  "type": "ml_prediction",
  "config": {
    "model_id": "sentiment_analysis_v1",
    "input": {
      "text": "{{gmail_trigger.body_text}}"
    },
    "timeout_seconds": 15
  }
}
```

**Output :**
```json
{
  "model_id": "sentiment_analysis_v1",
  "prediction": "positive",
  "confidence": 0.94,
  "raw_output": { "positive": 0.94, "negative": 0.04, "neutral": 0.02 },
  "duration_ms": 340
}
```

**Variable d'environnement requise :** `FLOWFORGE_ML_URL`

**Contrat API flowforge-ml (prévu) :**
```
POST {FLOWFORGE_ML_URL}/predict
{
  "model_id": "...",
  "input": { ... }
}
→ 200 { "prediction": ..., "confidence": ..., "raw_output": { ... } }
```

**Sécurité :**
- Communication interne uniquement (pas d'exposition publique de `flowforge-ml`).
- Timeout strict (15s par défaut) pour éviter les blocages du worker.
- Pas de validation du contenu des prédictions (responsabilité de flowforge-ml).

---

> Toutes les intégrations ci-dessus sont au statut ⬜ Non implémenté.
> La phase 1 de développement cible uniquement : Manual Trigger → HTTP Request.
> Gmail, Telegram et ML seront ajoutés après validation du chemin minimal.
