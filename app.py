"""
Travel Offer Catalog Prices
----------------------------
Application Streamlit minimaliste pour analyser les disponibilités 
et les prix d'une offre voyage SRP.
"""
from __future__ import annotations

import io
from datetime import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from data_formatter import format_availability

# ---------------------------------------------------------------------------
# Configuration générale
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Travel Offer Catalog Prices",
    page_icon="🏖️",
    layout="wide",
)

# Récupération des secrets pour le déploiement sécurisé
API_URL_TEMPLATE = st.secrets.get(
    "API_URL", 
    "https://hiddenprod-showroomprive.orchestra-platform.com/ajax/bookingEngine/{offer_id}"
)
API_USER = st.secrets.get("API_USER", "")
API_PASSWORD = st.secrets.get("API_PASSWORD", "")

# ---------------------------------------------------------------------------
# Appel API robuste avec cache et authentification
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_offer(offer_id: str) -> dict:
    url = API_URL_TEMPLATE.format(offer_id=offer_id)
    headers = {
        "Accept": "application/json",
        "Accept-Charset": "utf-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    
    # On prépare le tuple d'authentification s'il est configuré
    auth_tuple = (API_USER, API_PASSWORD) if API_USER and API_PASSWORD else None

    try:
        response = requests.get(url, headers=headers, auth=auth_tuple, timeout=15)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return {"error": "Le serveur met trop de temps à répondre. Veuillez réessayer."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Erreur de connexion à l'API : {e}"}

    response.encoding = "utf-8"
    try:
        data = response.json()
    except ValueError:
        return {"error": "Le format de réponse de l'API est invalide (non-JSON)."}
    
    return format_availability(data)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Disponibilites")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Interface Minimaliste
# ---------------------------------------------------------------------------
st.title("🏖️ Travel Offer Prices")

# Support du paramètre GET `offer_id` (ex: ?offer_id=450539)
query_params = st.query_params
initial_offer_id = query_params.get("offer_id", "")

col_input, col_btn = st.columns([3, 1])
with col_input:
    offer_id_input = st.text_input(
        "ID de l'offre voyage", 
        value=initial_offer_id, 
        placeholder="Ex: 450539",
        label_visibility="collapsed"
    )
with col_btn:
    analyze_btn = st.button("Analyser", use_container_width=True, type="primary")

# Mise à jour des paramètres dans l'URL si on utilise le bouton
if analyze_btn and offer_id_input:
    st.query_params["offer_id"] = offer_id_input.strip()
    active_offer_id = offer_id_input.strip()
    fetch_offer.clear() # Rafraîchissement forcé à la demande
else:
    active_offer_id = offer_id_input.strip()

if not active_offer_id:
    st.info("👈 Saisissez un identifiant d'offre ou passez-le dans l'URL (?offer_id=123) pour démarrer l'analyse.")
    st.stop()


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------
with st.spinner(f"Récupération des données pour {active_offer_id}..."):
    result = fetch_offer(active_offer_id)

if "error" in result:
    st.error(f"❌ {result['error']}")
    st.stop()

metadata = result["metadata"]
df: pd.DataFrame = result["disponibilites"]
total_offres = result["total_offres"]

if df.empty:
    st.warning("Aucune disponibilité trouvée pour cette offre.")
    st.stop()

# En-tête simple (Métadonnées)
st.markdown(f"**Hôtel:** {metadata.get('hotel', '-')} | **Destination:** {metadata.get('destination', '-')} | **Offres:** {total_offres}")
if metadata.get("titre"):
    st.caption(metadata["titre"])


# ---------------------------------------------------------------------------
# Filtres & Affichage (Simplifiés)
# ---------------------------------------------------------------------------
villes = sorted(df["ville_depart_label"].fillna(df["ville_depart"]).unique().tolist())
pensions = sorted(df["pension_label"].fillna(df["pension"]).replace("", pd.NA).dropna().unique().tolist())

col_f1, col_f2 = st.columns(2)
sel_villes = col_f1.multiselect("Villes", villes, default=villes)
sel_pensions = col_f2.multiselect("Pensions", pensions, default=pensions)

df_view = df.copy()
df_view["ville_affichee"] = df_view["ville_depart_label"].fillna(df_view["ville_depart"])
df_view["pension_affichee"] = df_view["pension_label"].fillna(df_view["pension"])

mask = (
    df_view["ville_affichee"].isin(sel_villes)
    & (df_view["pension_affichee"].isin(sel_pensions) | df_view["pension_affichee"].eq(""))
)
df_view = df_view[mask]

tab1, tab2 = st.tabs(["Tableau", "Graphique"])

with tab1:
    st.dataframe(
        df_view[["ville_affichee", "date_depart", "prix_actuel", "reduction_pourcentage", "statut"]],
        use_container_width=True,
        hide_index=True
    )
    
    c1, c2 = st.columns(2)
    c1.download_button(
        "📥 CSV", 
        data=df_view.to_csv(index=False).encode("utf-8-sig"), 
        file_name=f"{active_offer_id}.csv", 
        use_container_width=True
    )
    c2.download_button(
        "📊 Excel", 
        data=to_excel_bytes(df_view), 
        file_name=f"{active_offer_id}.xlsx", 
        use_container_width=True
    )

with tab2:
    if not df_view.empty:
        fig = px.line(
            df_view.sort_values("date_depart"), 
            x="date_depart", y="prix_actuel", color="ville_affichee", markers=True
        )
        st.plotly_chart(fig, use_container_width=True)