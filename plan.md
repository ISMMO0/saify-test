# Plan — Besoin 1 : rapprochement des positions Orsay Gestion

## Périmètre

Construire une application Streamlit permettant à l'opérateur du middle office de déposer les fichiers du matin,
de repérer les suspens et de télécharger un point de situation pour son responsable.
Ce document décrit le travail prévu : aucune fonctionnalité applicative n'est encore implémentée ou vérifiée.
L'énoncé fait foi ; les consignes de développement sont dans AGENTS.md.

Le besoin 2 (questions en langage naturel sur orsay.db) sera traité plus tard.
Le besoin 1 fonctionne sans appel LLM ni clé API. Le point de situation utilise un modèle de texte déterministe.

## Architecture simple

```text
Fichiers bruts, conservés intacts
    ↓
lecture.py : lire le paramétrage et les quatre sources, contrôler les formats
    ↓
preparation.py : normaliser, exclure les lignes concernées, agréger
    ↓
rapprochement.py : comparer, qualifier les suspens, associer les actions
    ↓
exports.py : préparer les téléchargements et le point de situation
    ↓
app/streamlit_app.py : afficher les suspens, le point de situation et les contrôles
```

Les scripts échangent leurs résultats en mémoire. Aucune modification des fichiers bruts.
Le moteur métier reste indépendant de Streamlit : fonctions explicites, sans couche API ni serveur supplémentaire.

```text
app/
  streamlit_app.py
src/
  __init__.py
  lecture.py
  preparation.py
  rapprochement.py
  exports.py
tests/
donnees/             # fichiers fournis, inchangés, locaux et exclus de Git
AGENTS.md
ENONCE.html
plan.md
README.md
pyproject.toml
uv.lock
```

Les dossiers app/, src/ et tests/ sont initialisés avec des fichiers sans logique applicative.
README.md décrit l'état actuel. pyproject.toml et uv.lock seront créés lors de la configuration des dépendances.

## Entrées

| Fichier | Lecture et rôle |
|---|---|
| positions_internes.csv | CSV séparé par `;`, référence interne ; positions par sous-compte, titre et conservateur |
| depositaire_A_20260925.xlsx | Excel, positions du conservateur A |
| depositaire_B_20260925.txt | Largeur fixe, positions de B ; quantités à deux décimales implicites |
| depositaire_C_20260925.xml | XML avec namespace, positions de C, lots et annulations |
| parametrage.xlsx | Correspondances comptes/fonds, types de suspens et actions attendues |

orsay.db reste disponible pour le futur besoin 2 et n'entre pas dans ce rapprochement.
L'interface prévoit cinq chargements nommés pour éviter de confondre les fichiers.
Les noms réels de colonnes et les feuilles Excel seront examinés avant de coder les lecteurs.

## Stack

| Outil | Utilité |
|---|---|
| Python 3.12 | Logique métier |
| uv | Gestion de l'environnement, des dépendances et des commandes |
| pandas | Tables, CSV/Excel, jointures et regroupements |
| openpyxl | Lecture des fichiers Excel avec pandas |
| xml.etree.ElementTree | Lecture XML ; bibliothèque standard |
| decimal.Decimal | Quantités exactes, sans tolérance ni arrondi flottant ; bibliothèque standard |
| Streamlit | Chargement, affichage, filtres, téléchargements |
| pytest | Tests des règles à risque |

Pas d'Uvicorn nécessaire : Streamlit lance son propre serveur.
Pas de dépendance Anthropic pour cette étape ; le SDK sera ajouté lors du besoin 2.
Commandes cibles, à rendre fonctionnelles lors de l'implémentation :

```sh
uv sync
uv run pytest
uv run streamlit run app/streamlit_app.py
```

## Traitements et règles

1. Inspecter les données et le paramétrage ; documenter les ambiguïtés dans le README.
2. Lire les sources en gardant le fichier et la référence d'origine : ligne CSV/TXT, feuille et ligne Excel,
   index de l'Item XML et lot lorsqu'il existe.
3. Contrôler les dates d'arrêté et les comptages : ligne T de B, NbItems de C avant exclusion des annulations.
4. Normaliser les ISIN (espaces et casse), les quantités et les conservateurs
   (CACEIS → A, EUROCLEAR → B, BNP/BP2S → C).
5. Exclure P3G, les lignes sans sous-compte et les annulations C. Journaliser les exclusions et leurs motifs ;
   une absence de sous-compte est une anomalie de qualité.
6. Utiliser les correspondances du paramétrage pour retrouver les fonds. Signaler les comptes non reconnus.
7. Agréger les sous-comptes internes et les lots conservateurs à la maille fonds + ISIN + conservateur,
   en conservant toutes les références sources.
8. Comparer les deux inventaires, y compris les positions présentes d'un seul côté. Convention :
   écart = quantité conservateur − quantité interne. Tout écart non nul est un suspens.
9. Regrouper en un seul suspens les écarts correspondant à une livraison chez le mauvais conservateur.
   Ne pas attribuer automatiquement une cause si les données ne permettent pas de la déterminer.
10. Lire les types et actions dans le paramétrage ; ne pas inventer de typologie.

Les anomalies structurelles (fichier illisible, schéma indispensable absent, contrôle de comptage ou date incohérent)
empêchent de présenter le résultat comme validé. Les problèmes de ligne sont visibles avec les exclusions.
Le périmètre affecté et le caractère incomplet d'un éventuel résultat doivent être explicites.

## Contrat entre moteur et interface

Point d'entrée prévu : `rapprocher(sources)` dans src/rapprochement.py.
`sources` est un dictionnaire à cinq clés : `interne`, `a`, `b`, `c`, `parametrage` ; chaque valeur est le contenu
du fichier en bytes. Le moteur n'importe pas Streamlit et peut être testé directement.

Le résultat est un dictionnaire simple :

- `positions_internes` et `positions_conservateurs` : tables préparées, colonnes `fonds`, `isin`, `conservateur`,
  `quantite`, `sources`.
- `suspens` : table décrite ci-dessous.
- `controles` : table des validations, anomalies et exclusions décrite ci-dessous.
- `valide` : booléen indiquant si les contrôles bloquants sont satisfaits ; ne signifie pas « aucun suspens ».

Les quantités sont exactes dans le moteur. La conversion en texte décimal intervient à l'affichage et à l'export.
Les références sources restent des listes en mémoire, converties en texte lisible dans les exports.
Les ajustements de ce contrat après inspection des données seront répercutés sur les deux branches.

## Les trois sorties

### 1. Suspens

Table Streamlit filtrable par fonds et conservateur, export `suspens.csv`.
Une ligne par problème, avec les colonnes :

`id_suspens`, `date_arrete`, `fonds`, `isin`, `conservateur_attendu`, `conservateur_constate`,
`quantite_interne`, `quantite_conservateur`, `ecart`, `type`, `action`, `sources_internes`, `sources_conservateurs`.

Pour une livraison chez le mauvais conservateur, la ligne porte les deux conservateurs et les quantités concernées.
L'écart total peut alors être nul : le changement de conservateur constitue le problème et reste visible.

### 2. Point de situation

Texte visible dans Streamlit et téléchargeable en `point_situation.md`, prêt à copier pour le responsable :
date d'arrêté, validité des contrôles, nombre de suspens, répartition par fonds/conservateur,
liste des suspens et actions attendues, réserves liées aux anomalies.
Les chiffres proviennent des tables calculées ; aucun envoi automatique de message.

### 3. Contrôles et anomalies

Table Streamlit et export `controles.csv`, colonnes :
`source`, `reference`, `controle`, `statut`, `motif`, `attendu`, `constate`, `bloquant`.

Elle présente les contrôles réussis et échoués ainsi que les lignes exclues avec leur motif.
Les CSV sont encodés en UTF-8 avec BOM, séparateur `;`, quantités en notation décimale sans perte de précision.
Les téléchargements sont générés en mémoire et ne remplacent jamais les entrées.

## Organisation Git et travail en parallèle

1. Sur main : commit du cadrage (README, plan, consignes, énoncé), puis push.
   Les données restent dans donnees/ en local, exclues de Git avec les secrets et l'environnement local.
   Sur un autre poste, remettre les fichiers fournis dans donnees/ ou les charger dans l'interface lorsqu'elle sera prête.
2. Créer deux branches depuis ce même commit :
   - `codex/backend` : lecture, préparation, rapprochement, exports et tests métier ;
   - `codex/streamlit` : interface utilisant le contrat ci-dessus.
3. Pour travailler simultanément, utiliser deux worktrees distincts : deux branches dans un seul dossier
   ne permettent pas de travailler simultanément sans interférences.
4. Le backend porte la configuration initiale des dépendances ; l'interface évite de modifier les mêmes fichiers.
   Des données fictives temporaires d'interface peuvent servir à sa mise en page, clairement identifiées.
5. Commits ciblés au moins toutes les 15 minutes, après vérification de git status.
6. Intégrer le backend puis l'interface dans main ; vérifier le parcours sur les vrais fichiers avant le push final.

La création des branches prépare le travail ; elle ne lance pas l'implémentation.

## Ordre de réalisation et vérification

1. Inspection réelle des cinq entrées et documentation des interprétations.
2. Lecture et préparation : vérifier les références sources, exclusions et agrégations.
3. Comparaison : tester l'unité d'écart et le mauvais conservateur compté une seule fois.
4. Interface et exports : connecter le moteur et vérifier les trois sorties sur les fichiers fournis.
5. README court et lancement reproductible ; distinguer vérifications exécutées par l'assistant et par l'humain.
6. Export de l'historique de session selon l'outil utilisé ; l'énoncé demande celui de Claude Code via /export.

Tests métier minimaux : P3G, sous-compte manquant, annulation C, lots C, décimales B, noms des conservateurs,
agrégation des sous-comptes, écart d'une unité, mauvais conservateur, comptages B et C.
Aucun résultat chiffré n'est annoncé avant exécution réelle.
