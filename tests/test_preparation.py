from decimal import Decimal

import pytest

from src.lecture import lire_a, lire_b, lire_c, lire_interne, lire_parametrage
from src.preparation import normaliser_conservateur, preparer, quantite_exacte, somme_exacte


def test_compte_a_conserve_ses_zeros(sources):
    table, _ = lire_a(sources["a"])
    assert table.iloc[0]["compte"] == "0041872"
    assert "ligne 4" in table.iloc[0]["sources"][0]
    assert "0041872" in lire_parametrage(sources["parametrage"])["TRANSCO_DEPOSITAIRE_A"]


def test_decimales_implicites_et_total_b(sources):
    table, controles = lire_b(sources["b"].replace(b"0000500", b"0000501"))
    assert quantite_exacte(table.iloc[0]["quantite"]) == Decimal("5.01")
    assert controles[0]["statut"] == "OK"
    _, controles = lire_b(sources["b"].replace(b"T000001", b"T000002"))
    assert controles[0]["bloquant"] is True


def test_annulation_c_exclue_lots_sommes_et_comptage(sources):
    contenu = sources["c"]
    item = contenu[contenu.index(b"<Item>"):contenu.index(b"</Item>") + 7]
    contenu = contenu.replace(b"</Positions>", item.replace(b">1</Dim>", b">2</Dim>")
                              + item.replace(b">C</Dim>", b">S</Dim>") + b"</Positions>")
    contenu = contenu.replace(b"<NbItems>1", b"<NbItems>3")
    brut, controles = lire_c(contenu)
    table, exclusions = preparer(brut, lire_parametrage(sources["parametrage"]), "C")
    assert len(table) == 1
    assert table.iloc[0]["quantite"] == Decimal("50")
    assert any("Item 2" in s for s in table.iloc[0]["sources"])
    assert controles[0]["statut"] == "OK"
    assert len(exclusions) == 1 and "ACTION=S" in exclusions[0]["motif"]
    assert "Item 3" in exclusions[0]["reference"]
    _, controles = lire_c(contenu.replace(b"<NbItems>3", b"<NbItems>2"))
    assert controles[0]["bloquant"] is True


def test_exclusions_agregation_et_normalisation(sources):
    contenu = sources["interne"] + (
        "2026-09-25;SC2; fr0000010001 ;Titre;2;Caceis Bank France\n"
        "2026-09-25;P3G;FR0000010001;Titre;999;CACEIS\n"
        "2026-09-25;;FR0000010001;Titre;888;CACEIS\n").encode()
    table, controles = preparer(lire_interne(contenu), lire_parametrage(sources["parametrage"]), "interne")
    assert len(table) == 3
    assert table.loc[table["isin"] == "FR0000010001", "quantite"].iloc[0] == Decimal(12)
    assert len(controles) == 2
    assert any("P3G" in c["motif"] for c in controles)
    assert any("Sous-compte absent" in c["motif"] and "ligne 7" in c["reference"] for c in controles)


@pytest.mark.parametrize("libelle,code", [("Caceis Bank France", "A"), ("EUROCLEAR FR", "B"),
                                        ("Bnp Paribas SS", "C"), ("BP2S", "C")])
def test_normalisation_conservateur(libelle, code):
    assert normaliser_conservateur(libelle) == code


@pytest.mark.parametrize("valeur", ["", "NaN", "Infinity", "1 2", "=10", "1,2.3"])
def test_quantites_invalides_refusees(valeur):
    with pytest.raises(ValueError):
        quantite_exacte(valeur)


def test_somme_exacte_au_dela_precision_par_defaut():
    assert somme_exacte([Decimal("9" * 50), Decimal("0.01")]) == Decimal("9" * 50 + ".01")


def test_ligne_ininterpretable_visible_bloquante(sources):
    table = lire_interne(sources["interne"].replace(b";10;", b";NaN;"))
    resultat, controles = preparer(table, lire_parametrage(sources["parametrage"]), "interne")
    assert len(resultat) == 2
    assert controles[0]["bloquant"] is True


@pytest.mark.parametrize("libelle", ["Inconnu", "BNP et CACEIS"])
def test_conservateur_inconnu_ou_ambigu_refuse(libelle):
    with pytest.raises(ValueError):
        normaliser_conservateur(libelle)


@pytest.mark.parametrize("contenu", [
    b"H20260925RELEVE\nDORPFR000001037300000000000050\nT000001\n",
    b"H20260925RELEVE\nDORPFR0000010373ABCDEFGHIJKLMNO\nT000001\n",
    b"H20260925RELEVE\nDORPFR0000010373000000000000500\n",
])
def test_largeur_fixe_b_invalide_refusee(contenu):
    with pytest.raises(ValueError):
        lire_b(contenu)
