"""Parcours Streamlit avec les fichiers locaux et le vrai moteur, sans simulation."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


RACINE = Path(__file__).resolve().parents[1]
FICHIERS = {
    "interne": "positions_internes.csv",
    "a": "depositaire_A_20260925.xlsx",
    "b": "depositaire_B_20260925.txt",
    "c": "depositaire_C_20260925.xml",
    "parametrage": "parametrage.xlsx",
}


@pytest.mark.parametrize("comptage_valide", [True, False])
def test_interface_fichiers_reels_moteur_et_exports(comptage_valide):
    chemins = {cle: RACINE / "donnees" / nom for cle, nom in FICHIERS.items()}
    if not all(chemin.is_file() for chemin in chemins.values()):
        pytest.skip("Les cinq fichiers fournis ne sont pas présents en local")
    sources = {cle: chemin.read_bytes() for cle, chemin in chemins.items()}
    empreintes = {cle: sha256(contenu).hexdigest() for cle, contenu in sources.items()}
    if not comptage_valide:
        sources["b"] = sources["b"].replace(b"T000013", b"T000014")

    app = AppTest.from_file(RACINE / "app" / "streamlit_app.py").run()
    for cle, contenu in sources.items():
        app.file_uploader(key=f"fichier_{cle}").set_value(
            (FICHIERS[cle], contenu, "application/octet-stream")
        )
    app.run()
    app.button[0].click().run()

    assert not app.exception
    resultat = app.session_state["resultat"]
    assert resultat["valide"] is comptage_valide
    assert resultat["date_arrete"] == "2026-09-25"
    assert len(resultat["suspens"]) == 7
    assert len(app.tabs) == 3
    assert len(app.download_button) == 3
    assert len(app.dataframe[0].value) == 7
    if comptage_valide:
        assert app.success and not app.error
    else:
        assert not app.success
        assert "Résultat incomplet" in app.error[0].value
        assert "ÉCHEC" in app.session_state["exports"]["point"]

    exports = app.session_state["exports"]
    csv_suspens = pd.read_csv(BytesIO(exports["suspens"]), sep=";", dtype=str, keep_default_na=False)
    csv_controles = pd.read_csv(BytesIO(exports["controles"]), sep=";", dtype=str)
    assert len(csv_suspens) == 7 and len(csv_controles) == len(resultat["controles"])
    assert "Nombre de suspens calculés : 7" in exports["point"]
    assert exports["suspens"].startswith(b"\xef\xbb\xbf")

    app.multiselect(key="filtre_fonds").set_value(["ORSAY OBLIGATIONS"]).run()
    assert not app.exception
    assert set(app.dataframe[0].value["fonds"]) == {"ORSAY OBLIGATIONS"}
    assert len(app.session_state["resultat"]["suspens"]) == 7
    for bouton in app.download_button:
        bouton.click().run()
        assert not app.exception
    assert {cle: sha256(chemin.read_bytes()).hexdigest() for cle, chemin in chemins.items()} == empreintes
