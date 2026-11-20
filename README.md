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

## Traitement et sorties

Lecture et contrôles → nettoyage et exclusions → regroupement par fonds/ISIN/conservateur → comparaison.
Les quantités sont calculées par Python, sans LLM, sans seuil de tolérance, avec références aux lignes sources.

L'interface Streamlit présente trois résultats :

- **Suspens** : un tableau par problème, avec quantités, écart, type, action et sources ; export `suspens.csv`.
- **Point de situation** : texte prêt à transmettre au responsable ; export `point_situation.md`.
- **Contrôles et anomalies** : dates, comptages, exclusions et motifs ; export `controles.csv`.

Les CSV utilisent UTF-8 avec BOM et le séparateur `;`. Les filtres changent l'affichage ; les téléchargements
et la synthèse portent sur l'ensemble du rapprochement.

## Organisation et choix techniques

`app/streamlit_app.py` contient l'interface ; `src/` contient la lecture, la préparation, le rapprochement et les exports.
`tests/` vérifie les règles métier, l'interface et leur intégration sur les fichiers fournis lorsqu'ils sont présents.
Stack configurée : Python 3.12, uv, pandas, openpyxl, Streamlit et pytest, avec les bibliothèques standard pour XML
et les quantités décimales exactes. Fonctions simples et logique métier indépendante de l'interface.
Voir [plan.md](plan.md) pour le détail et [AGENTS.md](AGENTS.md) pour les consignes.

## État et lancement

Le besoin 1 est implémenté et intégré : cinq chargements, contrôles, nettoyage, exclusions, agrégations,
qualification des suspens, références sources et trois téléchargements. Aucune clé API n'est nécessaire.

Depuis la racine du dépôt, installer puis lancer l'interface :

```sh
uv sync
uv run streamlit run app/streamlit_app.py
```

Charger les cinq fichiers dans le panneau latéral, puis cliquer sur **Lancer le rapprochement**.
Sur le jeu fourni au 25/09/2026 : **7 suspens**, **3 exclusions visibles**, aucun contrôle bloquant en échec.
Les 37 lignes PMS donnent 30 positions agrégées après exclusions ; les conservateurs donnent 29 positions.

Commandes de vérification sans navigateur :

```sh
uv run pytest -q
uv run python src/lecture.py
uv run python src/rapprochement.py
```

La dernière commande affiche le point de situation et les contrôles dans le terminal.
Les tests utilisant les fichiers réels sont ignorés si ces fichiers locaux ne sont pas disponibles.

## Interprétations

- Les données d'entrée restent locales, exclues de Git, et ne sont jamais réécrites par le programme.
- Le point de situation est construit par un modèle de texte déterministe, sans appel Anthropic.
- Convention : écart = quantité conservateur − quantité interne.
- Une livraison chez le mauvais conservateur est un seul suspens si l'appariement entre absence et présence est unique.
  Les répartitions ambiguës restent séparées pour examen humain.
- Sous-compte absent : exclusion signalée, non bloquante ; P3G et annulations C sont également exclus et visibles.
- Dates incohérentes : aucune comparaison. Compte inconnu ou quantité illisible : exclusion bloquante,
  résultat incomplet et suspens éventuels provisoires.
- Le format des ISIN est contrôlé ; leur clé n'est ni validée ni corrigée automatiquement.

## Limites

Les lecteurs suivent les formats de l'énoncé (notamment feuille Positions et en-têtes en ligne 3 pour A).
Il n'y a pas d'historique persistant, d'envoi automatique au responsable ou de recherche de cause dans la base.
Le besoin 2 est analysé mais pas implémenté. L'utilisateur doit examiner les anomalies avant de transmettre la synthèse.

## Vérifications

L'assistant a vérifié par commandes Git l'identité configurée et l'état du dépôt ; il a lu l'énoncé et les consignes.
Il a comparé les empreintes Git des six fichiers de données aux originaux : identiques octet pour octet.
`uv sync` a été exécuté avec Python 3.12.13 ; `uv run pytest -q` donne **60 tests réussis** sur main.
Les tests couvrent les règles métier et les interactions Streamlit.
Deux essais d'intégration AppTest utilisent le vrai moteur et les cinq vrais fichiers, sans simulation :
chargement, 7 suspens, filtres, trois téléchargements et contrôle de comptage volontairement erroné.
Les contenus CSV exportés sont relus et les empreintes des entrées sont contrôlées après traitement.
La commande directe de rapprochement a été exécutée avec succès.
Aucune vérification manuelle de l'application par l'humain n'est déclarée à ce stade.
Les secrets `.env` sont exclus de Git et ne doivent jamais être partagés.
