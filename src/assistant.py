"""Anthropic choisit une consultation ; aucun SQL libre ni calcul n'est généré."""

import os
from pathlib import Path

from anthropic import Anthropic, APIError
from dotenv import load_dotenv


def comprendre_question(question, fonds="PAT", date="2026-09-25", fin="2027-03-25"):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("Clé Anthropic absente. Utilisez le mode Questions prédéfinies.")
    if not question.strip() or len(question) > 2000:
        raise ValueError("Saisissez une question de moins de 2 000 caractères.")
    schema = {
        "type": "object",
        "properties": {
            "type_question": {"type": "string", "enum": ["encours", "concentration", "echeances", "attente", "origine", "refus"]},
            "fonds": {"type": "string", "enum": ["PAT", "OBL", "ACT"]},
            "date": {"type": "string"}, "fin": {"type": "string"},
            "isin": {"type": "string"}, "message": {"type": "string"},
        },
        "required": ["type_question", "fonds", "date", "fin", "isin", "message"],
        "additionalProperties": False,
    }
    try:
        with Anthropic(max_retries=0, timeout=20.0) as client:
            resultat = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"), max_tokens=500,
                system=("Tu classes une question financière, sans calculer et sans produire de SQL. "
                        "PAT=Orsay Patrimoine, OBL=Orsay Obligations, ACT=Orsay Actions Europe. "
                        "Consultations : encours titres, concentration par émetteur, échéances de principal, "
                        "opérations en attente, mouvements candidats à l'origine d'un suspens. "
                        "Respecte le fonds et les dates demandés, sinon utilise le contexte fourni. "
                        "Pour une modification, une demande hors périmètre, plusieurs fonds ou une ambiguïté "
                        "non résolue : type_question=refus avec une explication ou question de clarification. "
                        "Pour origine, demander un ISIN si absent. Ne réponds jamais avec un chiffre inventé."),
                messages=[{"role": "user", "content": f"Contexte : fonds={fonds}, arrêté={date}, horizon={fin}. Question : {question}"}],
                tools=[{"name": "consulter", "description": "Sélectionner une consultation en lecture seule", "input_schema": schema}],
                tool_choice={"type": "tool", "name": "consulter"},
            )
    except APIError:
        raise ValueError("Anthropic indisponible (clé, crédit, modèle ou réseau). Utilisez les questions prédéfinies.") from None
    choix = next((bloc.input for bloc in resultat.content if bloc.type == "tool_use" and bloc.name == "consulter"), None)
    if not isinstance(choix, dict) or choix.get("type_question") not in schema["properties"]["type_question"]["enum"]:
        raise ValueError("Réponse Anthropic non exploitable : aucune consultation exécutée.")
    if choix["type_question"] == "refus":
        raise ValueError(str(choix.get("message", "Précisez votre question.")))
    return {cle: choix.get(cle, "") for cle in ("type_question", "fonds", "date", "fin", "isin")}
