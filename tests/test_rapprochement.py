from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook
import pytest

from src.exports import exporter_csv, generer_point_situation
from src.rapprochement import rapprocher


def changer_cellule(contenu, feuille, cellule, valeur):
    classeur = load_workbook(BytesIO(contenu))
    classeur[feuille][cellule] = valeur
    sortie = BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


def test_resultat_sans_suspens_garde_date_et_contrat(sources):
    resultat = rapprocher(sources)
    assert resultat["valide"] is True
    assert resultat["date_arrete"] == "2026-09-25"
    assert resultat["suspens"].empty
    assert len(resultat["positions_internes"]) == 3
    assert len(resultat["positions_conservateurs"]) == 3
    assert "2026-09-25" in generer_point_situation(resultat)
    assert "Nombre de suspens calculés : 0" in generer_point_situation(resultat)


def test_ecart_unite_et_action_du_parametrage(sources):
    sources["a"] = changer_cellule(sources["a"], "Positions", "D4", "9")
    sources["parametrage"] = changer_cellule(sources["parametrage"], "TYPES_ECARTS", "C2", "Action sur mesure")
    resultat = rapprocher(sources)
    assert resultat["valide"] is True
    assert len(resultat["suspens"]) == 1
    s = resultat["suspens"].iloc[0]
    assert s["ecart"] == Decimal(-1)
    assert s["type"] == "Quantité différente"
    assert s["action"] == "Action sur mesure"
    assert any("TYPES_ECARTS:ligne 2" in source for source in s["sources_internes"])
    assert s["sources_conservateurs"][0] == "depositaire_A_20260925.xlsx/Positions:ligne 4"


@pytest.mark.parametrize("quantite,ecart", [("5", "0"), ("4", "1")])
def test_mauvais_conservateur_un_seul_suspens(sources, quantite, ecart):
    sources["interne"] = sources["interne"].replace(b";5;EUROCLEAR", f";{quantite};CACEIS".encode())
    resultat = rapprocher(sources)
    assert len(resultat["suspens"]) == 1
    s = resultat["suspens"].iloc[0]
    assert (s["conservateur_attendu"], s["conservateur_constate"]) == ("A", "B")
    assert s["type"] == "Autre dépositaire"
    assert s["ecart"] == Decimal(ecart)
    point = generer_point_situation(resultat)
    assert "Nombre de suspens calculés : 1" in point
    assert "Conservateur  :" not in point


@pytest.mark.parametrize("cle,ancien,nouveau", [
    ("b", b"T000001", b"T000002"), ("c", b"<NbItems>1", b"<NbItems>9")])
def test_controle_comptage_bloque_validation(sources, cle, ancien, nouveau):
    sources[cle] = sources[cle].replace(ancien, nouveau)
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    assert resultat["controles"]["bloquant"].any()
    assert "ÉCHEC" in generer_point_situation(resultat)


@pytest.mark.parametrize("cle,ancien,nouveau", [
    ("interne", b"2026-09-25", b"2026-09-24"), ("b", b"H20260925", b"H20260924"),
    ("c", b"25092026", b"24092026")])
def test_dates_divergentes_pas_de_comparaison(sources, cle, ancien, nouveau):
    sources[cle] = sources[cle].replace(ancien, nouveau)
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    assert resultat["date_arrete"] == ""
    assert resultat["suspens"].empty
    assert "absence de suspens ne conclut pas" in generer_point_situation(resultat)


def test_date_a_lue_dans_titre(sources):
    sources["a"] = changer_cellule(sources["a"], "Positions", "A1", "ARRETE DU 24/09/2026")
    assert rapprocher(sources)["valide"] is False


def test_date_invalide_meme_sur_ligne_exclue(sources):
    sources["interne"] += b"2026-09-99;P3G;FR0000010001;Titre;1;CACEIS\n"
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    assert resultat["date_arrete"] == ""
    assert resultat["suspens"].empty
    assert any("ligne 5" in c["reference"] and c["controle"] == "date_arrete"
               for c in resultat["controles"].to_dict("records"))


@pytest.mark.parametrize("cle", ["interne", "a", "b", "c", "parametrage"])
def test_fichier_illisible_visible_sans_faux_suspens(sources, cle):
    sources[cle] = b"illisible"
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    assert resultat["suspens"].empty
    assert resultat["controles"].loc[resultat["controles"]["source"] == cle, "bloquant"].any()


def test_compte_inconnu_et_action_c_inconnue_bloquants(sources):
    sources["interne"] = sources["interne"].replace(b"SC1", b"SC_INCONNU", 1)
    sources["c"] = sources["c"].replace(b">C</Dim>", b">X</Dim>")
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    motifs = " ".join(resultat["controles"]["motif"])
    assert "Compte non reconnu" in motifs
    assert "ACTION inconnue" in motifs


def test_parametrage_duplique_refuse(sources):
    sources["parametrage"] = changer_cellule(sources["parametrage"], "TRANSCO_SOUS_COMPTES", "A3", "SC1")
    resultat = rapprocher(sources)
    assert resultat["valide"] is False
    assert any("dupliquée" in m for m in resultat["controles"]["motif"])


def test_export_csv_decimal_exact_bom_et_listes(sources):
    grand = "99999999999999999999999999999999999999999999999999.01"
    sources["interne"] = sources["interne"].replace(b";10;", f";{grand};".encode())
    resultat = rapprocher(sources)
    sortie = exporter_csv(resultat["suspens"])
    assert sortie.startswith(b"\xef\xbb\xbf")
    texte = sortie.decode("utf-8-sig")
    assert grand in texte
    assert "id_suspens;date_arrete" in texte
    assert "positions_internes.csv:ligne 2 | parametrage" in texte
    assert "E+" not in texte
    assert grand in generer_point_situation(resultat)
