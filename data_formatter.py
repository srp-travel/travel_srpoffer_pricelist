"""
Module de nettoyage et de mise en forme des données de disponibilité
issues du booking engine SRP.

Ce module est volontairement indépendant de Streamlit afin de rester
facilement testable.
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Dates : on n'utilise JAMAIS le timestamp epoch "departureDate".
# ---------------------------------------------------------------------------
# Ce timestamp représente en théorie minuit heure de Paris, mais son
# interprétation (UTC vs local) est ambiguë et a provoqué un décalage d'un
# jour entre la date affichée et le prix associé. La structure JSON encode
# déjà la date de façon non ambiguë via les clés imbriquées :
#   availabilities[ville][j-n][MM-YYYY][DD] = { "day": "DD", ... }
# On reconstruit donc la date directement à partir de ces clés (source de
# vérité), sans jamais repasser par le timestamp.


def _build_date_from_keys(month_key: str, day_key: str) -> datetime | None:
    """Construit une date à partir des clés 'MM-YYYY' et 'DD' du JSON."""
    try:
        month_str, year_str = month_key.split("-")
        return datetime(int(year_str), int(month_str), int(day_key))
    except (ValueError, AttributeError, TypeError):
        return None


def _safe_dict(value: Any) -> dict:
    """Retourne un dict exploitable même si la valeur d'origine est None."""
    return value if isinstance(value, dict) else {}


_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)$", re.IGNORECASE)
_TRAILING_INDEX_RE = re.compile(r"[-_]?\d+$")


def _title_from_image_url(url: Any) -> str:
    """Déduit un titre lisible à partir du slug de l'URL de la photo produit.

    Beaucoup d'offres n'exposent aucun champ "titre" exploitable (title,
    hotel.name, document.title sont vides), mais le nom de fichier/dossier
    de la photo principale est un slug descriptif du produit
    (ex: ".../VINCCI-SAFARI-PALMS-TUNISIE-OVOYAGES-01.jpg" ou
    ".../camping-maeva-escapades-les-cottages-de-perpignan-1.jpeg").
    """
    if not isinstance(url, str) or not url:
        return ""
    path = url.split("?")[0]
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return ""
    filename = _IMAGE_EXT_RE.sub("", segments[-1])
    filename = _TRAILING_INDEX_RE.sub("", filename)
    if not filename or filename.isdigit():
        return ""
    words = [word for word in re.split(r"[-_]+", filename) if word]
    if len(words) < 2:
        return ""
    return " ".join(word.capitalize() for word in words)


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

    booking_engine = _safe_dict(offer_data.get("bookingEngine"))
    product = _safe_dict(booking_engine.get("product"))

    # Repli du titre : sur beaucoup d'offres (notamment "Sans Transport"), les
    # champs habituels (title, hotel.name, document.title) sont vides. On se
    # replie alors, dans l'ordre :
    #   1. le slug de la photo principale du produit (le plus descriptif) ;
    #   2. le `product.toCode` reformaté (identifiant parfois lisible, ex:
    #      "Fusion_Safira_Palms_Zarzis"), seulement s'il contient des lettres.
    document = _safe_dict(product.get("document"))
    main_image = _safe_dict(document.get("mainImage"))
    image_title = _title_from_image_url(main_image.get("url"))

    to_code = product.get("toCode", "")
    to_code_title = clean_text(to_code).replace("_", " ").strip() if to_code else ""
    if to_code_title.isdigit():
        to_code_title = ""

    titre = (
        clean_text(offer_data.get("title", ""))
        or clean_text(hotel_data.get("name", ""))
        or image_title
        or to_code_title
    )

    metadata = {
        "titre": titre,
        "destination": clean_text(destination_data.get("label", "")),
        "hotel": clean_text(hotel_data.get("name", "")),
        "etoiles": hotel_data.get("stars", 0),
    }

    tour_operator = _safe_dict(product.get("tourOperator"))
    if tour_operator:
        metadata["tour_operator"] = {
            "code": clean_text(tour_operator.get("code", "")),
            "label": clean_text(tour_operator.get("label", "")),
        }

    # Correspondance code ville -> libellé lisible (ex: "PAR" -> "Paris").
    # Cette table est exposée dans `bookingEngine.cities` pour les offres
    # classiques, et parfois recopiée à la racine de la réponse pour les
    # offres "Sans Transport" (camping, mobil-home) : on regarde les deux.
    city_labels = _safe_dict(booking_engine.get("cities")) or _safe_dict(
        offer_data.get("cities")
    )

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
                    if not isinstance(day_data, dict):
                        continue

                    # La date fait foi via les clés JSON (mois/année de la
                    # boucle + jour), jamais via le timestamp epoch.
                    day_key = str(day_data.get("day", day))
                    departure_date = _build_date_from_keys(month, day_key)
                    if departure_date is None:
                        continue

                    night_nb = day_data.get("nightNb", nights)
                    try:
                        return_date = departure_date + timedelta(days=int(night_nb))
                    except (TypeError, ValueError):
                        return_date = None

                    status = _resolve_status(day_data)

                    # Correspondance ville de départ -> libellé : la table
                    # `cities` (racine de la réponse) fait foi ; on ne se
                    # replie sur `departureLabel` / le code brut qu'en son
                    # absence.
                    ville_label = (
                        clean_text(city_labels.get(city_code))
                        or clean_text(day_data.get("departureLabel"))
                        or clean_text(city_code)
                    )

                    prix_actuel = day_data.get("price")
                    prix_normal = day_data.get("regularPrice", prix_actuel)

                    prix_barre = None
                    reduction_pourcentage = 0.0
                    if (
                        prix_actuel is not None
                        and prix_normal is not None
                        and prix_normal > prix_actuel
                    ):
                        prix_barre = prix_normal
                        reduction_pourcentage = round(
                            (prix_normal - prix_actuel) / prix_normal * 100, 1
                        )

                    rows.append(
                        {
                            "ville_depart": clean_text(city_code),
                            "ville_depart_label": ville_label,
                            "date_depart": departure_date,
                            "date_retour": return_date,
                            "jour_semaine_depart": departure_date.strftime("%A"),
                            "duree_jours": days,
                            "duree_nuits": nights,
                            "duree_label": f"{days}j / {nights}n",
                            "prix_actuel": prix_actuel,
                            "prix_normal": prix_normal,
                            "prix_barre": prix_barre,
                            "reduction_euro": day_data.get("reduction", 0),
                            "reduction_pourcentage": reduction_pourcentage,
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