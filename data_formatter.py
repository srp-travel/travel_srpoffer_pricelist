"""
Module de nettoyage et de mise en forme des données de disponibilité
issues du booking engine SRP.

Ce module est volontairement indépendant de Streamlit afin de rester
facilement testable.
"""
from __future__ import annotations

import html
import unicodedata
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

# ---------------------------------------------------------------------------
# Fuseau horaire de référence
# ---------------------------------------------------------------------------
# Les timestamps renvoyés par l'API (en millisecondes) représentent en réalité
# minuit heure de Paris (Europe/Paris), mais sous forme d'epoch UTC. Une simple
# conversion naïve (datetime.fromtimestamp sans tz) décale donc la date d'un
# jour selon le fuseau du serveur d'exécution. On convertit systématiquement
# en heure de Paris pour retrouver la date réellement affichée sur le site.
PARIS_TZ = ZoneInfo("Europe/Paris")


def _timestamp_to_paris_date(timestamp_ms: Any) -> datetime | None:
    """Convertit un timestamp epoch (ms) en date/heure locale Europe/Paris."""
    if timestamp_ms is None:
        return None
    try:
        ts_seconds = float(timestamp_ms) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts_seconds, tz=timezone.utc).astimezone(PARIS_TZ)


def _safe_dict(value: Any) -> dict:
    """Retourne un dict exploitable même si la valeur d'origine est None."""
    return value if isinstance(value, dict) else {}


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
    """Transforme la réponse brute de l'API en métadonnées + DataFrame.

    Gère automatiquement les différentes variantes de réponse rencontrées
    (offres hôtel classiques avec villes de départ, offres "Sans Transport"
    de type camping/mobil-home, champs hotel/destination explicitement nuls,
    etc.).
    """
    if not data or not isinstance(data, list) or len(data) == 0:
        return {"error": "Données invalides"}

    offer_data = data[0]
    if not isinstance(offer_data, dict):
        return {"error": "Format de données inattendu"}

    rows: list[dict] = []

    hotel_data = _safe_dict(offer_data.get("hotel"))
    destination_data = _safe_dict(offer_data.get("destination"))

    metadata = {
        "titre": clean_text(offer_data.get("title", "")),
        "destination": clean_text(destination_data.get("label", "")),
        "hotel": clean_text(hotel_data.get("name", "")),
        "etoiles": hotel_data.get("stars", 0),
    }

    booking_engine = _safe_dict(offer_data.get("bookingEngine"))
    product = _safe_dict(booking_engine.get("product"))
    tour_operator = _safe_dict(product.get("tourOperator"))
    if tour_operator:
        metadata["tour_operator"] = {
            "code": clean_text(tour_operator.get("code", "")),
            "label": clean_text(tour_operator.get("label", "")),
        }

    # Correspondance code ville -> libellé lisible (ex: "XXX" -> "Sans Transport").
    # Présente au niveau racine de la réponse pour les offres sans transport
    # (camping, mobil-home) ; sert de repli quand departureLabel est absent.
    city_labels = _safe_dict(offer_data.get("cities"))

    availabilities = _safe_dict(booking_engine.get("availabilities"))

    for city_code, city_data in availabilities.items():
        if not isinstance(city_data, dict):
            continue
        for duration_code, month_map in city_data.items():
            if not isinstance(month_map, dict):
                continue
            try:
                days, nights = map(int, duration_code.split("-"))
            except (ValueError, AttributeError):
                continue

            for month, day_map in month_map.items():
                if not isinstance(day_map, dict):
                    continue
                for day, day_data in day_map.items():
                    if not isinstance(day_data, dict) or "departureDate" not in day_data:
                        continue

                    departure_date = _timestamp_to_paris_date(day_data.get("departureDate"))
                    if departure_date is None:
                        continue
                    return_date = _timestamp_to_paris_date(day_data.get("returnDate"))

                    status = _resolve_status(day_data)

                    ville_label = (
                        clean_text(day_data.get("departureLabel"))
                        or clean_text(city_labels.get(city_code))
                        or clean_text(city_code)
                    )

                    rows.append(
                        {
                            "ville_depart": clean_text(city_code),
                            "ville_depart_label": ville_label,
                            "date_depart": departure_date.replace(tzinfo=None),
                            "date_retour": return_date.replace(tzinfo=None) if return_date else None,
                            "jour_semaine_depart": departure_date.strftime("%A"),
                            "duree_jours": days,
                            "duree_nuits": nights,
                            "duree_label": f"{days}j / {nights}n",
                            "prix_actuel": day_data.get("price"),
                            "prix_normal": day_data.get("regularPrice", day_data.get("price")),
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
        df = df.dropna(subset=["prix_actuel"]).sort_values("date_depart").reset_index(drop=True)

    return {
        "metadata": metadata,
        "disponibilites": df,
        "total_offres": len(df),
    }