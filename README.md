# Dashboard PAARLY vs Prestataire X

Petite appli **Streamlit** pour visualiser la couverture scraping PAARLY vs Prestataire X.

---

## 🚀 Installation (1ʳᵉ fois)

### 1. Vérifier que Python 3.10+ est installé

```bash
python3 --version
```

Si pas installé → [python.org/downloads](https://www.python.org/downloads/)

### 2. Créer un environnement virtuel (recommandé)

Dans le dossier `paarly_dashboard/` :

```bash
python3 -m venv venv
# macOS / Linux :
source venv/bin/activate
# Windows :
venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

---

## ▶️ Lancer l'appli

```bash
streamlit run app.py
```

Ça ouvre automatiquement le navigateur sur `http://localhost:8501`.

Pour arrêter : `Ctrl+C` dans le terminal.

---

## 📁 Ajouter de nouvelles données

### Quotidien — PAARLY (CSV)

Dépose le fichier CSV de la journée dans `data/paarly_csv/` (brut `.csv` ou compressé `.csv.gz`). Format de nom :
```
Competitors_Prices_AAAA_MM_JJ_*.csv
```
Exemple : `Competitors_Prices_2026_05_19_07_00_03.csv`

L'appli détecte automatiquement les nouveaux fichiers et calcule les comptages par (pays × reseller).

### Quotidien — Prestataire X (HTML, à venir)

Dépose le rapport HTML dans `data/prestataire_html/`.  
⚠️ **Le parser HTML n'est pas encore implémenté** — il faut me fournir un exemple de rapport pour que je puisse l'écrire. En attendant, les données X proviennent uniquement de l'Excel de base (jusqu'au 12/05/2026).

### Excel de base

`data/excel_base/meeting_paarly_base.xlsx` — référence historique avec les données X complètes (avril 2 → mai 12). Ne pas le modifier sauf si tu veux rebaser l'historique.

---

## ☁️ Version en ligne (Streamlit Community Cloud)

L'app est déployée depuis le dépôt GitHub privé, fichier principal `app.py`.

**Ajouter des fichiers** : sidebar > *📁 Ajouter un nouveau jour* > upload des CSV PAARLY
et/ou des comparatifs `.xlsx`, puis **Ajouter au dashboard**. Les CSV sont compressés en
`.csv.gz` et chaque ajout est commité dans le dépôt GitHub (sinon le fichier serait perdu
au redémarrage de l'app, le disque de Streamlit Cloud n'étant pas conservé). Un CSV est
refusé si un fichier existe déjà pour la même date.

**Secrets** (Settings > Secrets de l'app), au format TOML :
```toml
GITHUB_TOKEN = "github_pat_..."   # jeton fine-grained, droit Contents: Read and write sur ce dépôt uniquement
GITHUB_REPO = "compte/nom-du-depot"
APP_PASSWORD = "..."              # optionnel : demande un mot de passe à l'ouverture
```

En local, après des ajouts faits en ligne : `git pull` pour récupérer les fichiers.

---

## 🎛️ Les 4 onglets

| Onglet | Ce qu'il montre |
|---|---|
| **📊 Comparatif PAARLY vs X** | Histogramme côte-à-côte pour une date choisie, par (pays × reseller) |
| **🚦 Différentiel vs moy. X** | Tableau coloré + bar chart : déficit PAARLY vs moyenne X 8–12 mai, avec verdict (🟢 bon / 🟠 alarmant / 🔴 catastrophique) |
| **📈 Évolution PAARLY** | Lignes d'évolution depuis le 12/05, vues : global, par pays, par reseller, par couple pays×reseller |
| **🔀 PAARLY vs PAARLY** | Comparaison entre 2 dates quelconques, avec Δ absolu et Δ % |

---

## 🎨 Paliers du verdict

| Couleur | Plage de déficit | Verdict |
|---|---|---|
| 🟢 | ≤ 10 % | bon |
| 🟠 | 10 % < déficit ≤ 50 % | alarmant |
| 🔴 | > 50 % | catastrophique |

`Déficit = 1 − (PAARLY_jour / moyenne_X_8-12mai)`

---

## 📂 Arborescence

```
paarly_dashboard/
├── app.py                    # Appli Streamlit (UI)
├── data_loader.py            # Lecture Excel + CSV + HTML
├── requirements.txt
├── README.md
└── data/
    ├── excel_base/
    │   └── meeting_paarly_base.xlsx
    ├── paarly_csv/           # Déposer les nouveaux CSV PAARLY ici
    └── prestataire_html/     # (à venir) Rapports HTML du prestataire
```

---

## 🆘 Soucis fréquents

**"ModuleNotFoundError"** → tu n'as pas activé le venv ou pas fait `pip install -r requirements.txt`.

**Une nouvelle date n'apparaît pas après avoir ajouté un CSV** → clique sur **🔄 Recharger les données** dans la sidebar, ou redémarre l'appli.

**Date manquante dans le CSV** → vérifie que le nom du fichier contient bien `AAAA_MM_JJ` (le script extrait la date depuis le nom).
