"""Rapprochement déterministe ; aucune lecture de la base de gestion."""

import csv
from decimal import Decimal
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lecture import (COLONNES_CONTROLES, controle, date_iso, lire_a, lire_b, lire_c,
                         lire_interne, lire_parametrage)
from src.preparation import COLONNES_POSITIONS, preparer, somme_exacte


COLONNES_SUSPENS = ["id_suspens", "date_arrete", "fonds", "isin", "conservateur_attendu",
                    "conservateur_constate", "quantite_interne", "quantite_conservateur", "ecart",
                    "type", "action", "sources_internes", "sources_conservateurs"]


def comparer(internes, conservateurs, types, date_arrete):
    cle = ["fonds", "isin", "conservateur"]
    pms = {tuple(l[c] for c in cle): l for l in internes.to_dict("records")}
    dep = {tuple(l[c] for c in cle): l for l in conservateurs.to_dict("records")}
    suspens = []
    groupes = sorted({(fonds, isin) for fonds, isin, _ in pms.keys() | dep.keys()})
    for fonds, isin in groupes:
        cles = sorted(k for k in pms.keys() | dep.keys() if k[:2] == (fonds, isin))
        manquants = [k for k in cles if k in pms and k not in dep and pms[k]["quantite"] != 0]
        inattendus = [k for k in cles if k in dep and k not in pms and dep[k]["quantite"] != 0]
        couples = []
        if len(manquants) == len(inattendus) == 1:
            # Une seule destination possible : un seul suspens, y compris si la quantité diffère.
            couples.append((manquants[0], inattendus[0], "DEP"))
        traites = {k for attendu, constate, _ in couples for k in (attendu, constate)}
        for k in cles:
            if k in traites:
                continue
            qi = pms[k]["quantite"] if k in pms else Decimal(0)
            qc = dep[k]["quantite"] if k in dep else Decimal(0)
            if qi == qc:
                continue
            code = "ABS_DEP" if k not in dep else "ABS_INT" if k not in pms else "QTE"
            couples.append((k if k in pms else None, k if k in dep else None, code))
        for attendu, constate, code in couples:
            interne = pms.get(attendu, {})
            externe = dep.get(constate, {})
            qi, qc = interne.get("quantite", Decimal(0)), externe.get("quantite", Decimal(0))
            typologie = types[code]
            suspens.append({"id_suspens": f"S{len(suspens) + 1:03d}", "date_arrete": date_arrete,
                            "fonds": fonds, "isin": isin,
                            "conservateur_attendu": attendu[2] if attendu else "",
                            "conservateur_constate": constate[2] if constate else "",
                            "quantite_interne": qi, "quantite_conservateur": qc,
                            "ecart": somme_exacte([qc, qi.copy_negate()]),
                            "type": typologie["libelle"], "action": typologie["action_attendue"],
                            "sources_internes": interne.get("sources", []) + typologie["sources"],
                            "sources_conservateurs": externe.get("sources", [])})
    return pd.DataFrame(suspens, columns=COLONNES_SUSPENS)


def rapprocher(sources):
    """Recevoir cinq fichiers bytes ; retourner tables, contrôles et date commune."""
    resultat = {"positions_internes": pd.DataFrame(columns=COLONNES_POSITIONS),
                "positions_conservateurs": pd.DataFrame(columns=COLONNES_POSITIONS),
                "suspens": pd.DataFrame(columns=COLONNES_SUSPENS),
                "controles": pd.DataFrame(columns=COLONNES_CONTROLES), "valide": False, "date_arrete": ""}
    controles, lectures = [], {}
    lecteurs = {"parametrage": lire_parametrage, "interne": lire_interne, "a": lire_a, "b": lire_b, "c": lire_c}
    for nom, lecteur in lecteurs.items():
        try:
            if nom not in sources or not isinstance(sources[nom], bytes):
                raise ValueError("Fichier absent ou contenu différent de bytes")
            lecture = lecteur(sources[nom])
            if nom in ("a", "b", "c"):
                lectures[nom], validations = lecture
                controles.extend(validations)
            else:
                lectures[nom] = lecture
            controles.append(controle(nom, nom, "lecture", True, "Structure lisible"))
        except (ValueError, KeyError, TypeError, IndexError, UnicodeError, ET.ParseError, BadZipFile, csv.Error) as erreur:
            controles.append(controle(nom, nom, "lecture", False, str(erreur)))
    if len(lectures) != len(lecteurs):
        resultat["controles"] = pd.DataFrame(controles, columns=COLONNES_CONTROLES)
        return resultat

    dates = []
    dates_valides = True
    for nom in ("interne", "a", "b", "c"):
        dates_source = set()
        source_valide = True
        for ligne in lectures[nom].to_dict("records"):
            try:
                date = date_iso(ligne["date_arrete"], "%Y-%m-%d")
                dates.append(date)
                dates_source.add(date)
            except ValueError:
                dates_valides = False
                source_valide = False
                controles.append(controle(nom, " | ".join(ligne["sources"]), "date_arrete", False,
                                          "Date invalide", "AAAA-MM-JJ", ligne["date_arrete"]))
        fichier = lectures[nom].iloc[0]["sources"][0].split(":")[0]
        reference_date = {"interne": f"{fichier}:colonne date_arrete, toutes les lignes",
                          "a": f"{fichier}:ligne 1", "b": f"{fichier}:ligne 1",
                          "c": f"{fichier}:Entete/DateArrete"}[nom]
        controles.append(controle(nom, reference_date,
                                  "date_source", len(dates_source) == 1 and source_valide,
                                  "Date lue dans le fichier, avant exclusions", "Une seule date", ", ".join(sorted(dates_source))))
    communes = set(dates)
    date_arrete = next(iter(communes)) if len(communes) == 1 and dates_valides else ""
    controles.append(controle("toutes", "Dates PMS ; A: titre ligne 1 ; B: ligne H ; C: Entete/DateArrete",
                              "date_commune", bool(date_arrete),
                              "Toutes les positions, exclusions comprises, doivent porter le même arrêté",
                              "Une seule date d'arrêté", ", ".join(sorted(communes))))
    resultat["date_arrete"] = date_arrete
    prepares = {}
    for nom in ("interne", "a", "b", "c"):
        prepares[nom], exclusions = preparer(lectures[nom], lectures["parametrage"],
                                             "interne" if nom == "interne" else nom.upper())
        controles.extend(exclusions)
    resultat["positions_internes"] = prepares["interne"]
    resultat["positions_conservateurs"] = pd.concat([prepares[n] for n in ("a", "b", "c")], ignore_index=True)
    resultat["controles"] = pd.DataFrame(controles, columns=COLONNES_CONTROLES)
    resultat["valide"] = not any(c["bloquant"] for c in controles)
    # Les dates divergentes empêchent toute comparaison entre inventaires de jours différents.
    if date_arrete:
        resultat["suspens"] = comparer(resultat["positions_internes"], resultat["positions_conservateurs"],
                                        lectures["parametrage"]["TYPES_ECARTS"], date_arrete)
    return resultat


if __name__ == "__main__":
    from src.exports import generer_point_situation

    dossier = Path(__file__).resolve().parents[1] / "donnees"
    fichiers = {"interne": "positions_internes.csv", "a": "depositaire_A_20260925.xlsx",
                "b": "depositaire_B_20260925.txt", "c": "depositaire_C_20260925.xml", "parametrage": "parametrage.xlsx"}
    resultat = rapprocher({cle: (dossier / nom).read_bytes() for cle, nom in fichiers.items()})
    print(generer_point_situation(resultat))
    print("\nContrôles et anomalies :")
    print(resultat["controles"].to_string(index=False))
