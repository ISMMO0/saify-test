"""Rapprochement des positions : chargement local et restitution du moteur."""

from decimal import Decimal
from pathlib import Path
import sys

import streamlit as st

# Streamlit exécute ce fichier depuis app/ ; src/ se trouve à la racine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def table_affichable(table):
    """Préserver les décimales et rendre les références lisibles à l'écran."""
    def texte(valeur):
        if isinstance(valeur, Decimal):
            return format(valeur, "f")
        if isinstance(valeur, list):
            return " | ".join(str(reference) for reference in valeur)
        return valeur

    affichage = table.map(texte)
    for colonne in ("quantite", "quantite_interne", "quantite_conservateur", "ecart"):
        if colonne in affichage:
            affichage[colonne] = affichage[colonne].map(str)
    return affichage


st.set_page_config(page_title="Orsay Gestion · Rapprochement", layout="wide")
st.title("Rapprochement des positions")
st.caption("Orsay Gestion · Middle office · Inventaire PMS et conservateurs A, B, C")

fichiers = [
    ("interne", "Inventaire interne PMS — CSV", "csv", "Séparateur ;"),
    ("a", "Conservateur A — Excel", "xlsx", "Relevé des positions du conservateur A"),
    ("b", "Conservateur B — TXT", "txt", "Relevé à largeur fixe"),
    ("c", "Conservateur C — XML", "xml", "Relevé avec lots et annulations"),
    ("parametrage", "Paramétrage — Excel", "xlsx", "Comptes, fonds, types et actions"),
]

with st.sidebar:
    st.header("Fichiers du matin")
    st.caption("Chargez les cinq fichiers du même arrêté. Les originaux restent inchangés.")
    sources = {}
    for cle, libelle, extension, aide in fichiers:
        fichier = st.file_uploader(libelle, type=[extension], key=f"fichier_{cle}", help=aide)
        if fichier is not None:
            sources[cle] = fichier.getvalue()

    if sources != st.session_state.get("sources", {}):
        st.session_state.pop("resultat", None)
        st.session_state.pop("exports", None)
        for cle in ("filtre_fonds", "filtre_conservateur", "source_suspens"):
            st.session_state.pop(cle, None)
    st.session_state["sources"] = sources

    complet = len(sources) == len(fichiers) and all(sources.values())
    st.caption(f"{len(sources)} / {len(fichiers)} fichiers chargés")
    lancer = st.button("Lancer le rapprochement", type="primary", disabled=not complet)

if lancer:
    st.session_state.pop("resultat", None)
    st.session_state.pop("exports", None)
    try:
        from src.rapprochement import rapprocher
        from src.exports import exporter_csv, generer_point_situation
    except ImportError:
        st.error("Le moteur de rapprochement ou les exports ne sont pas encore disponibles. "
                 "Les fichiers sont conservés en session ; réessayez après leur installation.")
    else:
        try:
            with st.spinner("Lecture des fichiers, contrôles et comparaison des positions…"):
                resultat = rapprocher(st.session_state["sources"])
                exports = {
                    "suspens": exporter_csv(resultat["suspens"]),
                    "controles": exporter_csv(resultat["controles"]),
                    "point": generer_point_situation(resultat),
                }
            st.session_state["resultat"] = resultat
            st.session_state["exports"] = exports
        except ValueError as erreur:
            st.error(f"Rapprochement impossible : {erreur}")
        except Exception:
            st.error("Le traitement n'a pas abouti. Aucun résultat n'est disponible. "
                     "Faites vérifier les fichiers et le moteur avant de relancer.")

if "resultat" not in st.session_state:
    st.info("Chargez les cinq fichiers dans le panneau latéral, puis lancez le rapprochement. "
            "Aucun résultat métier n'est affiché avant le traitement.")
    st.stop()

resultat = st.session_state["resultat"]
exports = st.session_state["exports"]
suspens = resultat["suspens"]
st.subheader(f"Arrêté : {resultat['date_arrete']}")
if resultat["valide"]:
    st.success("Contrôles bloquants satisfaits. Les suspens et anomalies restent à examiner.")
else:
    st.error("Résultat incomplet ou contrôles bloquants en échec. "
             "Consultez « Contrôles et anomalies » avant toute utilisation du point de situation.")
st.caption(f"{len(suspens)} suspens au total · Aucun seuil de tolérance · "
           "Écart = quantité conservateur − quantité interne")

onglet_suspens, onglet_point, onglet_controles = st.tabs(
    ["Suspens", "Point de situation", "Contrôles et anomalies"]
)

with onglet_suspens:
    st.caption("Les filtres portent sur l'affichage. Les téléchargements et le point de situation "
               "couvrent l'ensemble du rapprochement.")
    fonds = sorted(suspens["fonds"].dropna().unique())
    conservateurs = sorted(
        valeur for valeur in (set(suspens["conservateur_attendu"].dropna())
                              | set(suspens["conservateur_constate"].dropna())) if valeur
    )
    colonne_fonds, colonne_conservateur = st.columns(2)
    with colonne_fonds:
        choix_fonds = st.multiselect("Fonds", fonds, key="filtre_fonds")
    with colonne_conservateur:
        choix_conservateur = st.multiselect(
            "Conservateur attendu ou constaté", conservateurs, key="filtre_conservateur"
        )
    selection = suspens
    if choix_fonds:
        selection = selection[selection["fonds"].isin(choix_fonds)]
    if choix_conservateur:
        selection = selection[selection["conservateur_attendu"].isin(choix_conservateur)
                              | selection["conservateur_constate"].isin(choix_conservateur)]

    if selection.empty:
        if suspens.empty:
            st.info("Aucun suspens détecté sur le périmètre traité. Vérifiez aussi les contrôles et exclusions.")
        else:
            st.info("Aucun suspens ne correspond aux filtres sélectionnés.")
    else:
        st.caption(f"{len(selection)} suspens affichés sur {len(suspens)}")
        st.dataframe(table_affichable(selection), hide_index=True, width="stretch")
        with st.expander("Consulter les références sources"):
            identifiant = st.selectbox(
                "Suspens à examiner", selection["id_suspens"].tolist(), key="source_suspens"
            )
            ligne = selection[selection["id_suspens"] == identifiant].iloc[0]
            st.write("**Sources internes**")
            st.json(ligne["sources_internes"])
            st.write("**Sources conservateurs**")
            st.json(ligne["sources_conservateurs"])

    st.download_button("Télécharger tous les suspens (CSV)", exports["suspens"],
                       file_name="suspens.csv", mime="text/csv", key="export_suspens")

with onglet_point:
    st.caption("Point de situation complet, prêt à copier ou à transmettre après examen des contrôles.")
    st.code(exports["point"], language="markdown", wrap_lines=True)
    st.download_button("Télécharger le point de situation", exports["point"],
                       file_name="point_situation.md", mime="text/markdown", key="export_point")

with onglet_controles:
    st.caption("Dates d'arrêté, totaux de contrôle, exclusions et anomalies ; références et motifs inclus.")
    st.dataframe(table_affichable(resultat["controles"]), hide_index=True, width="stretch")
    with st.expander("Consulter les positions préparées et leurs sources"):
        st.write("**Inventaire interne**")
        st.dataframe(table_affichable(resultat["positions_internes"]), hide_index=True, width="stretch")
        st.write("**Conservateurs**")
        st.dataframe(table_affichable(resultat["positions_conservateurs"]), hide_index=True, width="stretch")
    st.download_button("Télécharger tous les contrôles (CSV)", exports["controles"],
                       file_name="controles.csv", mime="text/csv", key="export_controles")
