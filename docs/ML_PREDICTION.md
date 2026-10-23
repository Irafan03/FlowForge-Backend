# Noeud ml_prediction

Le noeud envoie POST {FLOWFORGE_ML_URL}/predict. Par defaut,
FLOWFORGE_ML_URL=http://localhost:8001 pour deux services sur la meme machine.
Le timeout est de 15 secondes; timeout_seconds peut le regler jusqu'a 60
secondes (strictement superieur a zero).

## Exemple de workflow

Le modele actuel utilise l'identifiant breast_cancer_logistic_regression et
attend exactement les 30 caracteristiques numeriques exposees par GET
http://localhost:8001/models. Ces valeurs forment une ligne complete du
dataset d'exemple integre a scikit-learn.

~~~json
{
  "type": "ml_prediction",
  "config": {
    "model_id": "breast_cancer_logistic_regression",
    "timeout_seconds": 15,
    "input": {
      "mean radius": 17.99, "mean texture": 10.38,
      "mean perimeter": 122.8, "mean area": 1001.0,
      "mean smoothness": 0.1184, "mean compactness": 0.2776,
      "mean concavity": 0.3001, "mean concave points": 0.1471,
      "mean symmetry": 0.2419, "mean fractal dimension": 0.07871,
      "radius error": 1.095, "texture error": 0.9053,
      "perimeter error": 8.589, "area error": 153.4,
      "smoothness error": 0.006399, "compactness error": 0.04904,
      "concavity error": 0.05373, "concave points error": 0.01587,
      "symmetry error": 0.03003, "fractal dimension error": 0.006193,
      "worst radius": 25.38, "worst texture": 17.33,
      "worst perimeter": 184.6, "worst area": 2019.0,
      "worst smoothness": 0.1622, "worst compactness": 0.6656,
      "worst concavity": 0.7119, "worst concave points": 0.2654,
      "worst symmetry": 0.4601, "worst fractal dimension": 0.1189
    }
  }
}
~~~

## Resultat et erreurs

Les labels sont malignant et benign. La sortie contient prediction,
confidence, raw_output (probabilites par label), model_id et duration_ms.
Elle est stockee dans le contexte du workflow et utilisable par les noeuds
suivants, par exemple avec {{ml.prediction}}.

Un model_id inconnu produit une erreur HTTP 404 remontee comme erreur de noeud.
Les autres erreurs HTTP, le JSON invalide, une reponse incompatible au contrat,
une entree refusee (422), un modele non pret (503), un timeout ou une erreur
de connexion font egalement echouer le noeud. Le runner marque les descendants
skipped. Aucune prediction de remplacement n'est inventee.
