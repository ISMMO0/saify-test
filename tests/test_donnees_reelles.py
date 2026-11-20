"""Vérification d'intégration facultative : les fichiers client restent locaux."""

from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from src.exports import exporter_csv, generer_point_situation
from src.rapprochement import rapprocher


def test_rapprochement_complet_et_exports_sans_modifier_les_sources():
    dossier = Path(__file__).resolve().parents[1] / "donnees"
    noms = {"interne": "positions_internes.csv", "a": "depositaire_A_20260925.xlsx",
            "b": "depositaire_B_20260925.txt", "c": "depositaire_C_20260925.xml", "parametrage": "parametrage.xlsx"}
    if not all((dossier / nom).is_file() for nom in noms.values()):
        pytest.skip("Les cinq fichiers client ne sont pas présents en local")
    sources = {cle: (dossier / nom).read_bytes() for cle, nom in noms.items()}
    empreintes = {cle: sha256(contenu).hexdigest() for cle, contenu in sources.items()}
    resultat = rapprocher(sources)
    assert resultat["valide"] is True
    assert resultat["date_arrete"] == "2026-09-25"
    assert len(resultat["positions_internes"]) == 30
    assert len(resultat["positions_conservateurs"]) == 29
    assert len(resultat["suspens"]) == 7
    suspens = resultat["suspens"].set_index("isin")
    assert set(suspens.index) == {"FR0000012965", "FR0000016297", "FR0000011488", "FR0000012966",
                                  "FR0000015927", "FR0000051641", "FR0000999914"}
    assert suspens.loc["FR0000012965", "ecart"] == Decimal(-25000)
    assert suspens.loc["FR0000016297", "ecart"] == Decimal(1000)
    assert suspens.loc["FR0000015927", "conservateur_attendu"] == "A"
    assert suspens.loc["FR0000015927", "conservateur_constate"] == "B"
    assert suspens.loc["FR0000015927", "ecart"] == Decimal(0)
    assert suspens.loc["FR0000051641", "ecart"] == Decimal(-50000)
    anomalies = resultat["controles"].query("statut == 'ANOMALIE'")
    assert len(anomalies) == 3 and not anomalies["bloquant"].any()
    for table in ("suspens", "controles", "positions_internes", "positions_conservateurs"):
        assert exporter_csv(resultat[table]).startswith(b"\xef\xbb\xbf")
    point = generer_point_situation(resultat)
    assert "Nombre de suspens calculés : 7" in point
    assert "Conservateur  :" not in point
    assert "ACTION=S" in point and "Sous-compte absent" in point
    assert {cle: sha256((dossier / nom).read_bytes()).hexdigest() for cle, nom in noms.items()} == empreintes
