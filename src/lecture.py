"""Lecture des sources sans nettoyage ni modification des fichiers."""

import csv
from io import BytesIO, StringIO
from datetime import datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pandas as pd
from openpyxl import load_workbook


COLONNES_CONTROLES = ["source", "reference", "controle", "statut", "motif", "attendu", "constate", "bloquant"]


def controle(source, reference, nom, ok, motif="", attendu="", constate="", bloquant=True):
    return dict(zip(COLONNES_CONTROLES, [source, reference, nom, "OK" if ok else "ANOMALIE",
                                      motif, str(attendu), str(constate), bool(bloquant and not ok)]))


def date_iso(texte, format_date):
    texte = str(texte).strip()
    date = datetime.strptime(texte, format_date).date()
    if date.strftime(format_date) != texte:
        raise ValueError(f"Date au format incorrect : {texte!r}")
    return date.isoformat()


def lire_parametrage(contenu: bytes) -> dict:
    """Refuser un mapping ambigu plutôt que choisir arbitrairement un fonds."""
    classeur = load_workbook(BytesIO(contenu), read_only=True, data_only=False)
    schemas = {
        "TRANSCO_SOUS_COMPTES": ["sous_compte", "entite"],
        "TRANSCO_DEPOSITAIRE_A": ["compte", "entite"],
        "TRANSCO_DEPOSITAIRE_B": ["code_desk", "entite"],
        "TRANSCO_DEPOSITAIRE_C": ["compte", "entite"],
        "TYPES_ECARTS": ["code", "libelle", "action_attendue"],
    }
    tables = {}
    for nom, colonnes in schemas.items():
        if nom not in classeur.sheetnames:
            raise ValueError(f"parametrage.xlsx : feuille {nom} absente")
        lignes = list(classeur[nom].values)
        if list(lignes[0]) != colonnes:
            raise ValueError(f"parametrage.xlsx/{nom} : en-tête incorrect")
        table = {}
        for numero, valeurs in enumerate(lignes[1:], 2):
            if all(v is None for v in valeurs):
                continue
            if any(not isinstance(v, str) or not v.strip() or v.startswith("=") for v in valeurs):
                raise ValueError(f"parametrage.xlsx/{nom}:ligne {numero} : valeur vide, numérique ou formule")
            ligne = dict(zip(colonnes, (v.strip() for v in valeurs)))
            cle = ligne[colonnes[0]]
            if cle in table:
                raise ValueError(f"parametrage.xlsx/{nom} : clé dupliquée {cle}")
            ligne["sources"] = [f"parametrage.xlsx/{nom}:ligne {numero}"]
            table[cle] = ligne
        if not table:
            raise ValueError(f"parametrage.xlsx/{nom} : table vide")
        tables[nom] = table
    if not {"QTE", "ABS_DEP", "ABS_INT", "DEP"}.issubset(tables["TYPES_ECARTS"]):
        raise ValueError("parametrage.xlsx/TYPES_ECARTS : codes QTE, ABS_DEP, ABS_INT, DEP requis")
    return tables


def lire_a(contenu: bytes):
    classeur = load_workbook(BytesIO(contenu), read_only=True, data_only=False)
    feuille = classeur["Positions"]
    lignes = list(feuille.values)
    match = re.search(r"ARRETE DU (\d{2}/\d{2}/\d{4})", str(lignes[0][0]))
    if not match or list(lignes[2]) != ["Compte", "Code ISIN", "Désignation", "Quantité"]:
        raise ValueError("Conservateur A : titre daté ou en-tête ligne 3 incorrect")
    date = date_iso(match[1], "%d/%m/%Y")
    positions = []
    for numero, valeurs in enumerate(lignes[3:], 4):
        if all(v is None for v in valeurs):
            continue
        if not isinstance(valeurs[0], str):
            raise ValueError(f"Conservateur A:ligne {numero} : compte texte requis (zéros initiaux)")
        positions.append(dict(zip(["compte", "isin", "libelle", "quantite"], valeurs),
                              date_arrete=date, action="C",
                              sources=[f"depositaire_A.xlsx/Positions:ligne {numero}"]))
    if not positions:
        raise ValueError("Conservateur A : aucune position")
    return pd.DataFrame(positions), []


def lire_b(contenu: bytes):
    lignes = contenu.decode("utf-8-sig").splitlines()
    if len(lignes) < 2 or not re.fullmatch(r"H\d{8}.*", lignes[0]) or not re.fullmatch(r"T\d{6}", lignes[-1]):
        raise ValueError("Conservateur B : en-tête H ou total T incorrect")
    date = date_iso(lignes[0][1:9], "%Y%m%d")
    positions = []
    for numero, ligne in enumerate(lignes[1:-1], 2):
        if not re.fullmatch(r"D.{3}.{12}\d{15}", ligne):
            raise ValueError(f"Conservateur B:ligne {numero} : détail de largeur fixe incorrect")
        chiffres = ligne[16:31]
        positions.append({"compte": ligne[1:4], "isin": ligne[4:16],
                          "quantite": chiffres[:-2] + "." + chiffres[-2:], "date_arrete": date,
                          "action": "C", "sources": [f"depositaire_B.txt:ligne {numero}"]})
    if not positions:
        raise ValueError("Conservateur B : aucune position")
    attendu = int(lignes[-1][1:7])
    controles = [controle("B", f"depositaire_B.txt:ligne {len(lignes)}", "nombre_details", attendu == len(positions),
                          "Nombre de détails avant toute exclusion", attendu, len(positions))]
    return pd.DataFrame(positions), controles


def lire_c(contenu: bytes):
    racine = ET.fromstring(contenu)
    ns = {"c": "urn:orsay:depositaire-c:positions:2026"}
    if racine.tag != "{" + ns["c"] + "}RelevePositions":
        raise ValueError("Conservateur C : racine ou espace de noms incorrect")
    date = date_iso(racine.findtext("c:Entete/c:DateArrete", namespaces=ns), "%d%m%Y")
    attendu = int(racine.findtext("c:Entete/c:NbItems", namespaces=ns))
    items = racine.findall("c:Positions/c:Item", ns)
    positions = []
    for numero, item in enumerate(items, 1):
        dimensions = item.findall("c:Dim", ns)
        valeurs = {d.get("prop"): d.text or "" for d in dimensions}
        if len(valeurs) != len(dimensions) or not {"ACTION", "COMPTE", "CODE_ISIN", "QUANTITE", "LOT"}.issubset(valeurs):
            raise ValueError(f"Conservateur C:Item {numero} : dimensions absentes ou dupliquées")
        positions.append({"compte": valeurs["COMPTE"], "isin": valeurs["CODE_ISIN"],
                          "quantite": valeurs["QUANTITE"], "action": valeurs["ACTION"], "date_arrete": date,
                          "sources": [f"depositaire_C.xml:Item {numero}, lot {valeurs['LOT']}"]})
    if not positions:
        raise ValueError("Conservateur C : aucun Item")
    controles = [controle("C", "depositaire_C.xml:Entete/NbItems", "nombre_items", attendu == len(items),
                          "Comptage incluant les annulations", attendu, len(items))]
    return pd.DataFrame(positions), controles


def lire_interne(contenu: bytes, nom_source: str = "positions_internes.csv") -> pd.DataFrame:
    """Garder les valeurs brutes et la ligne physique de chaque position."""
    lecteur = csv.reader(StringIO(contenu.decode("utf-8-sig"), newline=""), delimiter=";", strict=True)
    colonnes = next(lecteur, [])
    requises = {"date_arrete", "sous_compte", "isin", "libelle", "quantite", "depositaire"}
    if not requises.issubset(colonnes) or len(colonnes) != len(set(colonnes)):
        raise ValueError(f"{nom_source} : en-tête absent, incomplet ou dupliqué")
    if "sources" in colonnes:
        raise ValueError(f"{nom_source} : colonne réservée 'sources'")

    positions = []
    while True:
        ligne = lecteur.line_num + 1
        valeurs = next(lecteur, None)
        if valeurs is None:
            break
        if len(valeurs) != len(colonnes):
            raise ValueError(f"{nom_source}, ligne {ligne} : nombre de champs incorrect")
        position = dict(zip(colonnes, valeurs))
        position["sources"] = [f"{nom_source}:ligne {ligne}"]
        positions.append(position)

    if not positions:
        raise ValueError(f"{nom_source} : aucune position")
    return pd.DataFrame(positions)


if __name__ == "__main__":
    fichier = Path(__file__).resolve().parents[1] / "donnees" / "positions_internes.csv"
    positions = lire_interne(fichier.read_bytes())
    print(f"Nombre de positions : {len(positions)}")
    print(positions.to_string(index=False))
