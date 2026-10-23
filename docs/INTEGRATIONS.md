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

## Webhook Trigger

Un n?ud `webhook_trigger` dans le graphe provisionne un token UUID v4 opaque et stable lors de la cr?ation du workflow. Le token n'est pas plac? dans le graphe.

- `GET /workflows/{workflow_id}/webhook-url` (authentifi?, propri?taire uniquement) retourne `webhook_path`, relatif ? la base `/api/v1` configur?e.
- `POST /webhooks/{token}` est public et transmet le payload JSON comme `input_data` ? une ex?cution du workflow.
- Le workflow doit ?tre actif. L'API retourne `409` lorsqu'il est inactif.
- Le token est une capacit? secr?te : conserver l'URL priv?e.
- Aucune configuration de signature HMAC n'est actuellement expos?e dans le workflow; ne pas documenter l'option comme disponible.

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

## HTTP Request

Effectue une requete HTTP sortante. La protection SSRF bloque les adresses privees, loopback, link-local, reservees et les schemas autres que HTTP(S). Les requetes avec credential ne suivent pas les redirections afin de ne pas transmettre le credential a un autre hote.

### Configuration sans authentification

```json
{
  "type": "http_request",
  "config": {
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": { "Accept": "application/json" },
    "timeout": 30
  }
}
```

### Credential API Key

Creer un credential `api_key` dont les donnees sont `{"api_key":"<secret>"}`. Ces donnees sont chiffrees a la persistance et ne sont jamais renvoyees par l'API. Le graphe conserve uniquement la reference et les parametres non secrets du header :

```json
{
  "credential_id": "<credential UUID>",
  "credential_type": "api_key",
  "api_key_header": "Authorization",
  "api_key_prefix": "Bearer "
}
```

Le header par defaut est `Authorization: Bearer <api_key>`. `api_key_header` et `api_key_prefix` peuvent etre adaptes au service cible.

### Credential HTTP Header

Creer un credential `http_header` dont les donnees sont une carte de noms de headers vers leurs valeurs secretes, par exemple `{"X-API-Key":"<secret>"}`. Le graphe contient seulement `credential_id` et `credential_type: "http_header"`. Les headers du credential remplacent ceux de meme nom saisis dans la configuration du noeud.

Les secrets doivent etre ajoutes dans Credentials, jamais dans le graphe. Le worker verifie que le credential appartient au proprietaire du workflow et que son type correspond a la reference.

### Sortie et protection des secrets

La sortie contient `status_code`, les headers non sensibles, `body` et `ok`. Les headers d'authentification, cookies, tokens et cles sont exclus. Les champs de reponse portant des noms sensibles et toute valeur exacte du credential sont remplaces par `[REDACTED]` avant persistance dans l'historique.

Methodes supportees : GET, POST, PUT, PATCH, DELETE, HEAD et OPTIONS. Le timeout est borne a 30 secondes et la reponse a 10 MB.

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

### Flux OAuth 2.0

La SPA appelle `GET /integrations/google/auth-url` avec le Bearer de session. Le backend cree un nonce persistant, signe `state`, puis retourne l'URL Google. Le frontend l'ouvre dans une popup afin de conserver sa session en memoire. Le callback consomme le nonce une seule fois, echange le code, chiffre access/refresh tokens, enregistre un credential `oauth2_google`, puis renvoie uniquement un statut popup via `postMessage` vers l'origine configuree dans `FRONTEND_URL`.

L'ancien `GET /integrations/google/auth` reste disponible comme redirection navigateur. La SPA utilise `auth-url` car la navigation directe ne peut pas joindre le Bearer en memoire.

Variables requises : `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` et `FRONTEND_URL`. Le callback `GOOGLE_REDIRECT_URI` doit correspondre a l'URL autorisee cote Google. Les scopes demandes sont `gmail.readonly` et `gmail.send`; `access_type=offline` et `prompt=consent` sont utilises pour obtenir un refresh token.

Le compte Google et l'usage reel de Gmail ne sont valides qu'apres un consentement avec des identifiants OAuth configures.

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

## ML Prediction

Le noeud appelle POST {FLOWFORGE_ML_URL}/predict. Par defaut,
FLOWFORGE_ML_URL=http://localhost:8001 quand les deux services tournent sur la
meme machine. Le timeout est de 15 secondes et peut etre regle par
timeout_seconds jusqu'a 60 secondes.

La configuration exige model_id et input. Le modele disponible est
breast_cancer_logistic_regression et attend exactement ses 30 caracteristiques
numeriques, listees par GET /models. La sortie contient prediction, confidence,
raw_output (probabilites par label), model_id et duration_ms.

Les erreurs HTTP, le JSON invalide, les entrees refusees (422), un modele absent
(503), un timeout ou une erreur de connexion font echouer le noeud. Le runner
marque le workflow failed et ses descendants skipped. Aucune prediction de
remplacement n'est produite. Voir docs/ML_PREDICTION.md.

---

> Toutes les intégrations ci-dessus sont au statut ⬜ Non implémenté.
> La phase 1 de développement cible uniquement : Manual Trigger → HTTP Request.
> Gmail, Telegram et ML seront ajoutés après validation du chemin minimal.
