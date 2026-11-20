"""Consultations prédéfinies de la base d'information, sans écriture ni LLM."""

import sqlite3
from datetime import date as Date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic


BASE = Path(__file__).resolve().parents[1] / "donnees" / "orsay.db"
ARRETE = "2026-09-25"

POSITIONS = """SELECT p.rowid AS position_source, p.date_arrete,
    p.portefeuille, p.isin, p.depositaire, p.quantite,
    t.libelle, t.emetteur, t.type_titre, t.mode_cotation,
    t.devise, f.devise AS devise_fonds, c.date_cours, c.cours
FROM positions p
LEFT JOIN titres t ON t.isin = p.isin
LEFT JOIN portefeuilles f ON f.code = p.portefeuille
LEFT JOIN cours c ON c.isin = p.isin AND c.date_cours = p.date_arrete
WHERE p.date_arrete = :date AND p.portefeuille = :fonds
ORDER BY p.rowid"""

REQUETES = {
    "encours": POSITIONS,
    "concentration": POSITIONS,
    "echeances": """SELECT p.rowid AS position_source, p.date_arrete,
        p.portefeuille, p.isin, p.depositaire, p.quantite,
        t.libelle, t.date_echeance, t.mode_cotation, t.devise,
        f.devise AS devise_fonds
    FROM positions p
    LEFT JOIN titres t ON t.isin = p.isin
    LEFT JOIN portefeuilles f ON f.code = p.portefeuille
    WHERE p.date_arrete = :date AND p.portefeuille = :fonds
      AND t.date_echeance > :date AND t.date_echeance <= :fin
    ORDER BY t.date_echeance, p.rowid""",
    "attente": """SELECT m.id AS mouvement_source, m.*,
        t.libelle, t.mode_cotation, t.devise
    FROM mouvements m LEFT JOIN titres t ON t.isin = m.isin
    WHERE m.portefeuille = :fonds AND m.date_operation <= :date
      AND m.statut = 'EN_ATTENTE'
    ORDER BY m.date_denouement, m.id""",
    "origine": """SELECT m.id AS mouvement_source, m.*,
        t.libelle, t.mode_cotation, t.devise
    FROM mouvements m LEFT JOIN titres t ON t.isin = m.isin
    WHERE m.portefeuille = :fonds AND m.date_operation <= :date
      AND m.isin = :isin
    ORDER BY m.date_operation, m.id""",
}


def consulter(type_question: str, fonds: str = "PAT", date: str = ARRETE,
              fin: str = "2027-03-25", isin: str = "") -> dict:
    """Retourne toujours réponse, SELECT, paramètres, lignes brutes et détails."""
    resultat = {"reponse": "", "sql": "", "parametres": {},
                "lignes": [], "details": []}
    if type_question not in REQUETES:
        resultat["reponse"] = "Question non couverte par le catalogue autorisé."
        return resultat
    if fonds not in {"PAT", "OBL", "ACT"}:
        resultat["reponse"] = "Choisir un fonds : PAT, OBL ou ACT."
        return resultat
    try:
        if Date.fromisoformat(date).isoformat() != date or date != ARRETE:
            raise ValueError
        if type_question == "echeances":
            if Date.fromisoformat(fin).isoformat() != fin or fin <= date:
                raise ValueError
    except (ValueError, TypeError):
        resultat["reponse"] = (
            "Seul l'arrêté du 25/09/2026 est disponible ; aucune photographie "
            "historique n'est reconstituée. L'horizon doit être une date ISO "
            "postérieure à cet arrêté."
        )
        return resultat
    parametres = {"fonds": fonds, "date": date}
    if type_question == "echeances":
        parametres["fin"] = fin
    if type_question == "origine":
        if not isinstance(isin, str) or len(isin.strip()) != 12:
            resultat["reponse"] = "Préciser un ISIN de 12 caractères pour rechercher des mouvements candidats."
            return resultat
        parametres["isin"] = isin.strip().upper()
    resultat.update(sql=REQUETES[type_question], parametres=parametres)

    connexion = None
    try:
        connexion = sqlite3.connect(BASE.as_uri() + "?mode=ro", uri=True, timeout=2)
        connexion.row_factory = sqlite3.Row
        connexion.execute("PRAGMA query_only=ON")

        def autoriser(action, table, colonne, base, origine):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if (action == sqlite3.SQLITE_READ and base == "main"
                    and table in {"positions", "titres", "cours", "portefeuilles", "mouvements"}):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        connexion.set_authorizer(autoriser)
        debut = monotonic()
        connexion.set_progress_handler(lambda: int(monotonic() - debut > 2), 1000)
        lignes = connexion.execute(resultat["sql"], parametres).fetchmany(501)
        if len(lignes) > 500:
            resultat["reponse"] = "Plus de 500 lignes : consultation refusée, aucun total partiel calculé."
            return resultat
        resultat["lignes"] = [dict(ligne) for ligne in lignes]
    except sqlite3.Error:
        resultat["reponse"] = "Consultation SQLite impossible ou interrompue ; aucun résultat chiffré produit."
        return resultat
    finally:
        if connexion is not None:
            connexion.close()

    if not resultat["lignes"]:
        resultat["reponse"] = f"Aucune donnée correspondant aux critères pour {fonds}, arrêté du {date}."
        return resultat

    if type_question in {"encours", "concentration"}:
        total = Decimal(0)
        emetteurs = {}
        details = []
        try:
            for ligne in resultat["lignes"]:
                if (ligne["cours"] is None or ligne["libelle"] is None
                        or ligne["devise"] != "EUR" or ligne["devise_fonds"] != "EUR"
                        or ligne["mode_cotation"] not in {"POURCENTAGE", "UNITAIRE"}
                        or ligne["date_cours"] != date
                        or not ligne["emetteur"]):
                    raise ValueError
                quantite = Decimal(str(ligne["quantite"]))
                cours = Decimal(str(ligne["cours"]))
                if not quantite.is_finite() or not cours.is_finite() or cours < 0:
                    raise ValueError
                diviseur = Decimal(100) if ligne["mode_cotation"] == "POURCENTAGE" else Decimal(1)
                valeur = quantite * cours / diviseur
                total += valeur
                emetteur = ligne["emetteur"]
                emetteurs[emetteur] = emetteurs.get(emetteur, Decimal(0)) + valeur
                details.append({**ligne, "valeur_eur": str(valeur),
                                "formule": "quantite * cours / 100" if diviseur == 100 else "quantite * cours"})
        except (ValueError, InvalidOperation, TypeError):
            resultat["reponse"] = "Valorisation refusée : cours, unité, devise ou référentiel incomplet/invalide. Voir les lignes brutes."
            return resultat
        resultat["details"] = details
        if type_question == "encours":
            resultat["reponse"] = (
                f"Encours titres de {fonds} au {date} : {total:.2f} EUR, "
                "aux cours de clôture de cet arrêté, obligations et BTF au pied de coupon. "
                "Il ne s'agit pas d'une valeur liquidative complète. "
                "La quantité des titres cotés en pourcentage est interprétée comme un nominal ; "
                "aucune multiplication supplémentaire par la valeur nominale unitaire."
            )
        elif total <= 0:
            resultat["reponse"] = "Concentration non calculable : encours titres total nul ou négatif."
        else:
            parts = [f"{emetteur} : {valeur:.2f} EUR ({valeur / total * 100:.2f} %)"
                     for emetteur, valeur in sorted(emetteurs.items(), key=lambda paire: paire[1], reverse=True)]
            resultat["reponse"] = (
                f"Concentration par émetteur de {fonds} au {date}, "
                f"sur un encours titres de {total:.2f} EUR :\n" + "\n".join(parts)
                + "\nDénominateur : encours titres au pied de coupon, hors éléments absents de la base. "
                "Aucune conclusion réglementaire. Quantités des titres en pourcentage interprétées en nominal."
            )
    elif type_question == "echeances":
        if any(ligne["devise"] != "EUR" or ligne["devise_fonds"] != "EUR"
               or ligne["mode_cotation"] != "POURCENTAGE" for ligne in resultat["lignes"]):
            resultat["reponse"] = "Échéances non chiffrées : unité ou devise non prise en charge. Voir les lignes brutes."
            return resultat
        resultat["details"] = resultat["lignes"]
        echeances = [f"{ligne['date_echeance']} — {ligne['isin']} : nominal {ligne['quantite']} EUR"
                     for ligne in resultat["lignes"]]
        resultat["reponse"] = (
            f"Échéances de principal des positions de {fonds} au {date}, jusqu'au {fin} inclus :\n"
            + "\n".join(echeances)
            + "\nProjection sur les positions de l'arrêté, sans mouvements futurs ni calendrier des coupons."
        )
    elif type_question == "attente":
        resultat["details"] = [{**ligne, "en_retard_selon_date": ligne["date_denouement"] < date}
                               for ligne in resultat["lignes"]]
        resultat["reponse"] = (
            f"{len(resultat['lignes'])} opération(s) EN_ATTENTE pour {fonds} à l'arrêté du {date}. "
            "Dates de dénouement reprises de la base, sans recalcul du cycle J+2. "
            "Une opération en attente n'est pas nécessairement en retard ; voir le détail."
        )
    else:
        resultat["details"] = resultat["lignes"]
        resultat["reponse"] = (
            f"{len(resultat['lignes'])} mouvement(s) candidat(s) pour {fonds} / {parametres['isin']} "
            f"jusqu'au {date}. Ces opérations ne prouvent pas l'origine d'un suspens : "
            "la base ne contient ni relevé conservateur ni lien causal avec le rapprochement."
        )
    return resultat
