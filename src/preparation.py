"""Préparer les positions à la maille fonds, ISIN, conservateur."""

from decimal import Decimal, InvalidOperation, localcontext
import re

import pandas as pd

from src.lecture import controle


COLONNES_POSITIONS = ["fonds", "isin", "conservateur", "quantite", "sources"]


def somme_exacte(quantites):
    valeurs = list(quantites)
    if not valeurs:
        return Decimal(0)
    # La précision couvre tous les chiffres, les décimales et les retenues de la somme.
    precision = max(v.adjusted() for v in valeurs) - min(v.as_tuple().exponent for v in valeurs)
    with localcontext() as contexte:
        contexte.prec = max(28, precision + len(str(len(valeurs))) + 3)
        return sum(valeurs, Decimal(0))


def quantite_exacte(valeur):
    texte = str(valeur).strip().replace("\u00a0", " ").replace("\u202f", " ")
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?: \d{3})+)(?:[.,]\d+)?", texte):
        raise ValueError(f"Quantité invalide : {texte!r}")
    try:
        return Decimal(texte.replace(" ", "").replace(",", "."))
    except InvalidOperation as erreur:
        raise ValueError("Quantité décimale invalide") from erreur


def normaliser_conservateur(libelle):
    texte = str(libelle).upper()
    codes = {code for mot, code in [("CACEIS", "A"), ("EUROCLEAR", "B"), ("BNP", "C"), ("BP2S", "C")]
             if mot in texte}
    if len(codes) != 1:
        raise ValueError(f"Conservateur inconnu ou ambigu : {libelle!r}")
    return codes.pop()


def preparer(table, parametrage, source):
    positions, controles = [], []
    feuille = "TRANSCO_SOUS_COMPTES" if source == "interne" else f"TRANSCO_DEPOSITAIRE_{source}"
    mappings = parametrage[feuille]
    for ligne in table.to_dict("records"):
        reference = " | ".join(ligne["sources"])
        compte = str(ligne["sous_compte"] if source == "interne" else ligne["compte"]).strip()
        if source == "interne" and compte in ("", "P3G"):
            motif = "Sous-compte absent : saisie incomplète" if not compte else "P3G : compte technique de passage"
            controles.append(controle(source, reference, "exclusion", False, motif, bloquant=False))
            continue
        if source == "C" and ligne["action"] == "S":
            controles.append(controle(source, reference, "exclusion", False, "ACTION=S : annulation", bloquant=False))
            continue
        try:
            if source != "interne" and ligne["action"] != "C":
                raise ValueError(f"ACTION inconnue : {ligne['action']!r}")
            if compte not in mappings:
                raise ValueError(f"Compte non reconnu : {compte!r}")
            isin = str(ligne["isin"]).strip().upper()
            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin):
                raise ValueError(f"Format ISIN invalide : {isin!r}")
            quantite = quantite_exacte(ligne["quantite"])
            conservateur = normaliser_conservateur(ligne["depositaire"]) if source == "interne" else source
        except ValueError as erreur:
            controles.append(controle(source, reference, "ligne_exclue", False, str(erreur)))
            continue
        positions.append({"fonds": mappings[compte]["entite"], "isin": isin, "conservateur": conservateur,
                          "quantite": quantite, "sources": ligne["sources"] + mappings[compte]["sources"]})

    if not positions:
        return pd.DataFrame(columns=COLONNES_POSITIONS), controles
    table = pd.DataFrame(positions).groupby(["fonds", "isin", "conservateur"], as_index=False).agg(
        quantite=("quantite", somme_exacte), sources=("sources", lambda listes: list(dict.fromkeys(s for l in listes for s in l))))
    return table[COLONNES_POSITIONS], controles
