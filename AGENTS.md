# AGENTS.md — Cas pratique Saify « Orsay Gestion »

À lire en entier avant toute action. L'énoncé complet est dans `ENONCE.html` : en cas de doute, c'est lui qui fait foi.

## Contexte
Nous sommes consultants Saify. Le client, Orsay Gestion (société de gestion AMF, 3 FCP, 3 conservateurs A/B/C),
a deux besoins :
1. **Rapprochement quotidien des positions titres** : inventaire PMS vs relevés des 3 conservateurs. Le client veut
   voir immédiatement les suspens (fonds, conservateur, action à faire) et envoyer un point de situation à son
   responsable sans rien retaper.
2. **Répondre aux gérants et au RCCI** en langage naturel à partir de `orsay.db`, avec la source de chaque chiffre,
   aucun chiffre inventé, et aucune modification possible de l'inventaire.

Durée fixe : 1 h de construction. Les deux besoins ne tiennent pas en une heure : on priorise, et la fiabilité
compte plus que l'étendue. Nous sommes évalués sur la méthode, l'usage de l'assistant et la maîtrise du code produit.

## Principes non négociables
- **Les chiffres sont calculés par du code déterministe (Python/pandas/SQL), jamais par un LLM.** Le LLM peut
  traduire une question en requête, ou rédiger un texte, mais il ne calcule ni n'invente aucun montant.
- **Aucun seuil de tolérance** : un écart d'une seule unité est un suspens.
- **`orsay.db` est en lecture seule** : connexion SQLite `mode=ro`, uniquement des `SELECT`, jamais d'écriture.
- **Traçabilité** : chaque chiffre affiché doit pouvoir être relié à sa source (fichier et ligne, ou requête SQL).
- **Secrets** : la clé est dans `.env` (`ANTHROPIC_API_KEY`). Ne jamais la recopier dans le code, l'afficher ni la
  logger. Ne jamais commiter `.env`.
- **Ambiguïté** : choisir une interprétation, l'écrire dans le README (section « Interprétations »), continuer.

## Manière de travailler
- **Petites étapes.** Une étape = un changement ciblé, lancé et vérifié avant de passer à la suivante.
- **Ne rien coder sans consigne explicite.** Quand on demande un plan ou une analyse, ne modifier aucun fichier.
- **Regarder les données avant de coder** : colonnes, formats, valeurs manquantes, anomalies.
- **Code simple et lisible**, pas d'abstraction inutile, noms explicites, commentaires seulement là où c'est utile.
  Le code sera relu et expliqué ligne par ligne devant le client.
- **Logique directe dans chaque script (« pure logic »)** : écrire uniquement le code nécessaire au besoin traité.
  Pas de couches, classes, fonctions intermédiaires, dépendances ou fonctionnalités sans utilité concrète.
  Privilégier des fonctions courtes et explicites ; chaque ajout doit servir le traitement, une règle métier,
  un contrôle nécessaire ou la traçabilité. Aucun remplissage ni complexité anticipant des besoins futurs.
- **Tests pytest** sur les règles de gestion à risque (voir plus bas).
- **Commits réguliers (au moins toutes les 15 min)**, petits, avec des messages clairs. Vérifier `git status`
  avant chaque commit.
- **À la fin de chaque étape, faire un compte rendu court** : ce qui a changé, comment c'est vérifié (commande
  lancée + résultat réel), ce qui reste fragile. Ne jamais affirmer qu'une chose marche sans l'avoir exécutée.
- Dire clairement ce qui a été **vérifié en exécutant** et ce qui est **supposé**.

## Stack
- Python 3.12, dépendances gérées avec **uv** (`uv add`, `uv run`).
- **pandas** + **openpyxl** (CSV/Excel), **xml.etree** (XML), **sqlite3** (base), **pydantic** si utile pour valider.
- **Streamlit** pour l'interface utilisateur.
- **pytest** pour les tests.
- **anthropic** (SDK) uniquement pour le besoin 2, si on le traite.
- La solution doit se lancer sur le poste de l'évaluateur avec des instructions simples (`uv sync`, `uv run ...`).

## Données (`donnees/`, arrêté du 25/09/2026, non nettoyées)
| Fichier | Rôle |
|---|---|
| `positions_internes.csv` | Inventaire PMS par sous-compte et valeur. **Source interne du rapprochement.** Séparateur `;` |
| `depositaire_A_20260925.xlsx` | Relevé conservateur A |
| `depositaire_B_20260925.txt` | Relevé conservateur B, largeur fixe (voir spec) |
| `depositaire_C_20260925.xml` | Relevé conservateur C, XML (voir spec) |
| `parametrage.xlsx` | Transcodification comptes → fonds, typologie des suspens et action attendue par type |
| `orsay.db` | Base de gestion SQLite (fonds, titres, cours, positions, mouvements). **Information seulement, pas source du rapprochement** |

### Spécification conservateur B (largeur fixe, positions 1-indexées)
- En-tête : col 1 = `H`, col 2-9 = date d'arrêté `AAAAMMJJ`, puis libellé libre.
- Détail : col 1 = `D`, col 2-4 = code desk du client, col 5-16 = ISIN, col 17-31 = quantité sur 15 chiffres avec
  **2 décimales implicites**.
- Contrôle : col 1 = `T`, col 2-7 = nombre de lignes de détail sur 6 chiffres → **à vérifier**.

### Spécification conservateur C (XML)
- Espace de noms `urn:orsay:depositaire-c:positions:2026`. Chaque `Item` est une suite de `Dim` identifiées par `prop`.
- `Entete/DateArrete` au format `JJMMAAAA` ; `Entete/NbItems` = nombre total d'Item, annulations comprises → **à vérifier**.
- `ACTION` : `C` = position, `S` = annulation. `COMPTE`, `CODE_ISIN`, `LIBELLE_TITRE`.
- `QUANTITE` avec **virgule décimale**. `LOT` : une position peut être livrée en plusieurs lots → **sommer les lots**.

## Règles de gestion du rapprochement (données par le client)
- **Maille** : fonds + code ISIN + conservateur. Quantités en nombre de titres (actions) ou en nominal (obligations).
- **Sous-comptes** : un fonds peut porter la même valeur sur plusieurs sous-comptes PMS ; le conservateur ne voit que
  le compte-titres du fonds → **agréger les sous-comptes au niveau du fonds** via `parametrage.xlsx`.
- **Exclusions** :
  - sous-compte **P3G** = compte technique de passage, exclu de l'inventaire ;
  - ligne **sans sous-compte** = saisie incomplète : exclue du rapprochement mais **signalée** comme anomalie ;
  - mouvement **annulé** par le conservateur (`ACTION=S` chez C) = n'est plus une position.
- **Libellés conservateurs dans le PMS** (variables, à normaliser) : contient « CACEIS » → A ; « EUROCLEAR » → B ;
  « BNP » ou « BP2S » → C.
- **Nettoyage** : ISIN avec espaces et minuscules (`" fr0000014078 "`) → `strip().upper()`. Vérifier les formats
  de nombres (décimales implicites, virgules).
- **Aucune tolérance** : tout écart non nul est un suspens.
- **Typologie des suspens** et **action attendue** : lues dans `parametrage.xlsx`, pas inventées.
- **Une valeur attendue chez un conservateur mais livrée chez un autre = un seul suspens**, pas deux.
- Contrôler la **date d'arrêté** de chaque fichier et les **totaux de contrôle** (B : ligne `T`, C : `NbItems`).
  Toute incohérence doit être visible, pas silencieuse.

### Tests attendus au minimum
P3G exclu ; ligne sans sous-compte signalée ; annulation C exclue ; lots C sommés ; décimales implicites B ;
libellés conservateurs normalisés ; sous-comptes agrégés ; écart d'une unité détecté ; mauvais conservateur = un seul
suspens ; contrôles de totaux B et C.

## Restitution attendue côté client
- Liste des suspens par fonds et par conservateur, avec type et action attendue.
- **Point de situation** exportable (texte/Markdown prêt à envoyer) généré à partir des données calculées.
- Anomalies de qualité de données visibles (lignes ignorées et pourquoi, contrôles de totaux).

## Besoin 2 (si traité) : assistant gérants
- Question en langage naturel → le LLM propose une requête **SQL `SELECT`** → exécution sur `orsay.db` en
  **lecture seule** → réponse construite à partir du résultat réel.
- Toujours afficher **la requête exécutée et le résultat brut** (traçabilité). Refuser toute requête qui n'est pas un
  `SELECT`. Si la réponse n'est pas dans la base, le dire plutôt qu'inventer.
- Valorisation : **obligations cotées en % du nominal au pied de coupon** (valeur = nominal × cours / 100),
  **actions cotées à l'unité** (valeur = quantité × cours).

## Livrables obligatoires (fin de l'heure)
- Une solution qui se lance sur le poste de l'évaluateur à partir des instructions du README.
- Des commits réguliers (au moins toutes les 15 min).
- Un **`README.md` court** : comment lancer ; choix techniques et pourquoi ; interprétations retenues ; ce qui
  marche ; ce qui manque ; **ce qui a été vérifié par l'humain vs ce que l'assistant affirme**.
- L'historique de la session de l'assistant exporté.
