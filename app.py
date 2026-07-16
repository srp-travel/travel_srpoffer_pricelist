"""
Travel Offer Catalog Prices
----------------------------
Application Streamlit minimaliste pour analyser les disponibilités
et les prix d'une offre voyage SRP ou d'une vente complète (multi-offres).
"""
from __future__ import annotations

import io
import re
from typing import Optional, TypedDict

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup, Tag

from data_formatter import format_availability

# ---------------------------------------------------------------------------
# Typage explicite (évite les faux positifs Pylance sur les DataFrames)
# ---------------------------------------------------------------------------
class OfferResult(TypedDict, total=False):
    error: str
    metadata: dict
    disponibilites: pd.DataFrame
    total_offres: int


# ---------------------------------------------------------------------------
# Configuration générale
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Travel Offer Catalog Prices",
    page_icon="🏖️",
    layout="wide",
)

API_URL_TEMPLATE: str = st.secrets.get(
    "API_URL",
    "https://hiddenprod-showroomprive.orchestra-platform.com/ajax/bookingEngine/{offer_id}",
)
SALE_URL_TEMPLATE: str = st.secrets.get(
    "SALE_URL",
    "https://hiddenprod-showroomprive.orchestra-platform.com/sale?id={sale_id}",
)

API_USER: str = st.secrets.get("API_USER", "")
API_PASSWORD: str = st.secrets.get("API_PASSWORD", "")
AUTH_TUPLE: Optional[tuple[str, str]] = (
    (API_USER, API_PASSWORD) if API_USER and API_PASSWORD else None
)

DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Accept-Charset": "utf-8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}

REQUEST_TIMEOUT: int = 15
CACHE_TTL: int = 300

DISPLAY_COLUMNS: list[str] = [
    "ville_affichee",
    "date_depart",
    "duree_label",
    "prix_actuel",
]

DISPLAY_COLUMN_LABELS: dict[str, str] = {
    "offre_id": "Offre",
    "offre_titre": "Titre de l'offre",
    "ville_affichee": "Ville de départ",
    "date_depart": "Date de départ",
    "duree_label": "Durée du séjour",
    "prix_actuel": "Prix affiché",
}


class SaleInfo(TypedDict):
    titre: str
    offer_ids: list[str]


# ---------------------------------------------------------------------------
# Fonctions de récupération réseau (mises en cache)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_offer(offer_id: str) -> OfferResult:
    """Interroge l'API booking pour une offre donnée et retourne un résultat structuré."""
    url = API_URL_TEMPLATE.format(offer_id=offer_id)
    try:
        response = requests.get(
            url, headers=DEFAULT_HEADERS, auth=AUTH_TUPLE, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return {"error": f"Timeout lors de la récupération de l'offre {offer_id}."}
    except requests.exceptions.RequestException as exc:
        return {"error": f"Erreur de connexion (offre {offer_id}) : {exc}"}

    response.encoding = "utf-8"
    try:
        payload = response.json()
    except ValueError:
        return {"error": f"Réponse JSON invalide pour l'offre {offer_id}."}

    formatted = format_availability(payload)
    return {
        "metadata": formatted.get("metadata", {}),
        "disponibilites": formatted.get("disponibilites", pd.DataFrame()),
        "total_offres": formatted.get("total_offres", 0),
    }


def _extract_sale_title(soup: BeautifulSoup, sale_id: str) -> str:
    """Tente de retrouver le nom de la vente depuis le HTML (meta og:title, h1, puis title)."""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if isinstance(og_title, Tag):
        content = og_title.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        text = h1.get_text(strip=True)
        if text:
            return text

    if soup.title and soup.title.string:
        text = soup.title.string.strip()
        if text:
            return text

    return f"Vente {sale_id}"


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_sale_info(sale_id: str) -> SaleInfo:
    """Récupère la page HTML publique d'une vente : titre et identifiants d'offres."""
    url = SALE_URL_TEMPLATE.format(sale_id=sale_id)
    html_headers = {"User-Agent": DEFAULT_HEADERS["User-Agent"]}

    try:
        response = requests.get(
            url, headers=html_headers, auth=AUTH_TUPLE, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        st.error(f"Erreur d'accès à la vente {sale_id} : {exc}")
        return {"titre": f"Vente {sale_id}", "offer_ids": []}

    soup = BeautifulSoup(response.text, "html.parser")
    offer_ids: set[str] = set()

    id_in_query = re.compile(r"id=(\d+)")
    id_in_path = re.compile(r"(?:/|-)(\d{5,8})(?:\b|\.|\?|/)")

    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue
        href_value = link.get("href")
        href = href_value if isinstance(href_value, str) else ""
        if not href or "offer" not in href.lower():
            continue

        match = id_in_query.search(href) or id_in_path.search(href)
        if match:
            offer_ids.add(match.group(1))

    return {
        "titre": _extract_sale_title(soup, sale_id),
        "offer_ids": sorted(offer_ids),
    }


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Sérialise un DataFrame en fichier Excel (bytes) prêt au téléchargement."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Disponibilites")
    return buffer.getvalue()


def enrich_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute la colonne d'affichage normalisée (ville) à un DataFrame."""
    enriched = df.copy()
    enriched["ville_affichee"] = enriched["ville_depart_label"].fillna(
        enriched["ville_depart"]
    )
    return enriched


def build_sale_dataframe(sale_id: str) -> pd.DataFrame:
    """Récupère et consolide les disponibilités de toutes les offres d'une vente."""
    with st.spinner(f"Scan de la vente {sale_id} pour trouver les offres..."):
        sale_info = fetch_sale_info(sale_id)

    sale_title = sale_info["titre"]
    offer_ids = sale_info["offer_ids"]

    st.title(f"🏖️ {sale_title}")

    if not offer_ids:
        st.warning(f"Aucune offre trouvée sur la page de la vente {sale_id}.")
        return pd.DataFrame()

    st.success(f"{len(offer_ids)} offre(s) détectée(s). Récupération des prix en cours...")
    progress_bar = st.progress(0.0)

    frames: list[pd.DataFrame] = []
    for index, offer_id in enumerate(offer_ids, start=1):
        result = fetch_offer(offer_id)
        availabilities = result.get("disponibilites")
        if "error" not in result and isinstance(availabilities, pd.DataFrame) and not availabilities.empty:
            offer_df = availabilities.copy()
            offer_df.insert(0, "offre_titre", result.get("metadata", {}).get("titre", "-"))
            offer_df.insert(0, "offre_id", offer_id)
            frames.append(offer_df)
        progress_bar.progress(index / len(offer_ids))

    progress_bar.empty()

    if not frames:
        st.error("Aucune disponibilité trouvée parmi les offres de cette vente.")
        return pd.DataFrame()

    consolidated = pd.concat(frames, ignore_index=True)
    st.markdown(
        f"**Offres avec données :** {len(frames)}/{len(offer_ids)} "
        f"| **Total lignes :** {len(consolidated)}"
    )
    return consolidated


def build_single_offer_dataframe(offer_id: str) -> pd.DataFrame:
    """Récupère les disponibilités d'une offre unique."""
    with st.spinner(f"Récupération des données pour l'offre {offer_id}..."):
        result = fetch_offer(offer_id)

    if "error" in result:
        st.title("🏖️ Travel Prices")
        st.error(f"❌ {result['error']}")
        return pd.DataFrame()

    availabilities = result.get("disponibilites", pd.DataFrame())
    metadata = result.get("metadata", {})

    st.title(f"🏖️ {metadata.get('titre') or metadata.get('hotel') or 'Travel Prices'}")

    summary = (
        f"**Hôtel :** {metadata.get('hotel', '-')} | "
        f"**Destination :** {metadata.get('destination', '-')} | "
        f"**Offres :** {result.get('total_offres', 0)}"
    )
    st.markdown(summary)

    return availabilities if isinstance(availabilities, pd.DataFrame) else pd.DataFrame()


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
st.caption("🏖️ Travel Offer Catalog Prices")

query_params = st.query_params
initial_offer_id = query_params.get("offer_id", "")
initial_sale_id = query_params.get("sale_id", "")
default_mode = "Toute une vente" if initial_sale_id else "Une seule offre"

mode = st.radio(
    "Mode d'analyse",
    ["Une seule offre", "Toute une vente"],
    horizontal=True,
    index=0 if default_mode == "Une seule offre" else 1,
)
is_sale_mode = mode == "Toute une vente"

col_input, col_btn = st.columns([3, 1])
with col_input:
    placeholder = "Ex: 605655" if is_sale_mode else "Ex: 450539"
    default_value = initial_sale_id if is_sale_mode else initial_offer_id
    label = "ID de la vente" if is_sale_mode else "ID de l'offre"
    input_value = st.text_input(
        label, value=default_value, placeholder=placeholder, label_visibility="collapsed"
    )
with col_btn:
    analyze_clicked = st.button("Analyser", use_container_width=True, type="primary")

target_id = input_value.strip()

if analyze_clicked and target_id:
    if is_sale_mode:
        st.query_params["sale_id"] = target_id
        st.query_params.pop("offer_id", None)
        fetch_sale_info.clear()
    else:
        st.query_params["offer_id"] = target_id
        st.query_params.pop("sale_id", None)
        fetch_offer.clear()

if not target_id:
    st.title("🏖️ Travel Prices")
    st.info("👈 Saisissez un identifiant, ou passez `?offer_id=123` / `?sale_id=456` dans l'URL.")
    st.stop()

# ---------------------------------------------------------------------------
# Chargement des données selon le mode
# ---------------------------------------------------------------------------
final_df = build_sale_dataframe(target_id) if is_sale_mode else build_single_offer_dataframe(target_id)

if final_df.empty:
    st.stop()

# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
df_view = enrich_display_columns(final_df)

villes = sorted(df_view["ville_affichee"].dropna().unique().tolist())

if is_sale_mode:
    col_f1, col_f2 = st.columns(2)
    selected_villes = col_f1.multiselect("Villes de départ", villes, default=villes)

    offres = sorted(df_view["offre_titre"].dropna().unique().tolist())
    selected_offres = col_f2.multiselect("Offres", offres, default=offres)

    filter_mask = df_view["ville_affichee"].isin(selected_villes) & df_view["offre_titre"].isin(
        selected_offres
    )
else:
    selected_villes = st.multiselect("Villes de départ", villes, default=villes)
    filter_mask = df_view["ville_affichee"].isin(selected_villes)

df_view = df_view.loc[filter_mask].reset_index(drop=True)

columns_to_show = DISPLAY_COLUMNS.copy()
if is_sale_mode:
    columns_to_show = ["offre_id", "offre_titre"] + columns_to_show

# ---------------------------------------------------------------------------
# Affichage : Tableau / Graphique
# ---------------------------------------------------------------------------
tab_table, tab_chart = st.tabs(["Tableau", "Graphique"])

with tab_table:
    display_df = df_view[columns_to_show].rename(columns=DISPLAY_COLUMN_LABELS)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    export_name = f"vente_{target_id}" if is_sale_mode else f"offre_{target_id}"
    col_csv, col_xlsx = st.columns(2)
    col_csv.download_button(
        "📥 Télécharger CSV",
        data=display_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{export_name}.csv",
        use_container_width=True,
    )
    col_xlsx.download_button(
        "📊 Télécharger Excel",
        data=to_excel_bytes(display_df),
        file_name=f"{export_name}.xlsx",
        use_container_width=True,
    )

with tab_chart:
    if df_view.empty:
        st.info("Aucune donnée à afficher pour les filtres sélectionnés.")
    else:
        if is_sale_mode:
            st.caption("Prix moyen par date et par ville sur l'ensemble de la vente.")
            chart_source = (
                df_view.groupby(["date_depart", "ville_affichee"], as_index=False)["prix_actuel"]
                .mean()
            )
        else:
            chart_source = df_view

        chart_source = chart_source.sort_values("date_depart")  # type: ignore[call-overload]
        fig = px.line(
            chart_source,
            x="date_depart",
            y="prix_actuel",
            color="ville_affichee",
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)