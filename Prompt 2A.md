Agis comme un architecte backend Senior et Technical Writer spécialisé en FastAPI, PostgreSQL, Redis et moteurs d'exécution de workflows.

Analyse le repository `flowforge-backend` et produis une documentation professionnelle basée sur le code réel.

Crée ou mets à jour :

1. `README.md` : présentation, prérequis, installation, configuration, lancement, tests et Docker.
2. `docs/ARCHITECTURE.md` : API, services, repositories, workers, moteur d'exécution et dépendances.
3. `docs/API.md` : endpoints, méthodes HTTP, paramètres, réponses, codes d'erreur et authentification.
4. `docs/WORKFLOW_ENGINE.md` : format JSON, validation des graphes, ordre d'exécution, transmission des données et branchement IF.
5. `docs/INTEGRATIONS.md` : Gmail OAuth, Telegram Bot API, webhooks, Schedule, HTTP Request et ML Prediction.
6. `docs/DATABASE.md` : modèles, relations, migrations et stratégie de persistance.
7. `docs/SECURITY.md` : authentification, isolation des utilisateurs, chiffrement des credentials, protection SSRF et gestion des secrets.
8. `docs/TESTING.md` : tests unitaires, intégration, scénarios d'échec et commandes.
9. `docs/DEPLOYMENT.md` : Docker Compose, PostgreSQL, Redis, workers, variables et logs.
10. `.env.example` : variables requises sans valeurs secrètes.

La documentation doit expliquer le cycle complet : réception du déclenchement, création d'une exécution, traitement des nœuds, transmission des sorties, gestion des erreurs et enregistrement du résultat.

Ne documente aucune fonctionnalité comme terminée sans preuve dans le code ou les tests. Identifie explicitement les fonctionnalités absentes, incomplètes ou non sécurisées.

Ne modifie pas la logique métier sans nécessité. Termine par un rapport de cohérence entre documentation, code et tests.