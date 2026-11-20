from decimal import Decimal

import pytest

from src.lecture import lire_interne


ENTETE = "date_arrete;sous_compte;isin;libelle;quantite;depositaire\n"


def test_lecture_conserve_les_valeurs_et_les_lignes_a_traiter():
    contenu = ("\ufeff" + ENTETE
               + "2026-09-25;SC-TEST; fr0000014078 ;Titre;9007199254740993,01;Caceis Bank France\n"
               + "2026-09-25;P3G;FR0000011116;Passage;999999;CACEIS\n"
               + "2026-09-25;;FR0000011850;Incomplet;12345;EUROCLEAR\n").encode()

    table = lire_interne(contenu)

    assert len(table) == 3
    assert table.loc[0, "isin"] == " fr0000014078 "
    assert table.loc[0, "depositaire"] == "Caceis Bank France"
    assert Decimal(table.loc[0, "quantite"].replace(",", ".")) == Decimal("9007199254740993.01")
    assert table.loc[1, "sous_compte"] == "P3G"
    assert table.loc[2, "sous_compte"] == ""
    assert table.loc[2, "sources"] == ["positions_internes.csv:ligne 4"]


def test_reference_physique_apres_un_libelle_multiligne():
    contenu = (ENTETE
               + '2026-09-25;SC-TEST;FR0000014078;"Titre;avec\nretour";1;CACEIS\n'
               + "2026-09-25;SC-TEST;FR0000011116;Titre;2;CACEIS\n").encode()

    table = lire_interne(contenu, "inventaire.csv")

    assert table.loc[0, "libelle"] == "Titre;avec\nretour"
    assert table.loc[0, "sources"] == ["inventaire.csv:ligne 2"]
    assert table.loc[1, "sources"] == ["inventaire.csv:ligne 4"]


@pytest.mark.parametrize("contenu", [
    b"",
    b"date_arrete,sous_compte,isin,libelle,quantite,depositaire\n",
    (ENTETE.rstrip() + ";isin\n").encode(),
    (ENTETE.rstrip() + ";sources\n").encode(),
    ENTETE.encode(),
])
def test_rejette_les_entetes_invalides_et_inventaires_vides(contenu):
    with pytest.raises(ValueError):
        lire_interne(contenu)


@pytest.mark.parametrize("ligne", [
    "2026-09-25;SC-TEST;FR0000014078;Titre;1\n",
    "2026-09-25;SC-TEST;FR0000014078;Titre;1;CACEIS;EXTRA\n",
    "\n",
])
def test_rejette_une_ligne_incomplete_ou_decalee(ligne):
    with pytest.raises(ValueError, match="ligne 2"):
        lire_interne((ENTETE + ligne).encode())
