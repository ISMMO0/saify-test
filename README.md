# Orsay Gestion — Rapprochement des positions

Projet du cas pratique Saify : aider le middle office à comparer son inventaire PMS avec les positions
déclarées par trois conservateurs, puis à identifier les suspens et les actions à mener.
Le périmètre actuel est le premier besoin de l'énoncé. L'assistant de consultation de la base viendra ensuite.

## Entrées

Les fichiers bruts restent intacts dans `donnees/`, en local ; ils ne sont pas publiés dans le dépôt.

| Fichier | Rôle |
|---|---|
| `positions_internes.csv` | Inventaire PMS : référence interne du rapprochement |
| `depositaire_A_20260925.xlsx` | Positions du conservateur A, Excel |
| `depositaire_B_20260925.txt` | Positions du conservateur B, largeur fixe |
| `depositaire_C_20260925.xml` | Positions du conservateur C, XML |
| `parametrage.xlsx` | Correspondances comptes/fonds, types de suspens et actions |

`orsay.db` est réservé au second besoin et ne sert pas de référence pour le rapprochement.
Pour utiliser le projet sur un autre poste, récupérer ces fichiers séparément auprès de leur source.

## Traitement et sorties prévus

Lecture et contrôles → nettoyage et exclusions → regroupement par fonds/ISIN/conservateur → comparaison.
Les quantités sont calculées par Python, sans LLM, sans seuil de tolérance, avec références aux lignes sources.

L'interface Streamlit présentera trois résultats :

- **Suspens** : un tableau par problème, avec quantités, écart, type, action et sources ; export `suspens.csv`.
- **Point de situation** : texte prêt à transmettre au responsable ; export `point_situation.md`.
- **Contrôles et anomalies** : dates, comptages, exclusions et motifs ; export `controles.csv`.

Les CSV prévus utilisent UTF-8 avec BOM et le séparateur `;`.

## Organisation et choix techniques

`app/` accueillera Streamlit ; `src/` contiendra les scripts de lecture, préparation, rapprochement et export ;
`tests/` accueillera les tests métier.
Stack prévue : Python 3.12, uv, pandas, openpyxl, Streamlit et pytest, avec les bibliothèques standard pour XML
et les quantités décimales exactes. Fonctions simples et logique métier indépendante de l'interface.
Voir [plan.md](plan.md) pour le détail et [AGENTS.md](AGENTS.md) pour les consignes.

## État et lancement

Le projet est au stade du cadrage. L'application, les dépendances et les tests restent à implémenter.
Les futures commandes seront `uv sync`, `uv run pytest` et `uv run streamlit run app/streamlit_app.py` ;
elles ne permettent pas encore de lancer une solution fonctionnelle.

## Interprétations

- Les données d'entrée restent locales, exclues de Git, et ne sont jamais réécrites par le programme.
- Le point de situation sera construit par un modèle de texte déterministe, sans appel Anthropic.
- Convention prévue : écart = quantité conservateur − quantité interne.
- Une livraison chez le mauvais conservateur sera présentée comme un seul suspens.

## Vérifications

L'assistant a vérifié par commandes Git l'identité configurée et l'état du dépôt ; il a lu l'énoncé et les consignes.
Aucun traitement métier ni résultat chiffré n'a encore été exécuté ou validé.
Aucune vérification manuelle de l'application par l'humain n'est déclarée à ce stade.
Les secrets `.env` sont exclus de Git et ne doivent jamais être partagés.
