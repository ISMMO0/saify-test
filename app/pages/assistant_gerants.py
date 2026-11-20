"""Questions des gérants : consultations SQLite contrôlées et traçables."""

from datetime import date
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

st.set_page_config(page_title="Orsay · Questions aux gérants", layout="wide")
st.title("Questions aux gérants")
st.caption("Base de gestion en lecture seule · Calculs Python · SQL et résultats sources visibles")
st.info("Photographie disponible au 25/09/2026. Encours titres au pied de coupon ; ce montant n'est pas une valeur liquidative complète.")

types = {"Encours valorisé": "encours", "Concentration par émetteur": "concentration",
         "Échéances à venir": "echeances", "Opérations en attente": "attente", "Éléments sur un suspens": "origine"}
with st.form("question_gerant"):
    mode = st.radio("Mode", ["Langage naturel — Anthropic", "Questions prédéfinies — sans API"])
    question = st.text_area("Votre question", placeholder="Quel est l'encours valorisé d'Orsay Patrimoine ?")
    categorie = st.selectbox("Consultation en mode prédéfini", list(types))
    fonds = st.selectbox("Fonds de référence", ["PAT", "OBL", "ACT"],
                         format_func=lambda f: {"PAT": "Orsay Patrimoine", "OBL": "Orsay Obligations", "ACT": "Orsay Actions Europe"}[f])
    arrete = st.date_input("Date de référence", value=date(2026, 9, 25))
    fin = st.date_input("Fin de l'horizon des échéances", value=date(2027, 3, 25))
    isin = st.text_input("ISIN pour rechercher les mouvements d'un suspens (facultatif)")
    lancer = st.form_submit_button("Obtenir la réponse", type="primary")

if lancer:
    st.session_state.pop("consultation_gerant", None)
    try:
        from src.base import consulter
        parametres = {"type_question": types[categorie], "fonds": fonds,
                      "date": arrete.isoformat(), "fin": fin.isoformat(), "isin": isin.strip().upper()}
        with st.spinner("Lecture de la question et consultation de la base…"):
            if mode.startswith("Langage naturel"):
                from src.assistant import comprendre_question
                parametres = comprendre_question(question, fonds, arrete.isoformat(), fin.isoformat())
            resultat = consulter(**parametres)
        st.session_state["consultation_gerant"] = (parametres, resultat)
    except (ValueError, FileNotFoundError) as erreur:
        st.error(str(erreur))
    except Exception:
        st.error("Consultation indisponible. Vérifiez la présence de donnees/orsay.db et réessayez en mode prédéfini.")

if "consultation_gerant" in st.session_state:
    parametres, resultat = st.session_state["consultation_gerant"]
    st.subheader("Réponse")
    st.write(resultat["reponse"])
    st.caption(f"Source : donnees/orsay.db · Fonds {parametres['fonds']} · Référence {parametres['date']}")
    with st.expander("Interprétation retenue", expanded=False):
        st.json(parametres)
    with st.expander("Requête exécutée et paramètres", expanded=True):
        st.code(resultat["sql"], language="sql")
        st.json(resultat["parametres"])
    st.subheader("Résultat brut de la base")
    st.dataframe(resultat["lignes"], hide_index=True, width="stretch")
    if resultat.get("details"):
        st.subheader("Détail des calculs et sources")
        st.dataframe(resultat["details"], hide_index=True, width="stretch")
