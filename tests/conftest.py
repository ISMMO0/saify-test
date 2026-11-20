from io import BytesIO

from openpyxl import Workbook
import pytest


def excel(feuilles):
    classeur = Workbook()
    classeur.remove(classeur.active)
    for nom, lignes in feuilles.items():
        feuille = classeur.create_sheet(nom)
        for ligne in lignes:
            feuille.append(ligne)
    sortie = BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


@pytest.fixture
def sources():
    return {
        "interne": ("date_arrete;sous_compte;isin;libelle;quantite;depositaire\n"
                    "2026-09-25;SC1;FR0000010001;Titre;10;CACEIS\n"
                    "2026-09-25;SC1;FR0000010373;Titre;5;EUROCLEAR\n"
                    "2026-09-25;SC1;FR0000052052;Titre;25;BP2S\n").encode(),
        "a": excel({"Positions": [
            ["RELEVE - ARRETE DU 25/09/2026"], [],
            ["Compte", "Code ISIN", "Désignation", "Quantité"],
            ["0041872", "FR0000010001", "Titre", "10"]]}),
        "b": b"H20260925RELEVE\nDORPFR0000010373000000000000500\nT000001\n",
        "c": b'<RelevePositions xmlns="urn:orsay:depositaire-c:positions:2026">'
             b'<Entete><DateArrete>25092026</DateArrete><NbItems>1</NbItems></Entete>'
             b'<Positions><Item><Dim prop="ACTION">C</Dim><Dim prop="COMPTE">ORS-PAT</Dim>'
             b'<Dim prop="CODE_ISIN">FR0000052052</Dim><Dim prop="QUANTITE">25,00</Dim>'
             b'<Dim prop="LOT">1</Dim></Item></Positions></RelevePositions>',
        "parametrage": excel({
            "TRANSCO_SOUS_COMPTES": [["sous_compte", "entite"], ["SC1", "FONDS"], ["SC2", "FONDS"]],
            "TRANSCO_DEPOSITAIRE_A": [["compte", "entite"], ["0041872", "FONDS"]],
            "TRANSCO_DEPOSITAIRE_B": [["code_desk", "entite"], ["ORP", "FONDS"]],
            "TRANSCO_DEPOSITAIRE_C": [["compte", "entite"], ["ORS-PAT", "FONDS"]],
            "TYPES_ECARTS": [["code", "libelle", "action_attendue"],
                             ["QTE", "Quantité différente", "Action QTE"],
                             ["ABS_DEP", "Absence dépositaire", "Action ABS_DEP"],
                             ["ABS_INT", "Absence interne", "Action ABS_INT"],
                             ["DEP", "Autre dépositaire", "Action DEP"]]})}
