"""
Module de nettoyage et de mise en forme des données de disponibilité
issues du booking engine SRP.

Ce module est volontairement indépendant de Streamlit afin de rester
facilement testable.
"""
from __future__ import annotations

import html
import unicodedata
from datetime import datetime
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Nettoyage de texte (encodage / entités HTML)
# ---------------------------------------------------------------------------

_CORRECTIONS = {
    "Ã©": "é",
    "Ã¨": "è",
    "Ã ": "à",
    "Ã§": "ç",
    "Ã«": "ë",
    "Ã¯": "ï",
    "Ã´": "ô",
    "Ã¢": "â",
    "Ã¹": "ù",
    "Ã»": "û",
    "Ã®": "î",
    "Ã¼": "ü",
    "Ã±": "ñ",
    "Ã": "É",
    "Ã€": "À",
    "Ã‡": "Ç",
    "\\*": "★",
    "3\\*": "3★",
    "4\\*": "4★",
    "5\\*": "5★",
    "Ã\x83": "À",
    "Ã\x89": "É",
    "Ã\x8a": "Ê",
}


def clean_text(text: Any) -> str:
    """Nettoie et corrige l'encodage d'un texte provenant de l'API."""
    if not text:
        return ""

    text = html.unescape(str(text))
    text = unicodedata.normalize("NFKC", text)

    for wrong, correct in _CORRECTIONS.items():
        text = text.replace(wrong, correct)

    return text


# ---------------------------------------------------------------------------
# Statuts de disponibilité (libellé + couleur pour l'UI)
# ---------------------------------------------------------------------------

STATUS_STYLES = {
    "Disponible": "#2E8B57",
    "Complet": "#C0392B",
    "Dernière minute": "#D98A1F",
    "Meilleur tarif": "#267492",
}


def _resolve_status(day_data: dict) -> str:
    if day_data.get("soldOut", False):
        return "Complet"
    if day_data.get("lastMinute", False):
        return "Dernière minute"
    if day_data.get("bestPrice", False):
        return "Meilleur tarif"
    return "Disponible"


# ---------------------------------------------------------------------------
# Formatage principal
# ---------------------------------------------------------------------------

def format_availability(data: list) -> dict:
    """Transforme la réponse brute de l'API en métadonnées + DataFrame."""
    if not data or not isinstance(data, list) or len(data) == 0:
        return {"error": "Données invalides"}

    offer_data = data[0]
    rows: list[dict] = []

    metadata = {
        "titre": clean_text(offer_data.get("title", "")),
        "destination": clean_text(offer_data.get("destination", {}).get("label", "")),
        "hotel": clean_text(offer_data.get("hotel", {}).get("name", "")),
        "etoiles": offer_data.get("hotel", {}).get("stars", 0),
    }

    booking_engine = offer_data.get("bookingEngine", {})
    product = booking_engine.get("product", {})
    if "tourOperator" in product:
        metadata["tour_operator"] = {
            "code": clean_text(product["tourOperator"].get("code", "")),
            "label": clean_text(product["tourOperator"].get("label", "")),
        }

    availabilities = booking_engine.get("availabilities", {})

    for city_code, city_data in availabilities.items():
        for duration_code, month_map in city_data.items():
            for month, day_map in month_map.items():
                for day, day_data in day_map.items():
                    days, nights = map(int, duration_code.split("-"))

                    departure_date = datetime.fromtimestamp(day_data["departureDate"] / 1000)
                    return_date = (
                        datetime.fromtimestamp(day_data["returnDate"] / 1000)
                        if "returnDate" in day_data
                        else None
                    )

                    status = _resolve_status(day_data)

                    rows.append(
                        {
                            "ville_depart": clean_text(city_code),
                            "ville_depart_label": clean_text(day_data.get("departureLabel", city_code)),
                            "date_depart": departure_date,
                            "date_retour": return_date,
                            "jour_semaine_depart": departure_date.strftime("%A"),
                            "duree_jours": days,
                            "duree_nuits": nights,
                            "duree_label": f"{days}j / {nights}n",
                            "prix_actuel": day_data["price"],
                            "prix_normal": day_data.get("regularPrice", day_data["price"]),
                            "reduction_euro": day_data.get("reduction", 0),
                            "reduction_pourcentage": day_data.get("reductionRate", 0),
                            "type_chambre": clean_text(day_data.get("categoryCode", "")),
                            "type_chambre_label": clean_text(day_data.get("categoryLabel", "")),
                            "type_prix": clean_text(day_data.get("priceType", "")),
                            "pension": clean_text(day_data.get("boardType", "")),
                            "pension_label": clean_text(day_data.get("boardTypeLabel", "")),
                            "statut": status,
                            "participants_min": day_data.get("minParticipants", 1),
                            "participants_max": day_data.get("maxParticipants", 10),
                            "transport": clean_text(day_data.get("transport", "")),
                            "compagnie_aerienne": clean_text(day_data.get("airline", "")),
                            "vol_direct": day_data.get("directFlight", False),
                            "bagages_inclus": day_data.get("baggageIncluded", False),
                            "annulation_gratuite": day_data.get("freeCancellation", False),
                            "paiement_fractionne": day_data.get("installmentPayment", False),
                            "stock_restant": day_data.get("remainingStock", ""),
                        }
                    )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date_depart").reset_index(drop=True)

    return {
        "metadata": metadata,
        "disponibilites": df,
        "total_offres": len(df),
    }
