# Travel Offer Catalog Prices

Application **Streamlit** permettant d'analyser les disponibilités et les
prix d'une offre voyage SRP (migration de l'ancienne application
Flask + DataTables vers Streamlit, avec un thème sobre et pro en
dégradés de `#267492`).

## Fonctionnalités

- Recherche d'une offre par identifiant
- Cartes de synthèse (hôtel, destination, étoiles, nombre d'offres)
- Filtres dynamiques (ville de départ, statut, pension, période)
- Tableau détaillé interactif avec badges de statut, colonnes formatées
  (prix, réduction, cases à cocher)
- Export CSV et Excel des résultats filtrés
- Graphique d'évolution des prix par ville de départ
- Mise en cache des appels API (5 minutes) pour limiter la charge réseau

## Structure du projet

```
travel_offerCatalogPrices/
├── app.py                 # Application Streamlit (UI)
├── data_formatter.py      # Logique de nettoyage / formatage des données
├── requirements.txt       # Dépendances Python
├── setup_venv.sh          # Script de création du venv (Linux/Mac)
├── setup_venv.bat         # Script de création du venv (Windows)
├── .streamlit/
│   └── config.toml        # Thème (dégradés de #267492)
└── README.md
```

## Installation locale (venv)

### Linux / Mac

```bash
cd travel_offerCatalogPrices
./setup_venv.sh
source .venv/bin/activate
streamlit run app.py
```

### Windows

```bat
cd travel_offerCatalogPrices
setup_venv.bat
.venv\Scripts\activate.bat
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`.

## Déploiement sur Streamlit Community Cloud

1. Créez un dépôt GitHub (public ou privé) et poussez le contenu de ce
   dossier à la racine du dépôt (`app.py` doit être à la racine, ou
   indiquez son chemin lors de la configuration) :

   ```bash
   cd travel_offerCatalogPrices
   git init
   git add .
   git commit -m "Initial commit - Travel Offer Catalog Prices"
   git branch -M main
   git remote add origin https://github.com/<votre-compte>/travel_offerCatalogPrices.git
   git push -u origin main
   ```

2. Rendez-vous sur [share.streamlit.io](https://share.streamlit.io) et
   connectez-vous avec votre compte GitHub.

3. Cliquez sur **New app**, sélectionnez le dépôt, la branche `main`
   et le fichier principal `app.py`.

4. Le fichier `.streamlit/config.toml` (thème) et `requirements.txt`
   (dépendances) sont automatiquement pris en compte par Streamlit
   Cloud, aucune configuration supplémentaire n'est nécessaire.

5. Cliquez sur **Deploy**. L'application sera disponible à une URL du
   type `https://<votre-app>.streamlit.app`.

### Remarque réseau

L'application interroge l'API interne
`https://hiddenprod-showroomprive.orchestra-platform.com`. Assurez-vous
que cette API est accessible publiquement (ou via VPN/allowlist) depuis
l'infrastructure de Streamlit Community Cloud, sinon privilégiez un
déploiement interne (serveur Showroomprive, Docker, etc.) ou la mise en
place d'un accès sécurisé (reverse proxy avec authentification, IP
allowlisting côté API...).

## Personnalisation du thème

Le thème est défini dans `.streamlit/config.toml` et complété par du
CSS embarqué dans `app.py` (variables `PRIMARY`, `PRIMARY_DARK`,
`PRIMARY_LIGHT`, `PRIMARY_PALE`) pour obtenir des dégradés cohérents à
partir de la couleur de marque `#267492`.
