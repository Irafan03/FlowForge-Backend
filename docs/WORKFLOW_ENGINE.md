# Moteur d'exécution des Workflows — FlowForge Backend

> ⚠️ **SPÉCIFICATION** — Le moteur d'exécution n'a pas encore été implémenté.
> Source : `Prompt 2B.md`. Statut global : ⬜ Non implémenté.

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Format JSON du workflow](#format-json-du-workflow)
- [Types de nœuds](#types-de-nœuds)
- [Validation du graphe](#validation-du-graphe)
- [Cycle d'exécution](#cycle-dexécution)
- [Transmission des données entre nœuds](#transmission-des-données-entre-nœuds)
- [Branchement IF](#branchement-if)
- [Statuts d'exécution](#statuts-dexécution)
- [Gestion des erreurs](#gestion-des-erreurs)
- [Timeouts et retries](#timeouts-et-retries)
- [Contraintes de sécurité](#contraintes-de-sécurité)

---

## Vue d'ensemble

Le moteur d'exécution est le cœur de FlowForge. Il reçoit un workflow (graphe JSON), le valide, exécute chaque nœud dans l'ordre topologique, transmet les sorties d'un nœud aux entrées du suivant, et gère les branches conditionnelles (IF).

L'exécution est **toujours asynchrone** : déclenchée par un trigger, enqueued dans Redis, puis traitée par un worker isolé.

```
Trigger → ExecutionService.enqueue() → Redis → Worker → engine.runner.run() → PostgreSQL
```

---

## Format JSON du workflow

Un workflow stocke son graphe dans un champ `graph` de type JSONB en PostgreSQL.

### Structure complète

```json
{
  "nodes": [
    {
      "id": "node_uuid_or_slug",
      "type": "node_type",
      "name": "Nom affiché",
      "config": { },
      "position": { "x": 100, "y": 200 }
    }
  ],
  "edges": [
    {
      "id": "edge_uuid",
      "source": "node_id_source",
      "target": "node_id_target",
      "source_handle": "output",
      "target_handle": "input",
      "condition": null
    }
  ]
}
```

### Champs obligatoires

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `nodes` | array | ✅ | Liste des nœuds |
| `nodes[].id` | string | ✅ | Identifiant unique dans le graphe |
| `nodes[].type` | string | ✅ | Type de nœud (voir liste ci-dessous) |
| `nodes[].config` | object | ✅ | Configuration spécifique au type |
| `edges` | array | ✅ | Liste des connexions |
| `edges[].source` | string | ✅ | ID du nœud source |
| `edges[].target` | string | ✅ | ID du nœud cible |

### Champs optionnels

| Champ | Type | Description |
|---|---|---|
| `nodes[].name` | string | Label affiché dans l'UI |
| `nodes[].position` | object | Position visuelle (ignorée à l'exécution) |
| `edges[].id` | string | Identifiant de l'arête |
| `edges[].source_handle` | string | Port de sortie source (pour nœuds IF : `"true"` / `"false"`) |
| `edges[].target_handle` | string | Port d'entrée cible |
| `edges[].condition` | string | Réservé (null pour arêtes standard) |

---

## Types de nœuds

### Triggers (exactement 1 par workflow)

| Type | Description | Config requise |
|---|---|---|
| `manual_trigger` | Déclenchement via API | `{}` |
| `webhook_trigger` | Réception d'une requête HTTP | `{"method": "POST"}` |
| `schedule_trigger` | Déclenchement cron | `{"cron": "0 9 * * *", "timezone": "Europe/Paris"}` (`timezone` optionnel, défaut `UTC`) |
| `gmail_trigger` | Nouveau mail Gmail | `{"credential_id": "cred_...", "filter": "..."}` |
| `telegram_trigger` | Message Telegram reçu | `{"credential_id": "cred_..."}` |

### Traitement de données

| Type | Description | Config requise |
|---|---|---|
| `set_data` | Définit/transforme des champs | `{"fields": [{"key": "x", "value": "{{node_1.output}}"}]}` |
| `if_condition` | Branchement conditionnel | `{"condition": "{{node_1.status_code}} == 200"}` |

### Actions

| Type | Description | Config requise |
|---|---|---|
| `http_request` | Requête HTTP sortante | `{"url": "...", "method": "GET", "headers": {}, "body": {}}` |
| `gmail_send` | Envoi d'un email Gmail | `{"credential_id": "...", "to": "...", "subject": "...", "body": "..."}` |
| `telegram_send` | Envoi d'un message Telegram | `{"credential_id": "...", "chat_id": "...", "text": "..."}` |
| `ml_prediction` | Prédiction ML via flowforge-ml | `{"model_id": "...", "input": {}}` |

### Exemple complet : workflow Manual → HTTP → IF → Telegram/Log

```json
{
  "nodes": [
    {
      "id": "trigger",
      "type": "manual_trigger",
      "name": "Déclenchement manuel",
      "config": {}
    },
    {
      "id": "call_api",
      "type": "http_request",
      "name": "Appel API externe",
      "config": {
        "url": "https://api.example.com/status",
        "method": "GET",
        "headers": { "Accept": "application/json" }
      }
    },
    {
      "id": "check_status",
      "type": "if_condition",
      "name": "Vérifier statut HTTP",
      "config": {
        "condition": "{{call_api.status_code}} == 200"
      }
    },
    {
      "id": "notify_success",
      "type": "telegram_send",
      "name": "Notification succès",
      "config": {
        "credential_id": "cred_telegram_xyz",
        "chat_id": "-100123456789",
        "text": "✅ API répond correctement"
      }
    },
    {
      "id": "notify_failure",
      "type": "telegram_send",
      "name": "Notification échec",
      "config": {
        "credential_id": "cred_telegram_xyz",
        "chat_id": "-100123456789",
        "text": "❌ API en erreur : {{call_api.status_code}}"
      }
    }
  ],
  "edges": [
    { "source": "trigger", "target": "call_api" },
    { "source": "call_api", "target": "check_status" },
    { "source": "check_status", "target": "notify_success", "source_handle": "true" },
    { "source": "check_status", "target": "notify_failure", "source_handle": "false" }
  ]
}
```

---

## Validation du graphe

La validation est effectuée **avant chaque exécution** (et optionnellement à la sauvegarde).

### Règles de validation (prévues)

| Règle | Erreur si violée |
|---|---|
| Au moins un nœud de type `*_trigger` | `"Workflow must have exactly one trigger node"` |
| Un seul nœud trigger | `"Multiple trigger nodes are not allowed"` |
| Tous les `edges[].source` et `target` référencent des `nodes[].id` existants | `"Edge references unknown node: {id}"` |
| Pas de cycle (DAG strict) | `"Graph contains a cycle"` |
| Chaque `nodes[].config` valide selon le schéma du type | `"Node {id}: missing required field 'url'"` |
| Les arêtes d'un nœud `if_condition` ont `source_handle` = `"true"` ou `"false"` | `"IF node must have 'true' and 'false' branches"` |
| Les `credential_id` référencés existent et appartiennent à l'utilisateur | `"Credential not found: {id}"` |

### Algorithme de détection de cycle (prévu)

Tri topologique via DFS (Depth-First Search). Si un nœud est visité deux fois dans la même branche de DFS, un cycle est détecté.

```python
# Pseudocode — non implémenté
def has_cycle(nodes, edges) -> bool:
    graph = build_adjacency_list(nodes, edges)
    visited = set()
    rec_stack = set()

    def dfs(node_id):
        visited.add(node_id)
        rec_stack.add(node_id)
        for neighbor in graph[node_id]:
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node_id)
        return False

    for node in nodes:
        if node.id not in visited:
            if dfs(node.id):
                return True
    return False
```

---

## Cycle d'exécution

### 1. Création de l'exécution

```python
# Pseudocode — non implémenté
execution = WorkflowExecution(
    id=uuid4(),
    workflow_id=workflow.id,
    user_id=user.id,
    status=ExecutionStatus.QUEUED,
    trigger_type=trigger_type,
    input_data=input_data,
    created_at=now()
)
db.add(execution)
redis.enqueue("execute_workflow", execution_id=str(execution.id))
```

### 2. Traitement par le worker

```python
# Pseudocode — non implémenté
def execute_workflow(execution_id: str):
    execution = execution_repo.get(db, execution_id)
    workflow = workflow_repo.get(db, execution.workflow_id)

    # Mise à jour statut
    execution_repo.update_status(db, execution, ExecutionStatus.RUNNING)

    # Validation du graphe
    validators.validate_graph(workflow.graph)

    # Initialisation du contexte
    context = ExecutionContext(
        execution_id=execution_id,
        workflow_graph=workflow.graph,
        input_data=execution.input_data
    )

    # Exécution
    try:
        runner.run(context, db)
        execution_repo.update_status(db, execution, ExecutionStatus.SUCCESS)
    except Exception as e:
        execution_repo.update_status(db, execution, ExecutionStatus.FAILED, error=str(e))
```

### 3. Tri topologique et exécution nœud par nœud

```python
# Pseudocode — non implémenté
def run(context: ExecutionContext, db: Session):
    ordered_nodes = topological_sort(context.graph.nodes, context.graph.edges)

    for node in ordered_nodes:
        # Vérifier si ce nœud doit être exécuté (branches IF)
        if not context.should_execute(node.id):
            continue

        # Exécuter le nœud
        node_exec = NodeExecution(node_id=node.id, status=RUNNING, ...)
        try:
            output = node_executor.execute(node, context)
            context.set_output(node.id, output)
            node_exec.status = SUCCESS
            node_exec.output = output
        except NodeTimeoutError:
            node_exec.status = FAILED
            node_exec.error = "Timeout"
            raise
        except Exception as e:
            node_exec.status = FAILED
            node_exec.error = str(e)
            raise
        finally:
            db.add(node_exec)
            db.commit()
```

---

## Transmission des données entre nœuds

Les sorties de chaque nœud sont stockées dans l'`ExecutionContext` et accessibles aux nœuds suivants via une syntaxe de template.

### Syntaxe de référence

```
{{node_id.field}}
{{node_id.nested.field}}
{{node_id.array[0].field}}
```

### Exemples

```json
{
  "url": "https://api.example.com/users/{{trigger.input_data.user_id}}",
  "headers": {
    "Authorization": "Bearer {{cred_fetch.token}}"
  }
}
```

### Résolution des templates (prévue)

Avant d'exécuter un nœud, le moteur résout tous les templates dans `config` en remplaçant `{{node_id.field}}` par la valeur correspondante dans `context.outputs[node_id]`.

**Règle** : si un template référence un nœud qui n'a pas encore été exécuté, l'exécution échoue avec `"Unresolved reference: {node_id}"`.

### Structure d'output par type de nœud

| Type | Structure d'output |
|---|---|
| `manual_trigger` | `{ "triggered_at": "...", "input_data": {} }` |
| `webhook_trigger` | `{ "method": "POST", "headers": {}, "body": {}, "query_params": {} }` |
| `schedule_trigger` | `{ "triggered_at": "...", "cron": "..." }` |
| `http_request` | `{ "status_code": 200, "headers": {}, "body": {}, "duration_ms": 123 }` |
| `if_condition` | `{ "result": true, "condition": "..." }` |
| `set_data` | `{ "key1": "value1", "key2": "value2" }` |
| `gmail_send` | `{ "message_id": "...", "sent_at": "..." }` |
| `telegram_send` | `{ "message_id": 12345, "sent_at": "..." }` |
| `ml_prediction` | `{ "prediction": ..., "confidence": 0.95, "model_id": "..." }` |

---

## Branchement IF

Le nœud `if_condition` évalue une condition et dirige le flux d'exécution vers la branche `true` ou `false`.

### Configuration

```json
{
  "type": "if_condition",
  "config": {
    "condition": "{{http_call.status_code}} == 200"
  }
}
```

### Opérateurs supportés (prévus)

| Opérateur | Exemple |
|---|---|
| Égalité | `{{node.field}} == "value"` |
| Inégalité | `{{node.field}} != "error"` |
| Comparaison numérique | `{{node.count}} > 0` |
| Contient | `"error" in {{node.body.message}}` |
| Est vide/null | `{{node.result}} is null` |

### Mécanisme dans le moteur (prévu)

```python
# Pseudocode — non implémenté
def execute_if_node(node, context):
    condition_str = node.config["condition"]
    resolved = context.resolve_template(condition_str)
    result = evaluate_condition(resolved)  # évaluateur sécurisé (pas eval())

    output = {"result": result, "condition": condition_str}
    context.set_branch_result(node.id, "true" if result else "false")
    return output
```

### Propagation de branche

Lorsqu'un nœud IF est exécuté :
1. Le contexte enregistre `branch_result[node.id] = "true"|"false"`
2. Avant chaque nœud suivant, le moteur vérifie si ce nœud est sur une branche désactivée
3. Si `edge.source_handle` ne correspond pas à `branch_result[source_node]`, le nœud est **skipped** (statut `SKIPPED`)

Les nœuds skipped ne sont pas des erreurs. Ils sont enregistrés en base avec `status=SKIPPED`.

---

## Statuts d'exécution

### WorkflowExecution

| Statut | Description |
|---|---|
| `queued` | En attente dans Redis, pas encore pris par un worker |
| `running` | Worker en cours d'exécution |
| `success` | Tous les nœuds requis ont réussi |
| `failed` | Au moins un nœud a échoué (non récupérable) |
| `cancelled` | Annulé par l'utilisateur via `POST /executions/{id}/cancel` |

### NodeExecution

| Statut | Description |
|---|---|
| `pending` | En attente (prédécesseurs pas encore terminés) |
| `running` | En cours d'exécution |
| `success` | Nœud terminé avec succès |
| `failed` | Erreur non récupérée |
| `skipped` | Nœud ignoré (branche IF inactive) |

---

## Gestion des erreurs

### Propagation

Par défaut, si un nœud échoue, **l'exécution entière est marquée `failed`** et les nœuds suivants ne sont pas exécutés.

### Comportement prévu

- Timeout d'un nœud → `NodeTimeoutError` → nœud `failed` → workflow `failed`
- Erreur HTTP dans `http_request` (ex. DNS failure) → nœud `failed` → workflow `failed`
- Erreur de résolution de template → nœud `failed` immédiatement
- Erreur d'authentification credential → nœud `failed` avec message générique (pas de secret dans les logs)

### Ce qui n'est PAS encore prévu

- Branchement `on_error` (nœud alternatif en cas d'échec)
- Retry au niveau du nœud individuel (uniquement au niveau du workflow pour l'instant)

---

## Timeouts et retries

### Timeouts (prévus, non implémentés)

| Niveau | Timeout par défaut | Configurable |
|---|---|---|
| Nœud individuel | 30 secondes | Via `config.timeout_seconds` |
| Workflow entier | 10 minutes | Via `workflow.max_duration_seconds` |

### Retries (prévus, non implémentés)

```json
{
  "type": "http_request",
  "config": {
    "url": "...",
    "retry": {
      "max_attempts": 3,
      "delay_seconds": 2,
      "backoff": "exponential"
    }
  }
}
```

Les retries ne seront implémentés qu'après validation du chemin minimal Manual → HTTP Request.

---

## Cycle de vie du Schedule Trigger

Le nœud `schedule_trigger` stocke sa configuration dans `graph.nodes[].config` avec
`cron` (expression cron à cinq champs, par exemple `0 9 * * 1`) et `timezone` (nom IANA, par exemple
`Europe/Paris`). `timezone` est optionnel et vaut `UTC` en son absence. Le backend
valide les deux champs à la création et à chaque mise à jour du graphe ; une
expression cron ou un fuseau invalide produit une réponse HTTP 422.

Le backend conserve aussi une ligne unique dans `triggers` par workflow. Elle
reprend la configuration d'origine dans `config` et renseigne les colonnes
`cron_expression`, `timezone` et `next_run_at`. Remplacer le type du trigger
réutilise cette ligne et efface les champs propres au Schedule. Supprimer le
trigger Schedule du graphe le remplace par le nouveau type de trigger. La ligne
et le graphe sont écrits dans la même transaction. Activer un workflow active
son trigger et recalcule sa prochaine occurrence à partir de l'heure courante ;
le désactiver suspend le polling sans supprimer le planning.

`next_run_at` est conservé en UTC (`TIMESTAMPTZ`). Le calcul cron utilise l'heure
civile du fuseau IANA, puis convertit l'occurrence en UTC. Lors du retour à
l'heure d'hiver, un créneau local ambigu (par exemple 02:30 à Paris) est exécuté
une seule fois ; au passage à l'heure d'été, un créneau inexistant est résolu par
`croniter` vers la prochaine heure civile représentable. Le worker interroge
chaque minute les triggers arrivés à échéance dont le workflow est actif. Il
verrouille les lignes avec `FOR UPDATE SKIP LOCKED` et envoie d'abord l'exécution
par le service ARQ commun, avec une clé d'idempotence stable basée sur le trigger
et l'occurrence UTC. Il avance ensuite `next_run_at` de façon conditionnelle.
Deux pollers peuvent donc reprendre la même échéance sans créer plusieurs
exécutions ou jobs ARQ. Si l'enqueue échoue, l'exécution `queued` reste persistée,
le planning reste dû et le prochain poll retente le même job idempotent. Si
plusieurs occurrences sont manquées pendant l'arrêt du worker, une seule
exécution est créée au redémarrage et le calendrier repart à la prochaine
occurrence future.

Les tests unitaires du calendrier et du polling sont isolés avec SQLite en
mémoire. Les tests d'intégration du cycle de vie exigent un PostgreSQL dédié
`flowforge_test` via `TEST_DATABASE_URL` (voir `docs/TESTING.md`). Le polling du
worker s'exécute sans Redis dans ces tests par remplacement du service d'enqueue ;
un E2E ARQ/Redis requiert séparément Redis sur `127.0.0.1:6380`.

## Contraintes de sécurité

| Contrainte | Justification |
|---|---|
| **Pas d'exécution de code utilisateur arbitraire** | Les nœuds sont des types prédéfinis avec config Pydantic |
| **Évaluateur de conditions sécurisé** (pas `eval()`) | Prévention d'injection de code dans les conditions IF |
| **Résolution de templates bornée** | Pas d'accès à des variables hors `context.outputs` |
| **Secrets jamais dans les outputs/logs** | Les credentials ne transitent jamais dans les sorties de nœuds |
| **Isolation par user_id** | Un worker ne peut pas accéder aux workflows d'un autre utilisateur |

---

> Ce document sera mis à jour à chaque évolution du moteur. La phase 1 cible uniquement : Manual Trigger → Set/Transform Data → HTTP Request.
