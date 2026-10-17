Agis comme un ingénieur backend Senior spécialisé en Python, FastAPI, PostgreSQL, Redis, systèmes distribués et sécurité applicative.

Développe `flowforge-backend`, le moteur d'automatisation de FlowForge AI.

Stack technique :
- Python et FastAPI.
- PostgreSQL, SQLAlchemy et Alembic.
- Redis et un système de tâches asynchrones adapté.
- Pydantic et Pytest.
- Docker Compose.

Organise le projet en modules distincts pour l'API, la configuration, les modèles, les schémas, les repositories, les services, le moteur, les triggers, les intégrations et les workers.

Fonctionnalités à implémenter :

1. Authentification et isolation des données par utilisateur.
2. CRUD des workflows et stockage de leurs graphes JSON.
3. Validation des nœuds, connexions et paramètres avant exécution.
4. Moteur capable d'exécuter un graphe, de transmettre les sorties entre nœuds et de gérer les branches IF.
5. Statuts d'exécution : queued, running, success, failed et cancelled.
6. Manual Trigger, Webhook Trigger et Schedule Trigger.
7. Gmail Trigger et Gmail Send via OAuth 2.0.
8. Telegram Trigger et Telegram Send via un bot.
9. HTTP Request avec protections SSRF.
10. ML Prediction via l'API du repository `flowforge-ml`.
11. Historique, logs par nœud, erreurs, timeouts et retries contrôlés.
12. Gestion sécurisée des credentials.
13. API pour tester, activer, désactiver et consulter les workflows.

Commence par un moteur minimal avec Manual Trigger → Set/Transform Data → HTTP Request. Valide ce parcours avant d'ajouter Gmail, Telegram et ML.

Exigences :

- Définir les transactions et la persistance des exécutions.
- Prévoir l'idempotence des déclenchements lorsque nécessaire.
- Ne pas exécuter du code utilisateur arbitraire.
- Empêcher les accès inter-utilisateurs non autorisés.
- Ne jamais exposer les secrets dans les réponses ou les logs.
- Ajouter migrations, tests et configuration Docker.
- Respecter les contrats API et JSON communs.

Travaille en phases : architecture, base de données, API CRUD, moteur, triggers, intégrations, sécurité et tests.

À chaque phase, donne les fichiers complets, les commandes d'exécution et les résultats des tests réellement effectués. N'annonce pas une intégration comme terminée si elle n'est pas testée.

Mets à jour la documentation à chaque changement d'API ou de comportement. Attends ma validation avant chaque nouvelle phase importante.