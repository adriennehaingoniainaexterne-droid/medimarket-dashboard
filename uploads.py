"""
uploads.py
Ajout de fichiers depuis le dashboard (bouton d'upload de la sidebar) :
  - CSV PAARLY (Competitors_Prices_AAAA_MM_JJ_*.csv) → data/paarly_csv/ (compressé en .csv.gz)
  - Comparatif X vs PAARLY (Comparatif scraping JJ-MM-AAAA.xlsx) → data/comparatif/

En ligne (Streamlit Cloud), le disque est vidé à chaque redémarrage : les
fichiers sont donc aussi commités dans le dépôt GitHub (secrets GITHUB_TOKEN
et GITHUB_REPO). Sans ces secrets (en local), ils sont seulement écrits sur disque.
"""
import base64
import gzip
import io
import re
from pathlib import Path

import pandas as pd
import requests

from data_loader import COMPARATIF_DIR, PAARLY_CSV_DIR, paarly_csv_files

CSV_NAME_RE = re.compile(r'^Competitors_Prices_\d{4}_\d{2}_\d{2}.*\.csv$')
CSV_REQUIRED_COLS = {'product_id', 'reseller', 'country'}
COMPARATIF_REQUIRED_COLS = {'DateDesc', 'Region', 'Reseller', 'X', 'Paarly',
                            'Product Reference ID'}
ROOT_DIR = Path(__file__).parent.resolve()


def prepare(name: str, content: bytes) -> tuple:
    """Vérifie un fichier uploadé. Renvoie (chemin local cible, octets à écrire).
    Lève ValueError avec un message lisible si le fichier n'est pas reconnu."""
    if name.lower().endswith('.csv'):
        if not CSV_NAME_RE.match(name):
            raise ValueError(
                f"{name} : le nom doit être de la forme "
                f"Competitors_Prices_AAAA_MM_JJ_*.csv")
        head = pd.read_csv(io.BytesIO(content), sep=';', encoding='utf-8', nrows=5)
        missing = CSV_REQUIRED_COLS - set(head.columns)
        if missing:
            raise ValueError(f"{name} : colonnes manquantes {sorted(missing)}")
        # un 2e fichier pour la même date doublerait les comptages du jour
        date_str = re.search(r'\d{4}_\d{2}_\d{2}', name).group(0)
        target = PAARLY_CSV_DIR / f'{name}.gz'
        same_day = [f.name for f in paarly_csv_files()
                    if date_str in f.name and f != target]
        if same_day:
            raise ValueError(f"{name} : un fichier existe déjà pour cette date "
                             f"({same_day[0]})")
        return target, gzip.compress(content, mtime=0)

    if name.lower().endswith('.xlsx'):
        if not name.lower().startswith('comparatif scraping'):
            raise ValueError(
                f"{name} : le nom doit commencer par « Comparatif scraping »")
        try:
            head = pd.read_excel(io.BytesIO(content), sheet_name='Export',
                                 engine='openpyxl', nrows=5)
        except ValueError:
            raise ValueError(f"{name} : onglet « Export » introuvable")
        missing = COMPARATIF_REQUIRED_COLS - set(head.columns)
        if missing:
            raise ValueError(f"{name} : colonnes manquantes {sorted(missing)}")
        return COMPARATIF_DIR / name, content

    raise ValueError(f"{name} : seuls les .csv PAARLY et les .xlsx de comparatif sont acceptés")


def save_local(files: list) -> None:
    """files = [(chemin local, octets)]"""
    for path, data in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def commit_to_github(files: list, token: str, repo: str, branch: str = 'main') -> str:
    """Commite tous les fichiers en un seul commit via l'API Git Data de GitHub
    (accepte des fichiers jusqu'à 100 Mo, contrairement à l'API Contents).
    Renvoie le sha du commit."""
    api = f'https://api.github.com/repos/{repo}/git'
    s = requests.Session()
    s.headers.update({'Authorization': f'Bearer {token}',
                      'Accept': 'application/vnd.github+json'})

    def call(method, url, **kw):
        r = s.request(method, url, timeout=60, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {r.status_code} : {r.text[:200]}")
        return r.json()

    head_sha = call('GET', f'{api}/ref/heads/{branch}')['object']['sha']
    base_tree = call('GET', f'{api}/commits/{head_sha}')['tree']['sha']
    tree = []
    for path, data in files:
        blob = call('POST', f'{api}/blobs', json={
            'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
        tree.append({'path': path.resolve().relative_to(ROOT_DIR).as_posix(),
                     'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    new_tree = call('POST', f'{api}/trees', json={'base_tree': base_tree, 'tree': tree})
    names = ', '.join(p.name for p, _ in files)
    commit = call('POST', f'{api}/commits', json={
        'message': f'Ajout depuis le dashboard : {names}',
        'tree': new_tree['sha'], 'parents': [head_sha]})
    call('PATCH', f'{api}/refs/heads/{branch}', json={'sha': commit['sha']})
    return commit['sha']
