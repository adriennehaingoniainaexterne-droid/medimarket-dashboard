"""
data_loader.py
Charge les données depuis :
  - data/excel_base/meeting_paarly_base.xlsx (référence historique)
  - data/paarly_csv/*.csv  (nouveaux CSV quotidiens PAARLY)
  - data/prestataire_html/*.html  (à venir : rapports du prestataire X)
"""
import pandas as pd
from pathlib import Path
import re

DATA_DIR = Path(__file__).parent / 'data'
EXCEL_PATH = DATA_DIR / 'excel_base' / 'meeting_paarly_base.xlsx'
PAARLY_CSV_DIR = DATA_DIR / 'paarly_csv'
PRESTATAIRE_HTML_DIR = DATA_DIR / 'prestataire_html'
COMPARATIF_DIR = DATA_DIR / 'comparatif'
PIC_REFERENCE_PATH = DATA_DIR / 'pic_reference.csv'


def paarly_csv_files() -> list:
    """CSV PAARLY du dossier, bruts (.csv) ou compressés (.csv.gz : format
    versionné dans le dépôt GitHub pour la version en ligne)."""
    if not PAARLY_CSV_DIR.exists():
        return []
    return sorted(list(PAARLY_CSV_DIR.glob('*.csv')) + list(PAARLY_CSV_DIR.glob('*.csv.gz')))


def load_pic_reference() -> pd.DataFrame:
    """
    Pics de référence validés (region, reseller, pic, date_reference).
    Le pic affiché = max(pic de référence, comptes uniques des CSV postérieurs).
    """
    if not PIC_REFERENCE_PATH.exists():
        return pd.DataFrame()
    ref = pd.read_csv(PIC_REFERENCE_PATH, sep=';')
    ref['date_reference'] = pd.to_datetime(ref['date_reference'])
    return ref

COUNTRY_MAP = {'BEL': 'Belux', 'ESP': 'Spain', 'ITA': 'Italy', 'NL': 'Netherlands'}
RESELLER_SPECIAL = {'KRUDIVAT': 'Kruidvat', 'ELCORTEINGLES': 'Elcorteingles'}


def _norm_reseller(r: str) -> str:
    return RESELLER_SPECIAL.get(r, r.title())


def load_excel_base() -> pd.DataFrame:
    """Charge l'onglet Export de l'Excel de base."""
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(
            f"Fichier Excel de base introuvable : {EXCEL_PATH}\n"
            f"Place le fichier 'meeting_paarly_base.xlsx' dans data/excel_base/")
    df = pd.read_excel(EXCEL_PATH, sheet_name='Export', engine='openpyxl')
    df.columns = ['date', 'region', 'reseller', 'requested',
                  'x_count', 'paarly_count', 'x_pct', 'paarly_pct']
    df['date'] = pd.to_datetime(df['date'])
    return df


def parse_paarly_csv(csv_path: Path) -> pd.DataFrame:
    """Lit un CSV PAARLY brut et renvoie les comptages par (region, reseller, date)."""
    m = re.search(r'(\d{4})_(\d{2})_(\d{2})', csv_path.stem)
    if not m:
        return pd.DataFrame()
    file_date = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    df = pd.read_csv(csv_path, sep=';', encoding='utf-8')
    df['region'] = df['country'].map(COUNTRY_MAP)
    df['reseller'] = df['reseller'].apply(_norm_reseller)
    counts = (df.dropna(subset=['region'])
              .groupby(['region', 'reseller']).size().reset_index(name='paarly_count'))
    counts['date'] = file_date
    return counts[['date', 'region', 'reseller', 'paarly_count']]


def load_new_paarly_csvs() -> pd.DataFrame:
    """Lit tous les CSV PAARLY trouvés dans data/paarly_csv/."""
    parts = []
    for csv_file in paarly_csv_files():
        try:
            df_part = parse_paarly_csv(csv_file)
            if not df_part.empty:
                parts.append(df_part)
        except Exception as e:
            print(f"⚠️  Erreur sur {csv_file.name}: {e}")
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def list_available_csv_dates() -> list:
    """Liste les dates pour lesquelles un CSV PAARLY brut est disponible."""
    dates = set()
    for csv_file in paarly_csv_files():
        m = re.search(r'(\d{4})_(\d{2})_(\d{2})', csv_file.stem)
        if m:
            dates.add(pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return sorted(dates)


def compute_unique_paarly_per_date() -> pd.DataFrame:
    """
    Pour chaque CSV PAARLY dans data/paarly_csv/, calcule le compte unique
    (hors doublons) de produits par (région, reseller).
    Compte = nombre de triplets distincts (region, reseller, product_id).
    paarly_unique_suivi = même compte, limité aux product_id encore présents
    dans le CSV le plus récent pour la même région (tous resellers confondus) :
    les produits sortis du catalogue client ne comptent plus.
    Renvoie : DataFrame avec colonnes date, region, reseller, paarly_unique,
    paarly_unique_suivi.
    """
    dated_files = []
    for csv_file in paarly_csv_files():
        m = re.search(r'(\d{4})_(\d{2})_(\d{2})', csv_file.stem)
        if m:
            file_date = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            dated_files.append((file_date, csv_file))
    if not dated_files:
        return pd.DataFrame()
    dated_files.sort()

    def _read(csv_file):
        df = pd.read_csv(csv_file, sep=';', encoding='utf-8', dtype={'product_id': str})
        df['region'] = df['country'].map(COUNTRY_MAP)
        df['reseller_norm'] = df['reseller'].apply(_norm_reseller)
        return df.dropna(subset=['region', 'product_id'])

    # Catalogue actuel = product_id présents dans le dernier CSV, par région
    latest = _read(dated_files[-1][1])
    catalogue = latest[['region', 'product_id']].drop_duplicates()
    catalogue['suivi'] = True

    parts = []
    for file_date, csv_file in dated_files:
        try:
            df = _read(csv_file).merge(catalogue, on=['region', 'product_id'], how='left')
            grp = df.groupby(['region', 'reseller_norm'])
            uniq = grp['product_id'].nunique().reset_index(name='paarly_unique')
            suivi = (df[df['suivi'].fillna(False).astype(bool)]
                     .groupby(['region', 'reseller_norm'])['product_id'].nunique()
                     .reset_index(name='paarly_unique_suivi'))
            uniq = (uniq.merge(suivi, on=['region', 'reseller_norm'], how='left')
                    .rename(columns={'reseller_norm': 'reseller'}))
            uniq['paarly_unique_suivi'] = uniq['paarly_unique_suivi'].fillna(0)
            uniq['date'] = file_date
            parts.append(uniq[['date', 'region', 'reseller', 'paarly_unique',
                               'paarly_unique_suivi']])
        except Exception as e:
            print(f"⚠️  Erreur sur {csv_file.name}: {e}")
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def load_raw_paarly_csv(date: pd.Timestamp) -> pd.DataFrame:
    """
    Charge le CSV brut pour une date donnée (ligne par ligne).
    Renvoie un DataFrame vide si pas de CSV trouvé pour cette date.
    Colonnes ajoutées : 'region' (depuis country) et 'reseller_norm'.
    """
    date_str = f"{date.year:04d}_{date.month:02d}_{date.day:02d}"
    for csv_file in [f for f in paarly_csv_files() if date_str in f.name]:
        df = pd.read_csv(csv_file, sep=';', encoding='utf-8')
        df['region'] = df['country'].map(COUNTRY_MAP)
        df['reseller_norm'] = df['reseller'].apply(_norm_reseller)
        df['date'] = date
        return df
    return pd.DataFrame()


def parse_prestataire_html(html_path: Path) -> pd.DataFrame:
    """Stub — à implémenter quand un exemple de rapport HTML sera fourni."""
    return pd.DataFrame()


def load_new_prestataire_htmls() -> pd.DataFrame:
    if not PRESTATAIRE_HTML_DIR.exists():
        return pd.DataFrame()
    parts = []
    for html_file in sorted(PRESTATAIRE_HTML_DIR.glob('*.html')):
        try:
            df_part = parse_prestataire_html(html_file)
            if not df_part.empty:
                parts.append(df_part)
        except Exception as e:
            print(f"⚠️  Erreur sur {html_file.name}: {e}")
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def parse_comparatif(xlsx_path: Path) -> pd.DataFrame:
    """
    Lit un fichier « Comparatif scraping » (onglet Export : une ligne par produit
    demandé × reseller, colonnes X / Paarly = 'x' si trouvé).
    Renvoie les comptages par (date, region, reseller).
    """
    df = pd.read_excel(xlsx_path, sheet_name='Export', engine='openpyxl')
    df['date'] = pd.to_datetime(df['DateDesc']).dt.normalize()
    df['x_found'] = df['X'].astype(str).str.strip().str.lower().eq('x')
    df['paarly_found'] = df['Paarly'].astype(str).str.strip().str.lower().eq('x')
    agg = (df.groupby(['date', 'Region', 'Reseller'])
           .agg(requested=('Product Reference ID', 'nunique'),
                x_count=('x_found', 'sum'),
                paarly_count=('paarly_found', 'sum'))
           .reset_index()
           .rename(columns={'Region': 'region', 'Reseller': 'reseller'}))
    return agg


def load_comparatifs() -> pd.DataFrame:
    """Lit tous les fichiers de comparatif déposés dans data/comparatif/."""
    if not COMPARATIF_DIR.exists():
        return pd.DataFrame()
    parts = []
    for xlsx_file in sorted(COMPARATIF_DIR.glob('*.xlsx')):
        if xlsx_file.name.startswith('~$'):  # fichier verrou Excel
            continue
        try:
            parts.append(parse_comparatif(xlsx_file))
        except Exception as e:
            print(f"⚠️  Erreur sur {xlsx_file.name}: {e}")
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def load_data() -> pd.DataFrame:
    """Charge et fusionne toutes les sources (agrégées par jour × pays × reseller)."""
    base = load_excel_base()

    # Comparatifs X vs PAARLY : remplacent la ligne du jour si elle existe, sinon l'ajoutent
    comp = load_comparatifs()
    if not comp.empty:
        comp['x_pct'] = comp['x_count'] / comp['requested']
        comp['paarly_pct'] = comp['paarly_count'] / comp['requested']
        keys = ['date', 'region', 'reseller']
        base = (base.merge(comp[keys], on=keys, how='left', indicator=True)
                .query("_merge == 'left_only'").drop(columns='_merge'))
        base = pd.concat([base, comp[base.columns]], ignore_index=True)

    new_paarly = load_new_paarly_csvs()
    if not new_paarly.empty:
        existing_dates = set(base['date'].unique())
        new_dates_df = new_paarly[~new_paarly['date'].isin(existing_dates)]
        if not new_dates_df.empty:
            latest_req = (base.sort_values('date')
                          .groupby(['region', 'reseller'])['requested']
                          .last().reset_index())
            new_rows = new_dates_df.merge(latest_req, on=['region', 'reseller'], how='left')
            new_rows['x_count'] = pd.NA
            new_rows['x_pct'] = pd.NA
            new_rows['paarly_pct'] = new_rows['paarly_count'] / new_rows['requested']
            base = pd.concat([base, new_rows[base.columns]], ignore_index=True)

    new_x = load_new_prestataire_htmls()
    if not new_x.empty:
        for _, row in new_x.iterrows():
            mask = ((base['date'] == row['date']) &
                    (base['region'] == row['region']) &
                    (base['reseller'] == row['reseller']))
            base.loc[mask, 'x_count'] = row['x_count']
            base.loc[mask, 'x_pct'] = (
                row['x_count'] / base.loc[mask, 'requested']).where(
                base.loc[mask, 'requested'] > 0)

    return base.sort_values(['date', 'region', 'reseller']).reset_index(drop=True)


if __name__ == '__main__':
    df = load_data()
    print(f"Lignes : {len(df)}")
    print(f"Période : {df['date'].min().strftime('%d/%m/%Y')} → {df['date'].max().strftime('%d/%m/%Y')}")
    dates_csv = list_available_csv_dates()
    print(f"CSV bruts dispos : {[d.strftime('%Y-%m-%d') for d in dates_csv]}")
