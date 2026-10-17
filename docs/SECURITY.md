# Sécurité — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Aucune mesure de sécurité n'est implémentée. Source : `Prompt 2B.md`.
> Ce document identifie explicitement les risques non couverts.

---

## Table des matières

- [Authentification JWT](#authentification-jwt)
- [Isolation des utilisateurs](#isolation-des-utilisateurs)
- [Chiffrement des credentials](#chiffrement-des-credentials)
- [Protection SSRF](#protection-ssrf)
- [Gestion des secrets](#gestion-des-secrets)
- [Sécurité du moteur d'exécution](#sécurité-du-moteur-dexécution)
- [Risques identifiés non couverts](#risques-identifiés-non-couverts)

---

## Authentification JWT ⬜

### Mécanisme prévu

- Algorithme : **HS256** (HMAC-SHA256), configurable via `ALGORITHM`
- Clé de signature : `SECRET_KEY` (variable d'environnement, jamais codée en dur)
- Durée de vie : `ACCESS_TOKEN_EXPIRE_MINUTES` (défaut : 30 min)
- Payload : `{ "sub": "<user_id>", "exp": <timestamp_unix> }`

### Hash des mots de passe

- Algorithme : **bcrypt** via `passlib`
- Work factor (cost) : 12 (minimum recommandé)
- Le mot de passe en clair n'est **jamais** stocké, loggé ou retourné

### Dépendance FastAPI prévue

```python
# Pseudocode — non implémenté
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    user = user_repo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

### Ce qui n'est PAS implémenté (risques)

| Fonctionnalité manquante | Risque |
|---|---|
| Refresh tokens | Les utilisateurs doivent se reconnecter toutes les 30 min |
| Révocation de tokens | Un token volé reste valide jusqu'à expiration |
| Rate limiting sur `/auth/login` | Attaques brute-force possibles |
| MFA (2FA) | Absence de second facteur |

---

## Isolation des utilisateurs ⬜

### Principe

Chaque table de données possède un `user_id` (FK vers `users`). **Toutes** les requêtes de repository filtrent par `user_id` extrait du JWT.

### Pattern obligatoire dans les repositories

```python
# Pseudocode — non implémenté
def get_workflow_by_id(db: Session, workflow_id: UUID, user_id: UUID) -> Workflow:
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == user_id   # <-- TOUJOURS présent
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Not found")
    return workflow
```

> ⚠️ **Oublier le filtre `user_id`** est la première cause de fuite de données inter-utilisateurs. Ce pattern doit être audité systématiquement lors de chaque code review.

### Vérification dans les tests

Chaque endpoint doit avoir un test qui vérifie qu'un utilisateur B **ne peut pas** accéder aux ressources de l'utilisateur A, même en connaissant l'ID de la ressource.

---

## Chiffrement des credentials ⬜

### Mécanisme prévu : Fernet (AES-128-CBC + HMAC-SHA256)

Les credentials externes (tokens OAuth, clés API, tokens Telegram) sont chiffrés avant insertion en base.

```python
# Pseudocode — non implémenté
from cryptography.fernet import Fernet

def encrypt_credential(data: dict, key: str) -> bytes:
    f = Fernet(key.encode())
    json_bytes = json.dumps(data).encode("utf-8")
    return f.encrypt(json_bytes)

def decrypt_credential(encrypted: bytes, key: str) -> dict:
    f = Fernet(key.encode())
    json_bytes = f.decrypt(encrypted)
    return json.loads(json_bytes.decode("utf-8"))
```

### Règles impératives

| Règle | Justification |
|---|---|
| `ENCRYPTION_KEY` uniquement en variable d'environnement | Jamais en base, jamais en code source |
| Le JSON déchiffré n'est **jamais** retourné dans les réponses API | Prévention de fuite |
| Les logs ne contiennent **jamais** les valeurs de credentials | Prévention de fuite via logs |
| Rotation de clé = re-chiffrement de tous les credentials | À prévoir en procédure opérationnelle |

### Génération d'une clé Fernet

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Tokens OAuth Google

Les `access_token` et `refresh_token` Google sont stockés ensemble dans le JSON chiffré :

```json
{
  "access_token": "ya29...",
  "refresh_token": "1//...",
  "token_expiry": "2026-10-16T20:00:00Z",
  "scopes": ["https://www.googleapis.com/auth/gmail.send"]
}
```

Le refresh est automatique lors de l'exécution d'un nœud Gmail si l'access_token est expiré.

---

## Protection SSRF ⬜

### Contexte

Le nœud `http_request` permet à un utilisateur d'envoyer une requête HTTP vers une URL arbitraire. Sans protection, un attaquant peut cibler des services internes (base de données, Redis, métadonnées cloud AWS/GCP).

### Implémentation prévue

```python
# Pseudocode — non implémenté
import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS IMDS, link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

ALLOWED_SCHEMES = {"http", "https"}

def validate_url_for_ssrf(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFProtectionError(f"Scheme '{parsed.scheme}' is not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("No hostname in URL")

    # Résolution DNS
    try:
        ip_str = socket.gethostbyname(hostname)
    except socket.gaierror:
        raise SSRFProtectionError(f"Cannot resolve hostname: {hostname}")

    ip = ipaddress.ip_address(ip_str)

    for network in BLOCKED_NETWORKS:
        if ip in network:
            raise SSRFProtectionError(f"IP {ip} is in blocked range {network}")
```

### Validation des redirections

Chaque URL de redirection HTTP doit être revalidée contre la liste de blocage.

### Risques résiduels si non implémenté

| Risque | Impact |
|---|---|
| Accès à `169.254.169.254` (AWS IMDS) | Vol de credentials IAM de l'instance |
| Accès à `localhost:5432` | Requêtes directes sur PostgreSQL |
| Accès à `localhost:6379` | Commandes Redis arbitraires |
| DNS rebinding | Bypass de la validation si le DNS change entre la vérification et la requête |

> ⚠️ **CRITIQUE** — Ce mécanisme doit être implémenté et testé **avant tout déploiement**. Sans cette protection, le service est vulnérable aux attaques SSRF.

---

## Gestion des secrets ⬜

### Variables d'environnement critiques

| Variable | Description | Ne jamais faire |
|---|---|---|
| `SECRET_KEY` | Clé JWT | Logger, mettre dans le code, exposer en API |
| `ENCRYPTION_KEY` | Clé Fernet | Stocker en base, logger, exposer en API |
| `GOOGLE_CLIENT_SECRET` | Secret OAuth Google | Exposer côté client, committer en git |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram | Logger, exposer en API |
| `DATABASE_URL` | Contient le mot de passe DB | Logger, exposer en API |

### Règles `.gitignore`

```gitignore
# À ajouter dans .gitignore — non implémenté
.env
*.env
.env.local
.env.production
```

### Logging

- Niveau `DEBUG` : ne jamais activer en production (risque de fuite de secrets dans les logs)
- Les exceptions ne doivent pas propager les valeurs de credentials dans leurs messages
- Les outputs de nœuds sont stockés en base (JSONB) — veiller à ce qu'ils ne contiennent pas de secrets

---

## Sécurité du moteur d'exécution ⬜

### No arbitrary code execution

Le moteur **n'exécute jamais de code Python fourni par l'utilisateur**. Les nœuds sont des types prédéfinis avec des configurations validées par Pydantic. Il n'y a pas de nœud `execute_python` ou équivalent.

### Évaluation des conditions IF

L'évaluateur de conditions du nœud `if_condition` doit utiliser un **parseur de langage restreint**, pas `eval()` ni `exec()`.

```python
# À NE PAS FAIRE — vulnérable à l'injection de code
result = eval(condition_string)  # INTERDIT

# Approche sûre prévue — parser d'expressions
# Utiliser une bibliothèque comme `simpleeval` ou un parseur maison limité
```

### Résolution de templates

Les templates `{{node_id.field}}` sont résolus en accédant uniquement à `context.outputs`. Il n'y a pas d'accès au système de fichiers, aux variables d'environnement, ou à des attributs Python arbitraires.

### Isolation des workers

Chaque exécution de workflow est traitée par un worker qui accède uniquement aux données de l'utilisateur propriétaire. Les workers ne partagent pas d'état mutable entre exécutions concurrentes.

---

## Risques identifiés non couverts

Les risques suivants sont identifiés dans la spécification mais **ne sont pas encore couverts** par une implémentation :

| Risque | Sévérité | Statut |
|---|---|---|
| SSRF via `http_request` | 🔴 Critique | ⬜ Non implémenté |
| Injection dans les conditions IF (`eval`) | 🔴 Critique | ⬜ Non implémenté |
| Fuite de tokens via logs | 🟠 Élevé | ⬜ Non implémenté |
| Absence de rate limiting sur `/auth/login` | 🟠 Élevé | ⬜ Non implémenté |
| Absence de révocation de tokens JWT | 🟡 Moyen | ⬜ Non implémenté |
| Absence de validation HMAC sur webhooks | 🟡 Moyen | ⬜ Non implémenté |
| Données sensibles dans `node_executions.output` | 🟡 Moyen | ⬜ Non implémenté |
| Pas de rotation de la clé Fernet | 🟡 Moyen | ⬜ Non implémenté |
| Absence de headers de sécurité HTTP (CSP, HSTS) | 🟢 Faible | ⬜ Non implémenté |

> ⚠️ Les risques 🔴 Critiques doivent être résolus avant tout déploiement, même en environnement de test avec accès externe.

---

> Ce document est une liste vivante. Chaque fonctionnalité de sécurité doit être marquée ✅ uniquement lorsqu'elle est implémentée **ET** couverte par des tests.
