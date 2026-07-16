"""
Travel Offer Catalog Prices
----------------------------
Application Streamlit minimaliste pour analyser les disponibilités 
et les prix d'une offre voyage SRP ou d'une vente complète.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
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

# Récupération des secrets
API_URL_TEMPLATE = st.secrets.get(
    "API_URL", 
    "https://hiddenprod-showroomprive.orchestra-platform.com/ajax/bookingEngine/{offer_id}"
)
SALE_URL_TEMPLATE = st.secrets.get(
    "SALE_URL", 
    "https://hiddenprod-showroomprive.orchestra-platform.com/sale?id={sale_id}"
)

API_USER = st.secrets.get("API_USER", "")
API_PASSWORD = st.secrets.get("API_PASSWORD", "")
AUTH_TUPLE = (API_USER, API_PASSWORD) if API_USER and API_PASSWORD else None

HEADERS = {
    "Accept": "application/json",
    "Accept-Charset": "utf-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ---------------------------------------------------------------------------
# Fonctions de récupération (Mises en cache)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_offer(offer_id: str) -> dict:
    url = API_URL_TEMPLATE.format(offer_id=offer_id)
    try:
        response = requests.get(url, headers=HEADERS, auth=AUTH_TUPLE, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Erreur de connexion (Offre {offer_id}): {e}"}

    response.encoding = "utf-8"
    try:
        return format_availability(response.json())
    except ValueError:
        return {"error": f"Format invalide pour l'offre {offer_id}."}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sale_offers(sale_id: str) -> list[str]:
    """Récupère l'HTML de la vente et extrait tous les identifiants d'offres."""
    url = SALE_URL_TEMPLATE.format(sale_id=sale_id)
    try:
        # On utilise un user-agent standard pour l'HTML
        html_headers = {"User-Agent": HEADERS["User-Agent"]}
        response = requests.get(url, headers=html_headers, auth=AUTH_TUPLE, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur d'accès à la vente : {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    offer_ids = set()
    
    # On cherche tous les liens <a> contenant 'offer'
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "offer" in href.lower():
            # Cherche ?id=XXXXXX
            match_id = re.search(r'id=(\d+)', href)
            if match_id:
                offer_ids.add(match_id.group(1))
            else:
                # Ou cherche un ID composé de 5 à 8 chiffres dans le lien
                match_num = re.search(r'(?:/|-)(\d{5,8})(?:\b|\.|\?|/)', href)
                if match_num:
                    offer_ids.add(match_num.group(1))
                    
    return list(offer_ids)

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Disponibilites")
    return buffer.getvalue()

# ---------------------------------------------------------------------------
# Interface Minimaliste
# ---------------------------------------------------------------------------
st.title("🏖️ Travel Prices")

# Initialisation des paramètres URL
query_params = st.query_params
initial_offer_id = query_params.get("offer_id", "")
initial_sale_id = query_params.get("sale_id", "")
if initial_sale_id:
    initial_mode = "Toute une vente"
else:
    initial_mode = "Une seule offre"

# Choix du mode d'analyse
mode = st.radio(
    "Mode d'analyse", 
    ["Une seule offre", "Toute une vente"], 
    horizontal=True, 
    index=0 if initial_mode == "Une seule offre" else 1
)

target_id = None
analysis_type = "offer"

# Formulaire dynamique selon le mode
col_input, col_btn = st.columns([3, 1])
with col_input:
    if mode == "Une seule offre":
        input_val = st.text_input("ID de l'offre", value=initial_offer_id, placeholder="Ex: 450539", label_visibility="collapsed")
    else:
        input_val = st.text_input("ID de la vente", value=initial_sale_id, placeholder="Ex: 605655", label_visibility="collapsed")

with col_btn:
    analyze_btn = st.button("Analyser", use_container_width=True, type="primary")

# Gestion du clic ou présence dans l'URL
if analyze_btn and input_val:
    target_id = input_val.strip()
    if mode == "Une seule offre":
        st.query_params["offer_id"] = target_id
        st.query_params.pop("sale_id", None)
        fetch_offer.clear()
        analysis_type = "offer"
    else:
        st.query_params["sale_id"] = target_id
        st.query_params.pop("offer_id", None)
        fetch_sale_offers.clear()
        analysis_type = "sale"
elif (initial_offer_id and mode == "Une seule offre") or (initial_sale_id and mode == "Toute une vente"):
    target_id = input_val.strip()
    analysis_type = "offer" if mode == "Une seule offre" else "sale"

if not target_id:
    st.info("👈 Saisissez un identifiant pour démarrer l'analyse.")
    st.stop()

# ---------------------------------------------------------------------------
# Récupération et Consolidation des données
# ---------------------------------------------------------------------------
final_df = pd.DataFrame()
metadata_display = ""

if analysis_type == "offer":
    with st.spinner(f"Récupération des données pour l'offre {target_id}..."):
        result = fetch_offer(target_id)
        if "error" in result:
            st.error(f"❌ {result['error']}")
            st.stop()
        final_df = result["disponibilites"]
        meta = result["metadata"]
        metadata_display = f"**Hôtel:** {meta.get('hotel', '-')} | **Destination:** {meta.get('destination', '-')} | **Offres:** {result['total_offres']}"
        if meta.get("titre"):
            metadata_display += f"\n\n*{meta['titre']}*"

elif analysis_type == "sale":
    with st.spinner(f"Scan de la vente {target_id} pour trouver les offres..."):
        offer_ids = fetch_sale_offers(target_id)
    
    if not offer_ids:
        st.warning(f"Aucune offre trouvée sur la page de la vente {target_id}.")
        st.stop()
        
    st.success(f"{len(offer_ids)} offres détectées. Récupération des prix en cours...")
    
    progress_bar = st.progress(0)
    all_dfs = []
    
    for i, oid in enumerate(offer_ids):
        res = fetch_offer(oid)
        if "error" not in res and not res["disponibilites"].empty:
            df_offer = res["disponibilites"].copy()
            # Ajout des colonnes de consolidation
            df_offer.insert(0, "offre_titre", res["metadata"].get("titre", "-"))
            df_offer.insert(0, "offre_id", oid)
            all_dfs.append(df_offer)
        progress_bar.progress((i + 1) / len(offer_ids))
        
    if not all_dfs:
        st.error("Aucune disponibilité trouvée parmi l'ensemble des offres de la vente.")
        st.stop()
        
    final_df = pd.concat(all_dfs, ignore_index=True)
    metadata_display = f"**Vente ID:** {target_id} | **Offres récupérées:** {len(all_dfs)} sur {len(offer_ids)} | **Total dispo:** {len(final_df)}"

if final_df.empty:
    st.warning("Aucune disponibilité trouvée.")
    st.stop()

st.markdown(metadata_display)

# ---------------------------------------------------------------------------
# Filtres & Affichage
# ---------------------------------------------------------------------------
villes = sorted(final_df["ville_depart_label"].fillna(final_df["ville_depart"]).unique().tolist())
pensions = sorted(final_df["pension_label"].fillna(final_df["pension"]).replace("", pd.NA).dropna().unique().tolist())

col_f1, col_f2 = st.columns(2)
sel_villes = col_f1.multiselect("Villes de départ", villes, default=villes)
sel_pensions = col_f2.multiselect("Pensions", pensions, default=pensions)

df_view = final_df.copy()
df_view["ville_affichee"] = df_view["ville_depart_label"].fillna(df_view["ville_depart"])
df_view["pension_affichee"] = df_view["pension_label"].fillna(df_view["pension"])

mask = (
    df_view["ville_affichee"].isin(sel_villes)
    & (df_view["pension_affichee"].isin(sel_pensions) | df_view["pension_affichee"].eq(""))
)
df_view = df_view[mask]

# Si on est sur une vente, on montre les colonnes spécifiques d'abord
columns_to_show = ["ville_affichee", "date_depart", "prix_actuel", "reduction_pourcentage", "statut"]
if analysis_type == "sale":
    columns_to_show = ["offre_id", "offre_titre"] + columns_to_show

tab1, tab2 = st.tabs(["Tableau", "Graphique"])

with tab1:
    st.dataframe(df_view[columns_to_show], use_container_width=True, hide_index=True)
    
    c1, c2 = st.columns(2)
    export_name = f"vente_{target_id}" if analysis_type == "sale" else f"offre_{target_id}"
    c1.download_button("📥 Télécharger CSV", data=df_view.to_csv(index=False).encode("utf-8-sig"), file_name=f"{export_name}.csv", use_container_width=True)
    c2.download_button("📊 Télécharger Excel", data=to_excel_bytes(df_view), file_name=f"{export_name}.xlsx", use_container_width=True)

with tab2:
    if not df_view.empty:
        # Dans le cas d'une vente, le graphique peut être très chargé, on groupe par date/ville (moyenne du prix) ou on met un filtre supplémentaire
        if analysis_type == "sale":
            st.caption("Aperçu des prix moyens par date et par ville sur l'ensemble de la vente.")
            chart_data = df_view.groupby(["date_depart", "ville_affichee"], as_index=False)["prix_actuel"].mean()
            fig = px.line(chart_data.sort_values("date_depart"), x="date_depart", y="prix_actuel", color="ville_affichee", markers=True)
        else:
            fig = px.line(df_view.sort_values("date_depart"), x="date_depart", y="prix_actuel", color="ville_affichee", markers=True)
            
        st.plotly_chart(fig, use_container_width=True)