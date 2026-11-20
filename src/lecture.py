"""Lecture des sources sans nettoyage ni modification des fichiers."""

import csv
from io import StringIO
from pathlib import Path

import pandas as pd


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
