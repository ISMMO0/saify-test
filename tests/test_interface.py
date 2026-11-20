"""Tests d'interface ; données fictives et moteur simulé uniquement dans ce fichier."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import src.exports
import src.rapprochement


APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
COLONNES_SUSPENS = [
    "id_suspens", "date_arrete", "fonds", "isin", "conservateur_attendu",
    "conservateur_constate", "quantite_interne", "quantite_conservateur",
    "ecart", "type", "action", "sources_internes", "sources_conservateurs",
]
FICHIERS_FICTIFS = {
    "interne": ("test.csv", b"csv fictif", "text/csv"),
    "a": ("test_a.xlsx", b"excel a fictif", "application/octet-stream"),
    "b": ("test.txt", b"txt fictif", "text/plain"),
    "c": ("test.xml", b"xml fictif", "application/xml"),
    "parametrage": ("test_parametrage.xlsx", b"parametrage fictif", "application/octet-stream"),
}


def charger_fichiers(app):
    for cle, fichier in FICHIERS_FICTIFS.items():
        app.file_uploader(key=f"fichier_{cle}").set_value(fichier)
    return app.run()


@pytest.fixture
def moteur_simule(monkeypatch):
    appels = []
    positions = pd.DataFrame([{
        "fonds": "FONDS FICTIF A", "isin": "ISIN_FICTIF_1", "conservateur": "A",
        "quantite": Decimal("9007199254740993.01"), "sources": ["test.csv:2"],
    }])
    suspens = pd.DataFrame([
        ["TEST-1", "2026-09-25", "FONDS FICTIF A", "ISIN_FICTIF_1", "A", "B",
         Decimal("9007199254740993.01"), Decimal("9007199254740993.01"), Decimal("0"),
         "TYPE FICTIF", "ACTION FICTIVE", ["test.csv:2"], ["test_b.txt:2"]],
        ["TEST-2", "2026-09-25", "FONDS FICTIF B", "ISIN_FICTIF_2", "C", "C",
         Decimal("2"), Decimal("3"), Decimal("1"), "TYPE FICTIF", "ACTION FICTIVE",
         ["test.csv:3"], ["test_c.xml:Item 1"]],
    ], columns=COLONNES_SUSPENS)
    controles = pd.DataFrame([{
        "source": "test_b.txt", "reference": "ligne 4", "controle": "total fictif",
        "statut": "OK", "motif": "test uniquement", "attendu": "2", "constate": "2",
        "bloquant": False,
    }])
    resultat = {
        "positions_internes": positions, "positions_conservateurs": positions.copy(),
        "suspens": suspens, "controles": controles, "valide": True,
        "date_arrete": "2026-09-25",
    }

    def rapprocher_simule(sources):
        appels.append(sources.copy())
        return resultat

    monkeypatch.setattr(src.rapprochement, "rapprocher", rapprocher_simule, raising=False)
    monkeypatch.setattr(src.exports, "exporter_csv", lambda table: b"export CSV fictif", raising=False)
    monkeypatch.setattr(src.exports, "generer_point_situation",
                        lambda resultat: "# Point de situation fictif pour test", raising=False)
    return resultat, appels


def test_chargement_initial_sans_resultat():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert len(app.file_uploader) == 5
    assert app.button[0].disabled
    assert not app.dataframe
    assert not app.download_button


def test_moteur_indisponible_message_explicite(monkeypatch):
    monkeypatch.delattr(src.rapprochement, "rapprocher", raising=False)
    app = charger_fichiers(AppTest.from_file(APP).run())
    app.button[0].click().run()
    assert not app.exception
    assert "ne sont pas encore disponibles" in app.error[0].value
    assert "resultat" not in app.session_state
    assert len(app.session_state["sources"]) == 5


def test_parcours_filtres_sources_precision_et_telechargements(moteur_simule):
    resultat, appels = moteur_simule
    app = charger_fichiers(AppTest.from_file(APP).run())
    assert not app.button[0].disabled
    app.button[0].click().run()
    assert not app.exception
    assert appels == [{cle: fichier[1] for cle, fichier in FICHIERS_FICTIFS.items()}]
    assert len(app.tabs) == 3
    assert "Contrôles bloquants satisfaits" in app.success[0].value
    assert app.dataframe[0].value.iloc[0]["quantite_interne"] == "9007199254740993.01"
    assert "test.csv:2" in app.json[0].value

    # Une livraison A → B doit rester visible pour chacun de ces conservateurs.
    for conservateur in ("A", "B"):
        app.multiselect(key="filtre_conservateur").set_value([conservateur]).run()
        assert app.dataframe[0].value["id_suspens"].tolist() == ["TEST-1"]
    app.multiselect(key="filtre_fonds").set_value(["FONDS FICTIF B"]).run()
    assert any("Aucun suspens ne correspond" in message.value for message in app.info)
    app.multiselect(key="filtre_conservateur").set_value([]).run()
    assert app.dataframe[0].value["id_suspens"].tolist() == ["TEST-2"]

    assert len(app.download_button) == 3
    for bouton in app.download_button:
        bouton.click().run()
        assert not app.exception
    assert len(appels) == 1
    assert len(app.session_state["resultat"]["suspens"]) == len(resultat["suspens"])
    assert len(app.session_state["sources"]) == 5


def test_controles_invalides_et_aucun_suspens_ne_signifient_pas_succes(moteur_simule):
    resultat, _ = moteur_simule
    resultat["valide"] = False
    resultat["suspens"] = pd.DataFrame(columns=COLONNES_SUSPENS)
    app = charger_fichiers(AppTest.from_file(APP).run())
    app.button[0].click().run()
    assert not app.exception
    assert "Résultat incomplet" in app.error[0].value
    assert not app.success
    assert any("Aucun suspens détecté" in message.value for message in app.info)
    assert app.subheader[0].value == "Arrêté : 2026-09-25"
    assert len(app.download_button) == 3


@pytest.mark.parametrize("retirer", [False, True])
def test_changement_entree_retire_ancien_resultat(moteur_simule, retirer):
    app = charger_fichiers(AppTest.from_file(APP).run())
    app.button[0].click().run()
    if retirer:
        app.file_uploader(key="fichier_interne").clear().run()
    else:
        app.file_uploader(key="fichier_interne").set_value(
            ("nouveau.csv", b"autre contenu fictif", "text/csv")
        ).run()
    assert not app.exception
    assert "resultat" not in app.session_state
    assert not app.download_button
    assert not app.dataframe
    assert app.button[0].disabled == retirer


def test_erreur_traitement_ne_conserve_pas_un_ancien_resultat(moteur_simule, monkeypatch):
    app = charger_fichiers(AppTest.from_file(APP).run())
    app.button[0].click().run()

    def echec(sources):
        raise ValueError("En-tête de test invalide")

    monkeypatch.setattr(src.rapprochement, "rapprocher", echec)
    app.button[0].click().run()
    assert not app.exception
    assert "En-tête de test invalide" in app.error[0].value
    assert "resultat" not in app.session_state
    assert not app.download_button
