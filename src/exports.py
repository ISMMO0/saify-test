"""Exports en mémoire ; aucune écriture dans les fichiers sources."""

from decimal import Decimal


def texte(valeur):
    if isinstance(valeur, Decimal):
        return format(valeur, "f")
    if isinstance(valeur, list):
        return " | ".join(str(v) for v in valeur)
    return str(valeur)


def exporter_csv(table) -> bytes:
    return table.map(texte).to_csv(index=False, sep=";", lineterminator="\n").encode("utf-8-sig")


def generer_point_situation(resultat) -> str:
    suspens = resultat["suspens"]
    controles = resultat["controles"]
    reserve = controles.loc[controles["statut"] != "OK"]
    lignes = [f"# Point de situation — arrêté du {resultat['date_arrete'] or 'non déterminé'}", "",
              "Contrôles bloquants : " + ("satisfaits." if resultat["valide"] else "ÉCHEC — résultat incomplet, à ne pas valider."),
              f"Nombre de suspens calculés : {len(suspens)} (source : table suspens du rapprochement).", "",
              "Convention : écart = quantité conservateur − quantité interne.",
              "Les quantités de titres et les nominaux ne sont pas additionnés entre valeurs.", ""]
    if not resultat["valide"]:
        lignes.extend(["Les suspens affichés sont provisoires. Une absence de suspens ne conclut pas à l'absence d'écarts.", ""])
    if len(suspens):
        lignes.extend(["## Répartition des suspens", ""])
        for fonds, groupe in suspens.groupby("fonds", sort=True):
            lignes.append(f"- {fonds} : {len(groupe)} (source : suspens filtrés sur ce fonds).")
        conservateurs = sorted((set(suspens["conservateur_attendu"]) | set(suspens["conservateur_constate"])) - {""})
        for code in conservateurs:
            compte = ((suspens["conservateur_attendu"] == code) | (suspens["conservateur_constate"] == code)).sum()
            lignes.append(f"- Conservateur {code} : {compte} suspens impliquant ce conservateur.")
        lignes.extend(["", "Une livraison chez un autre conservateur figure dans les deux répartitions, mais compte pour un seul suspens au total.", "", "## Détail et actions", ""])
        for s in suspens.to_dict("records"):
            lignes.extend([f"- {s['id_suspens']} — {s['fonds']} — {s['isin']} — {s['type']}",
                           f"  Conservateur attendu : {s['conservateur_attendu'] or 'aucun'} ; constaté : {s['conservateur_constate'] or 'aucun'}.",
                           f"  Interne : {texte(s['quantite_interne'])} ; conservateur : {texte(s['quantite_conservateur'])} ; écart : {texte(s['ecart'])}.",
                           f"  Action : {s['action']}.",
                           f"  Sources internes et typologie : {texte(s['sources_internes']) or 'aucune position interne'}.",
                           f"  Sources conservateurs : {texte(s['sources_conservateurs']) or 'aucune position livrée'}."])
    lignes.extend(["", "## Réserves et exclusions", ""])
    if reserve.empty:
        lignes.append("Aucune anomalie ni exclusion signalée.")
    for c in reserve.to_dict("records"):
        lignes.append(f"- {c['source']} — {c['reference']} : {c['motif']}"
                      f" (attendu : {c['attendu'] or '—'} ; constaté : {c['constate'] or '—'} ;"
                      f" {'bloquant' if c['bloquant'] else 'non bloquant'}).")
    return "\n".join(lignes) + "\n"
