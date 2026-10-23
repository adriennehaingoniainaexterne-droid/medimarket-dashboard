"""
app.py — Dashboard PAARLY vs Prestataire X
Lance avec :  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from data_loader import (load_data, list_available_csv_dates,
                         load_raw_paarly_csv, compute_unique_paarly_per_date,
                         load_pic_reference)
import hmac
import uploads

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="PAARLY vs Prestataire X",
    page_icon="📊",
    layout="wide"
)

X_REF_START = pd.Timestamp('2026-05-08')
X_REF_END = pd.Timestamp('2026-05-12')
REF_DATE = pd.Timestamp('2026-05-12')

# Concurrents non suivis par PAARLY — exclus de toutes les stats
EXCLUDED_RESELLERS = {'Drmax', 'DRMAX', 'drmax'}


def classify_ecart(ecart):
    """Écart = (PAARLY / moy_X) - 1. Positif = PAARLY au-dessus, négatif = en-dessous."""
    if pd.isna(ecart):
        return ('N/A', '⚪', '#9ca3af')
    if ecart >= -0.10:  # PAARLY au plus 10% sous X (ou au-dessus)
        return ('bon', '🟢', '#22c55e')
    elif ecart >= -0.50:  # PAARLY entre -50% et -10% sous X
        return ('alarmant', '🟠', '#f59e0b')
    else:  # PAARLY à plus de 50% sous X
        return ('catastrophique', '🔴', '#dc2626')


def fmt_int(x):
    if pd.isna(x):
        return "—"
    return f"{int(x):,}".replace(",", " ")


def fmt_pct(x, signed=False):
    if pd.isna(x) or x in (float('inf'), float('-inf')):
        return "—"
    return f"{x:+.0%}" if signed else f"{x:.0%}"


def country_reseller_filters(df, key_prefix):
    """Renvoie (selected_region, selected_resellers) avec UI Streamlit."""
    col_a, col_b = st.columns([1, 2])
    regions = ['Tous'] + sorted(df['region'].dropna().unique().tolist())
    sel_region = col_a.selectbox("Pays", regions, key=f'{key_prefix}_region')
    if sel_region == 'Tous':
        avail = sorted(df['reseller'].dropna().unique().tolist())
    else:
        avail = sorted(df[df['region'] == sel_region]['reseller'].dropna().unique().tolist())
    sel_resellers = col_b.multiselect(
        "Reseller(s)", avail, default=avail, key=f'{key_prefix}_res')
    return sel_region, sel_resellers


def apply_filters(df, region, resellers):
    out = df.copy()
    if region != 'Tous':
        out = out[out['region'] == region]
    out = out[out['reseller'].isin(resellers)]
    return out


def secret(key, default=''):
    """Secret Streamlit Cloud ; '' en local sans .streamlit/secrets.toml."""
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


# ============================================================
# ACCÈS — mot de passe si APP_PASSWORD est défini dans les secrets
# ============================================================
_app_password = secret('APP_PASSWORD')
if _app_password and not st.session_state.get('auth_ok'):
    st.title("📊 PAARLY vs Prestataire X")
    pwd = st.text_input("Mot de passe", type="password")
    if pwd:
        if hmac.compare_digest(pwd, _app_password):
            st.session_state['auth_ok'] = True
            st.rerun()
        st.error("Mot de passe incorrect")
    st.stop()


# ============================================================
# DATA
# ============================================================
@st.cache_data(ttl=60)
def get_data():
    return load_data()


df = get_data()

# Exclusion des concurrents non suivis par PAARLY (cf. EXCLUDED_RESELLERS)
df = df[~df['reseller'].isin(EXCLUDED_RESELLERS)].reset_index(drop=True)

df_x_ref = df[(df['date'] >= X_REF_START) & (df['date'] <= X_REF_END)].dropna(subset=['x_count'])
x_avg = (df_x_ref.groupby(['region', 'reseller'])['x_count']
         .mean().reset_index().rename(columns={'x_count': 'x_avg_ref'}))

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("🎛️ Paramètres")
st.sidebar.markdown(
    f"**Période chargée**\n"
    f"{df['date'].min().strftime('%d/%m/%Y')} → "
    f"{df['date'].max().strftime('%d/%m/%Y')}"
)
st.sidebar.markdown(
    f"**Référence X**  \n{X_REF_START.strftime('%d/%m')} → {X_REF_END.strftime('%d/%m/%Y')}"
)
st.sidebar.markdown("---")
with st.sidebar.expander("📁 Ajouter un nouveau jour"):
    st.markdown(
        "- CSV PAARLY (`Competitors_Prices_AAAA_MM_JJ_*.csv`)\n"
        "- Comparatif X vs PAARLY (`Comparatif scraping JJ-MM-AAAA.xlsx`, onglet Export)"
    )
    uploaded = st.file_uploader("Fichiers à ajouter", type=['csv', 'xlsx'],
                                accept_multiple_files=True,
                                key=f"uploader_{st.session_state.get('upload_n', 0)}")
    if uploaded and st.button("Ajouter au dashboard", use_container_width=True):
        prepared = []
        for f in uploaded:
            try:
                prepared.append(uploads.prepare(f.name, f.getvalue()))
            except Exception as e:
                st.error(str(e))
        if prepared:
            uploads.save_local(prepared)
            names = ', '.join(p.name for p, _ in prepared)
            gh_token, gh_repo = secret('GITHUB_TOKEN'), secret('GITHUB_REPO')
            try:
                if gh_token and gh_repo:
                    with st.spinner("Enregistrement dans GitHub…"):
                        uploads.commit_to_github(prepared, gh_token, gh_repo)
                st.session_state['upload_msg'] = f"Ajouté : {names}"
                st.session_state['upload_n'] = st.session_state.get('upload_n', 0) + 1
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Ajouté pour cette session seulement, pas enregistré dans "
                         f"GitHub (perdu au prochain redémarrage) : {e}")
                st.cache_data.clear()
    if st.session_state.get('upload_msg'):
        st.success(st.session_state.pop('upload_msg'))
if st.sidebar.button("🔄 Recharger les données"):
    st.cache_data.clear()
    st.rerun()

# ============================================================
# TITRE
# ============================================================
st.title("📊 PAARLY vs Prestataire X — Couverture scraping")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Comparatif PAARLY vs X (jour)",
    "🚦 Différentiel vs moyenne X",
    "📈 Évolution PAARLY depuis le 12/05",
    "🔀 PAARLY vs PAARLY (entre dates)",
    "🔁 Doublons d'IDs PAARLY",
    "🚨 Valeurs manquantes (#N/A)",
])

# ============================================================
# TAB 1 — Comparatif jour par jour
# ============================================================
with tab1:
    st.header("Comparatif PAARLY vs Prestataire X")
    all_dates = sorted(df['date'].unique())
    sel_date = st.select_slider(
        "Date",
        options=all_dates,
        value=all_dates[-1],
        format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
        key='t1_date',
    )

    # Calcul du pic RÉEL (hors doublons) par (region, reseller)
    # basé sur les CSV bruts → compte distinct de (region, reseller, product_id)
    df_unique = compute_unique_paarly_per_date()
    has_unique_data = not df_unique.empty

    if has_unique_data:
        peak_paarly = (df_unique.groupby(['region', 'reseller'])['paarly_unique']
                       .max().reset_index()
                       .rename(columns={'paarly_unique': 'paarly_peak'}))
        idx_max = df_unique.groupby(['region', 'reseller'])['paarly_unique'].idxmax()
        peak_dates = (df_unique.loc[idx_max, ['region', 'reseller', 'date']]
                      .rename(columns={'date': 'peak_date'}))
        peak_paarly = peak_paarly.merge(peak_dates, on=['region', 'reseller'], how='left')

        # Pics de référence validés (data/pic_reference.csv) : ils remplacent le calcul
        pic_ref = load_pic_reference()
        if not pic_ref.empty:
            ref_peak = pic_ref.rename(columns={'pic': 'paarly_peak',
                                               'date_reference': 'peak_date'})
            peak_paarly = pd.concat([
                peak_paarly.merge(pic_ref[['region', 'reseller']],
                                  on=['region', 'reseller'], how='left', indicator=True)
                .query("_merge == 'left_only'").drop(columns='_merge'),
                ref_peak[['region', 'reseller', 'paarly_peak', 'peak_date']],
            ], ignore_index=True)
    else:
        # Fallback : pic basé sur paarly_count (peut inclure des doublons)
        peak_paarly = (df.groupby(['region', 'reseller'])['paarly_count']
                       .max().reset_index()
                       .rename(columns={'paarly_count': 'paarly_peak'}))
        idx_max = df.dropna(subset=['paarly_count']).groupby(
            ['region', 'reseller'])['paarly_count'].idxmax()
        peak_dates = (df.loc[idx_max, ['region', 'reseller', 'date']]
                      .rename(columns={'date': 'peak_date'}))
        peak_paarly = peak_paarly.merge(peak_dates, on=['region', 'reseller'], how='left')

    # Toutes les combos (region, reseller) jamais observées dans l'historique
    all_combos = (df[['region', 'reseller']].drop_duplicates()
                  .sort_values(['region', 'reseller']))

    # Données du jour sélectionné (peut ne pas couvrir toutes les combos)
    day_data = df[df['date'] == sel_date]

    # On part de all_combos pour ne perdre aucun concurrent même s'il a 0 ligne ce jour
    df_day = (all_combos.merge(day_data, on=['region', 'reseller'], how='left')
              .merge(x_avg, on=['region', 'reseller'], how='left')
              .merge(peak_paarly, on=['region', 'reseller'], how='left')
              .sort_values(['region', 'reseller']))

    # Marque les concurrents absents ce jour (paarly_count manquant après le left-join)
    df_day['absent_jour'] = df_day['paarly_count'].isna()
    df_day['paarly_count'] = df_day['paarly_count'].fillna(0)

    # Remplacer paarly_count du jour par paarly_unique si dispo (CSV brut)
    if has_unique_data:
        day_unique = df_unique[df_unique['date'] == sel_date][
            ['region', 'reseller', 'paarly_unique']]
        df_day = df_day.merge(day_unique, on=['region', 'reseller'], how='left')
        # Si on a une valeur unique pour ce jour, l'utiliser ; sinon garder paarly_count (0 si absent)
        df_day['paarly_count'] = df_day['paarly_unique'].fillna(df_day['paarly_count'])
        df_day = df_day.drop(columns=['paarly_unique'])

    df_day['combo'] = df_day['region'] + ' / ' + df_day['reseller']
    df_day['delta_vs_peak'] = ((df_day['paarly_peak'] - df_day['paarly_count'])
                               .fillna(0).clip(lower=0))
    df_day['pct_of_peak'] = df_day['paarly_count'] / df_day['paarly_peak']

    # Si X manquant pour ce jour → dernier relevé X connu avant cette date,
    # à défaut moy. X 8-12 mai
    x_hist = df[df['x_count'].notna() & (df['date'] <= sel_date)].sort_values('date')
    x_last = (x_hist.groupby(['region', 'reseller'])[['x_count', 'date']].last()
              .reset_index()
              .rename(columns={'x_count': 'x_last', 'date': 'x_last_date'}))
    df_day = df_day.merge(x_last, on=['region', 'reseller'], how='left')
    df_day['x_fallback'] = df_day['x_count'].isna() & (
        df_day['x_last'].notna() | df_day['x_avg_ref'].notna())
    df_day['x_effective'] = (df_day['x_count'].fillna(df_day['x_last'])
                             .fillna(df_day['x_avg_ref']))
    df_day['source_x'] = 'Réel'
    df_day.loc[df_day['x_fallback'] & df_day['x_last'].notna(), 'source_x'] = (
        'Dernier relevé X du ' + df_day['x_last_date'].dt.strftime('%d/%m/%Y'))
    df_day.loc[df_day['x_fallback'] & df_day['x_last'].isna(), 'source_x'] = 'Moy. 8-12 mai'

    n_fb = int(df_day['x_fallback'].sum())
    if n_fb > 0:
        sources = ', '.join(sorted(df_day.loc[df_day['x_fallback'], 'source_x'].unique()))
        st.info(
            f"ℹ️ Pas de relevé prestataire X à cette date pour **{n_fb}** "
            f"couple{'s' if n_fb > 1 else ''} pays/reseller — affichage : "
            f"**{sources}** (barres orange clair)."
        )

    # Alerte sur les concurrents absents ce jour
    n_absent = int(df_day['absent_jour'].sum())
    if n_absent > 0:
        absent_list = df_day[df_day['absent_jour']]['combo'].tolist()
        st.error(
            f"❌ **{n_absent} concurrent(s) absent(s)** dans les données du jour : "
            f"{', '.join(absent_list)}. Affichés à 0 ligne avec un marqueur ❌ "
            f"dans le graphe pour comparaison avec le pic et X.")

    # Alerte sur les baisses notables vs pic réel
    drops = df_day[df_day['delta_vs_peak'] > 0].copy()
    if not drops.empty:
        n_drop = len(drops)
        big_drops = drops[drops['pct_of_peak'] < 0.80]
        if not big_drops.empty:
            st.warning(
                f"⚠️ **{len(big_drops)} couple(s)** sous 80 % du pic réel "
                f"(sur {n_drop} en baisse). Voir les segments rouges sur le graphe.")
    if has_unique_data:
        st.caption(
            "📊 Pic réel = pic de référence validé du 23/09/2026 (`data/pic_reference.csv`) ; "
            "à défaut, nombre maximum de `product_id` uniques (hors doublons) "
            "observé sur (région, reseller) parmi les CSV bruts disponibles. "
            "Pour le jour sélectionné, la barre bleue affiche aussi le compte unique "
            "si un CSV brut existe pour cette date.")
    else:
        st.caption(
            "⚠️ Aucun CSV brut détecté — le pic est calculé sur `paarly_count` "
            "(peut inclure des doublons). Dépose des CSV dans `data/paarly_csv/` "
            "pour avoir un pic réel hors doublons.")

    # Marquage visuel : orange foncé = réel, orange clair = moyenne fallback
    x_colors = ['#fdba74' if fb else '#f97316' for fb in df_day['x_fallback']]
    x_hover = df_day['source_x'].apply(
        lambda s: 'Donnée X réelle' if s == 'Réel' else f'{s} (X manquant ce jour)').tolist()

    fig = go.Figure()

    # PAARLY (bleu) — valeur actuelle
    fig.add_trace(go.Bar(
        name='PAARLY', x=df_day['combo'], y=df_day['paarly_count'],
        marker_color='#3b82f6', offsetgroup='paarly',
        text=df_day['paarly_count'].apply(fmt_int),
        textposition='inside', insidetextanchor='middle',
        textfont=dict(color='white'),
        hovertemplate='%{x}<br>PAARLY : %{y}<extra></extra>'))

    # Manquant vs pic (rouge) — empilé au-dessus de la barre bleue
    delta_labels = df_day.apply(
        lambda r: (("❌ " if r.get('absent_jour', False) else "") +
                   f"-{fmt_int(r['delta_vs_peak'])} "
                   f"({fmt_pct(r['pct_of_peak'] - 1, signed=True)})")
        if r['delta_vs_peak'] > 0 else '',
        axis=1)
    peak_dates_str = df_day['peak_date'].apply(
        lambda d: pd.Timestamp(d).strftime('%d/%m/%Y') if pd.notna(d) else '—')
    fig.add_trace(go.Bar(
        name='Manquant vs pic réel', x=df_day['combo'],
        y=df_day['delta_vs_peak'], base=df_day['paarly_count'],
        marker_color='#dc2626', offsetgroup='paarly',
        text=delta_labels, textposition='outside',
        customdata=peak_dates_str,
        hovertemplate=('%{x}<br>'
                       'Manquant vs pic réel : %{y}<br>'
                       'Pic réel atteint le : %{customdata}<extra></extra>')))

    # Prestataire X (orange) — colonne séparée à côté
    fig.add_trace(go.Bar(
        name='Prestataire X', x=df_day['combo'], y=df_day['x_effective'],
        marker_color=x_colors, offsetgroup='x',
        text=df_day['x_effective'].apply(fmt_int),
        textposition='outside',
        customdata=x_hover,
        hovertemplate='%{x}<br>X : %{y}<br>(%{customdata})<extra></extra>'))

    fig.update_layout(
        barmode='group', xaxis_tickangle=-45, height=620,
        title=f"Nombre de produits scrapés — {pd.Timestamp(sel_date).strftime('%d/%m/%Y')}",
        yaxis_title="Nombre de produits", legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📋 Voir les données"):
        disp = df_day[['region', 'reseller', 'paarly_count', 'paarly_peak',
                       'peak_date', 'delta_vs_peak', 'pct_of_peak',
                       'x_count', 'x_effective', 'source_x', 'requested',
                       'absent_jour']].copy()
        disp['peak_date'] = disp['peak_date'].apply(
            lambda d: pd.Timestamp(d).strftime('%d/%m/%Y') if pd.notna(d) else '—')
        disp['statut'] = disp['absent_jour'].apply(lambda a: '❌ Absent' if a else 'OK')
        disp = disp[['region', 'reseller', 'statut', 'paarly_count', 'paarly_peak',
                     'peak_date', 'delta_vs_peak', 'pct_of_peak',
                     'x_count', 'x_effective', 'source_x', 'requested']]
        disp.columns = ['Pays', 'Reseller', 'Statut', 'PAARLY', 'Pic réel', 'Date du pic',
                        'Δ vs pic réel', '% du pic réel',
                        'X (réel)', 'X (utilisé)', 'Source X', '# Requested']
        # Formater % du pic
        disp['% du pic réel'] = disp['% du pic réel'].apply(
            lambda x: f"{x*100:.1f} %" if pd.notna(x) else '—')
        st.dataframe(disp, use_container_width=True, hide_index=True)

# ============================================================
# TAB 2 — Différentiel vs moyenne X 8-12 mai (avec filtres)
# ============================================================
with tab2:
    st.header("Différentiel PAARLY vs moyenne X (08–12/05/2026)")
    st.markdown("""
**Formule** : `Écart = (PAARLY_jour / moyenne_X_8-12mai) − 1`

Convention : **+ = PAARLY au-dessus de la moyenne X**, **− = en-dessous**.

| | Plage | Verdict |
|---|---|---|
| 🟢 | Écart ≥ −10 % | bon |
| 🟠 | −50 % ≤ Écart < −10 % | alarmant |
| 🔴 | Écart < −50 % | catastrophique |
""")

    # ⬇️ Filtres pays / reseller
    sel_region_t2, sel_resellers_t2 = country_reseller_filters(df, 't2')

    dates_post_12 = sorted([d for d in df['date'].unique() if pd.Timestamp(d) >= REF_DATE])
    sel_d2 = st.select_slider(
        "Date à évaluer",
        options=dates_post_12,
        value=dates_post_12[-1],
        format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
        key='t2_date',
    )

    df_eval = df[df['date'] == sel_d2].merge(x_avg, on=['region', 'reseller'], how='left')
    df_eval = apply_filters(df_eval, sel_region_t2, sel_resellers_t2)

    if df_eval.empty:
        st.warning("Aucun couple Pays/Reseller sélectionné.")
    else:
        df_eval['ecart'] = (df_eval['paarly_count'] / df_eval['x_avg_ref']) - 1
        df_eval[['verdict', 'emoji', 'color']] = df_eval['ecart'].apply(
            lambda x: pd.Series(classify_ecart(x)))

        counts = df_eval['verdict'].value_counts().to_dict()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🟢 Bon", counts.get('bon', 0))
        c2.metric("🟠 Alarmant", counts.get('alarmant', 0))
        c3.metric("🔴 Catastrophique", counts.get('catastrophique', 0))
        c4.metric("⚪ N/A", counts.get('N/A', 0))

        disp = df_eval[['emoji', 'region', 'reseller', 'paarly_count', 'x_avg_ref',
                        'ecart', 'verdict']].copy()
        disp.columns = ['', 'Pays', 'Reseller', 'PAARLY', 'Moy. X (8-12)',
                        'Écart', 'Verdict']
        disp['PAARLY'] = disp['PAARLY'].apply(fmt_int)
        disp['Moy. X (8-12)'] = disp['Moy. X (8-12)'].apply(fmt_int)
        disp['Écart'] = df_eval['ecart'].apply(lambda x: fmt_pct(x, signed=True))

        def _row_style(row):
            col = df_eval.loc[row.name, 'color']
            return [f'background-color: {col}33;' for _ in row]

        st.dataframe(disp.style.apply(_row_style, axis=1),
                     use_container_width=True, hide_index=True)

        df_viz = df_eval.dropna(subset=['ecart']).copy()
        df_viz['combo'] = df_viz['region'] + ' / ' + df_viz['reseller']
        df_viz = df_viz.sort_values('ecart', ascending=False)  # best en haut
        if not df_viz.empty:
            fig2 = go.Figure(go.Bar(
                x=df_viz['ecart'] * 100,
                y=df_viz['combo'],
                orientation='h',
                marker_color=df_viz['color'],
                text=[fmt_pct(d, signed=True) for d in df_viz['ecart']],
                textposition='outside',
            ))
            fig2.update_layout(
                title=f"Écart PAARLY vs moyenne X — {pd.Timestamp(sel_d2).strftime('%d/%m/%Y')}",
                xaxis_title="Écart (%)", yaxis_title="", height=max(300, 40 * len(df_viz)))
            fig2.add_vline(x=-10, line_dash='dash', line_color='#22c55e',
                           annotation_text='−10 %', annotation_position='top')
            fig2.add_vline(x=-50, line_dash='dash', line_color='#dc2626',
                           annotation_text='−50 %', annotation_position='top')
            fig2.add_vline(x=0, line_dash='dot', line_color='#475569')
            st.plotly_chart(fig2, use_container_width=True)

# ============================================================
# TAB 3 — Évolution PAARLY depuis le 12/05 (avec % d'évolution)
# ============================================================
with tab3:
    st.header("Évolution PAARLY depuis le 12/05/2026")
    view = st.radio(
        "Vue :",
        ["Global", "Par pays", "Par fournisseur (reseller)", "Par pays × fournisseur"],
        horizontal=True, key='t3_view')

    df_post = df[df['date'] >= REF_DATE].copy()

    def _pct_chart(agg, value_col, group_col=None, title=""):
        """Construit un line chart d'évolution en % vs 12/05."""
        agg = agg.copy()
        if group_col is None:
            ref_rows = agg[agg['date'] == REF_DATE]
            if ref_rows.empty:
                return None
            ref_val = ref_rows[value_col].iloc[0]
            if not ref_val:
                return None
            agg['pct'] = (agg[value_col] - ref_val) / ref_val
            fig = px.line(agg, x='date', y='pct', markers=True,
                          labels={'pct': '% vs 12/05', 'date': 'Date'},
                          title=title)
        else:
            refs = agg[agg['date'] == REF_DATE].set_index(group_col)[value_col].to_dict()

            def _calc(row):
                rv = refs.get(row[group_col])
                if not rv:
                    return None
                return (row[value_col] - rv) / rv

            agg['pct'] = agg.apply(_calc, axis=1)
            fig = px.line(agg, x='date', y='pct', color=group_col, markers=True,
                          labels={'pct': '% vs 12/05', 'date': 'Date'},
                          title=title)
        fig.update_yaxes(tickformat='+.1%')
        fig.add_hline(y=0, line_dash='dash', line_color='gray')
        return fig

    if view == "Global":
        agg = df_post.groupby('date')['paarly_count'].sum().reset_index()
        fig = px.line(agg, x='date', y='paarly_count', markers=True,
                      labels={'paarly_count': 'Total produits', 'date': 'Date'},
                      title="Évolution globale — Total tous fournisseurs")
        ref_val = agg[agg['date'] == REF_DATE]['paarly_count'].iloc[0]
        fig.add_hline(y=ref_val, line_dash='dash', line_color='gray',
                      annotation_text=f"Réf. 12/05 = {fmt_int(ref_val)}",
                      annotation_position='top right')
        st.plotly_chart(fig, use_container_width=True)

        fig_pct = _pct_chart(agg, 'paarly_count', None,
                             "Évolution en % vs 12/05")
        if fig_pct is not None:
            st.plotly_chart(fig_pct, use_container_width=True)

        agg['delta_pct'] = (agg['paarly_count'] - ref_val) / ref_val
        disp = agg[['date', 'paarly_count', 'delta_pct']].copy()
        disp.columns = ['Date', 'Total PAARLY', 'Δ % vs 12/05']
        disp['Date'] = disp['Date'].apply(lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'))
        disp['Total PAARLY'] = disp['Total PAARLY'].apply(fmt_int)
        disp['Δ % vs 12/05'] = agg['delta_pct'].apply(lambda x: fmt_pct(x, signed=True))
        st.dataframe(disp, use_container_width=True, hide_index=True)

    elif view == "Par pays":
        agg = df_post.groupby(['date', 'region'])['paarly_count'].sum().reset_index()
        fig = px.line(agg, x='date', y='paarly_count', color='region', markers=True,
                      labels={'paarly_count': 'Produits', 'date': 'Date', 'region': 'Pays'},
                      title="Évolution par pays")
        st.plotly_chart(fig, use_container_width=True)

        fig_pct = _pct_chart(agg, 'paarly_count', 'region',
                             "Évolution en % vs 12/05 — par pays")
        if fig_pct is not None:
            st.plotly_chart(fig_pct, use_container_width=True)

    elif view == "Par fournisseur (reseller)":
        agg = df_post.groupby(['date', 'reseller'])['paarly_count'].sum().reset_index()
        fig = px.line(agg, x='date', y='paarly_count', color='reseller', markers=True,
                      labels={'paarly_count': 'Produits', 'date': 'Date', 'reseller': 'Reseller'},
                      title="Évolution par reseller")
        st.plotly_chart(fig, use_container_width=True)

        fig_pct = _pct_chart(agg, 'paarly_count', 'reseller',
                             "Évolution en % vs 12/05 — par reseller")
        if fig_pct is not None:
            st.plotly_chart(fig_pct, use_container_width=True)

    else:  # Par pays × fournisseur
        col_a, col_b = st.columns(2)
        regions = ['Tous'] + sorted(df_post['region'].dropna().unique().tolist())
        sel_region = col_a.selectbox("Pays", regions, key='t3_region')
        if sel_region != 'Tous':
            avail = sorted(df_post[df_post['region'] == sel_region]['reseller'].unique())
        else:
            avail = sorted(df_post['reseller'].dropna().unique())
        sel_resellers = col_b.multiselect("Reseller(s)", avail, default=avail, key='t3_res')

        df_filt = df_post.copy()
        if sel_region != 'Tous':
            df_filt = df_filt[df_filt['region'] == sel_region]
        df_filt = df_filt[df_filt['reseller'].isin(sel_resellers)]
        df_filt['combo'] = df_filt['region'] + ' / ' + df_filt['reseller']

        fig = px.line(df_filt, x='date', y='paarly_count', color='combo', markers=True,
                      labels={'paarly_count': 'Produits', 'date': 'Date',
                              'combo': 'Pays / Reseller'},
                      title="Évolution par couple pays × reseller")
        st.plotly_chart(fig, use_container_width=True)

        fig_pct = _pct_chart(df_filt, 'paarly_count', 'combo',
                             "Évolution en % vs 12/05 — par pays × reseller")
        if fig_pct is not None:
            st.plotly_chart(fig_pct, use_container_width=True)

# ============================================================
# TAB 4 — PAARLY vs PAARLY entre 2 dates (avec filtres)
# ============================================================
with tab4:
    st.header("Comparaison PAARLY entre 2 dates")

    # ⬇️ Filtres pays / reseller
    sel_region_t4, sel_resellers_t4 = country_reseller_filters(df, 't4')

    all_dates_l = sorted(df['date'].unique())
    col_a, col_b = st.columns(2)
    d1_idx = all_dates_l.index(REF_DATE) if REF_DATE in all_dates_l else 0
    d1 = col_a.selectbox("Date 1 (référence)", all_dates_l, index=d1_idx,
                         format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
                         key='t4_d1')
    d2 = col_b.selectbox("Date 2 (comparée)", all_dates_l,
                         index=len(all_dates_l) - 1,
                         format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
                         key='t4_d2')

    df1 = (df[df['date'] == d1][['region', 'reseller', 'paarly_count']]
           .rename(columns={'paarly_count': 'p1'}))
    df2 = (df[df['date'] == d2][['region', 'reseller', 'paarly_count']]
           .rename(columns={'paarly_count': 'p2'}))
    m = df1.merge(df2, on=['region', 'reseller'], how='outer')
    m = apply_filters(m, sel_region_t4, sel_resellers_t4)

    if m.empty:
        st.warning("Aucun couple Pays/Reseller sélectionné.")
    else:
        m['delta'] = m['p2'] - m['p1']
        m['delta_pct'] = (m['p2'] - m['p1']) / m['p1']
        m['combo'] = m['region'] + ' / ' + m['reseller']
        m = m.sort_values(['region', 'reseller'])

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name=f"PAARLY — {pd.Timestamp(d1).strftime('%d/%m/%Y')}",
            x=m['combo'], y=m['p1'], marker_color='#94a3b8'))
        fig.add_trace(go.Bar(
            name=f"PAARLY — {pd.Timestamp(d2).strftime('%d/%m/%Y')}",
            x=m['combo'], y=m['p2'], marker_color='#3b82f6'))
        fig.update_layout(barmode='group', xaxis_tickangle=-45, height=550,
                          legend=dict(orientation='h', y=1.08))
        st.plotly_chart(fig, use_container_width=True)

        d1_lbl = pd.Timestamp(d1).strftime('%d/%m')
        d2_lbl = pd.Timestamp(d2).strftime('%d/%m')
        disp = m[['combo', 'p1', 'p2', 'delta', 'delta_pct']].copy()
        disp.columns = ['Pays / Reseller', f'PAARLY {d1_lbl}', f'PAARLY {d2_lbl}',
                        'Δ absolu', 'Δ %']
        disp[f'PAARLY {d1_lbl}'] = disp[f'PAARLY {d1_lbl}'].apply(fmt_int)
        disp[f'PAARLY {d2_lbl}'] = disp[f'PAARLY {d2_lbl}'].apply(fmt_int)
        disp['Δ absolu'] = m['delta'].apply(lambda x: f"{x:+.0f}" if pd.notna(x) else "—")
        disp['Δ %'] = m['delta_pct'].apply(lambda x: fmt_pct(x, signed=True))
        st.dataframe(disp, use_container_width=True, hide_index=True)

# ============================================================
# TAB 5 — Doublons d'IDs PAARLY (par jour, avec filtres)
# ============================================================
with tab5:
    st.header("Décompte des IDs PAARLY en doublon")
    st.markdown(
        "Pour une date donnée, identifie les `product_id` qui apparaissent **plus d'une fois** "
        "dans le CSV PAARLY (après filtres pays / concurrents)."
    )

    avail_dates = list_available_csv_dates()
    if not avail_dates:
        st.warning(
            "⚠️ Aucun CSV brut disponible dans `data/paarly_csv/`. "
            "Dépose les CSV PAARLY quotidiens dans ce dossier pour analyser les doublons "
            "(l'Excel de base contient des comptages agrégés, pas les `product_id` ligne par ligne)."
        )
    else:
        st.caption(
            f"Dates dispo : {', '.join(d.strftime('%d/%m') for d in avail_dates)}"
        )
        sel_date_dup = st.select_slider(
            "Date",
            options=avail_dates,
            value=avail_dates[-1],
            format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
            key='t5_date',
        )

        raw = load_raw_paarly_csv(sel_date_dup)
        if raw.empty:
            st.warning(f"Pas de CSV pour le {pd.Timestamp(sel_date_dup).strftime('%d/%m/%Y')}.")
        else:
            # Filtres pays + concurrents (sur le CSV brut)
            col_a, col_b = st.columns(2)
            countries_avail = sorted(raw['country'].dropna().unique().tolist())
            sel_countries = col_a.multiselect(
                "Pays (code source : BEL/ESP/ITA/NL)",
                countries_avail, default=countries_avail, key='t5_countries')
            resellers_avail = sorted(
                raw[raw['country'].isin(sel_countries)]['reseller_norm'].dropna().unique().tolist())
            sel_resellers = col_b.multiselect(
                "Concurrent(s)",
                resellers_avail, default=resellers_avail, key='t5_resellers')

            filt = raw[(raw['country'].isin(sel_countries)) &
                       (raw['reseller_norm'].isin(sel_resellers))]

            if filt.empty:
                st.warning("Aucune ligne après filtres.")
            else:
                # Doublon = même product_id chez un même (pays, reseller).
                # On compte aussi le nombre d'URLs distinctes pour classer :
                #   - URLs toutes distinctes → souci de matching (même product_id matché à N URLs)
                #   - URLs toutes identiques → vrai bug scraper (même ligne importée N fois)
                #   - URLs partiellement distinctes → cas mixte
                counts = (filt.groupby(['country', 'reseller_norm', 'product_id'])
                          .agg(nb_occurrences=('url', 'size'),
                               nb_urls_distinctes=('url', 'nunique'))
                          .reset_index()
                          .sort_values('nb_occurrences', ascending=False))
                dups = counts[counts['nb_occurrences'] > 1].copy()

                def classify_dup(row):
                    if row['nb_urls_distinctes'] == row['nb_occurrences']:
                        return '🔗 Matching'
                    elif row['nb_urls_distinctes'] == 1:
                        return '🐛 Scraper'
                    else:
                        return '🔀 Mixte'
                if not dups.empty:
                    dups['type'] = dups.apply(classify_dup, axis=1)

                total_lignes = len(filt)
                ids_uniques_par_couple = len(counts)
                nb_dups = len(dups)
                lignes_dup = int(dups['nb_occurrences'].sum()) if not dups.empty else 0
                lignes_redondantes = lignes_dup - nb_dups

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Lignes filtrées", fmt_int(total_lignes))
                c2.metric("IDs uniques (par couple)", fmt_int(ids_uniques_par_couple),
                          help="Nombre de triplets (pays, reseller, product_id) distincts.")
                c3.metric("IDs en doublon", fmt_int(nb_dups),
                          help="Nombre de triplets (pays, reseller, product_id) où le product_id apparaît plus d'une fois.")
                c4.metric("Lignes redondantes", fmt_int(lignes_redondantes),
                          help="Total des lignes en doublon moins 1 par triplet (= occurrences superflues).")

                if dups.empty:
                    st.success(
                        "✅ Aucun doublon détecté avec ces filtres "
                        "(un doublon = même `product_id` chez un même concurrent dans un même pays).")
                else:
                    # Breakdown par type de doublon
                    st.markdown("##### Classification des doublons")
                    nb_matching = int((dups['type'] == '🔗 Matching').sum())
                    nb_scraper = int((dups['type'] == '🐛 Scraper').sum())
                    nb_mixte = int((dups['type'] == '🔀 Mixte').sum())
                    m1, m2, m3 = st.columns(3)
                    m1.metric("🔗 Matching", fmt_int(nb_matching),
                              help="URLs toutes distinctes : même product_id matché à plusieurs URLs distinctes chez le concurrent. À remonter à l'équipe matching (Adrienne / Wissem).")
                    m2.metric("🐛 Scraper", fmt_int(nb_scraper),
                              help="URLs toutes identiques : la même ligne a été importée plusieurs fois. Bug du scraper, à reporter.")
                    m3.metric("🔀 Mixte", fmt_int(nb_mixte),
                              help="Mélange des deux : certaines URLs sont distinctes, d'autres dupliquées.")

                    # Filtre sur le type
                    type_options = ['Tous'] + sorted(dups['type'].unique().tolist())
                    sel_type = st.radio("Filtrer par type", type_options, horizontal=True, key='t5_type')
                    dups_view = dups if sel_type == 'Tous' else dups[dups['type'] == sel_type]

                    if dups_view.empty:
                        st.info("Aucun doublon de ce type avec les filtres actuels.")
                    else:
                        # Affichage : combo pays/reseller + ID
                        dups_view = dups_view.copy()
                        dups_view['pays_reseller'] = dups_view['country'] + ' / ' + dups_view['reseller_norm']
                        dups_view['label'] = (dups_view['product_id'].astype(str) + ' — '
                                              + dups_view['pays_reseller'] + ' (' + dups_view['type'] + ')')

                        top_n = min(20, len(dups_view))
                        top = dups_view.head(top_n)
                        color_map = {'🔗 Matching': '#f59e0b', '🐛 Scraper': '#dc2626', '🔀 Mixte': '#7c3aed'}
                        fig_dup = go.Figure(go.Bar(
                            x=top['nb_occurrences'],
                            y=top['label'],
                            orientation='h',
                            marker_color=[color_map[t] for t in top['type']],
                            text=top['nb_occurrences'],
                            textposition='outside',
                        ))
                        fig_dup.update_layout(
                            title=f"Top {top_n} doublons (couleur = type)",
                            xaxis_title="Nombre d'occurrences",
                            yaxis_title="",
                            height=max(300, 30 * top_n),
                            yaxis=dict(autorange='reversed'))
                        st.plotly_chart(fig_dup, use_container_width=True)

                        # Tableau complet
                        st.markdown(f"**Tous les doublons** ({len(dups_view)} triplets)")
                        disp_dups = dups_view[['country', 'reseller_norm', 'product_id',
                                                'nb_occurrences', 'nb_urls_distinctes', 'type']].copy()
                        disp_dups.columns = ['Pays', 'Reseller', 'product_id',
                                             'Nb occurrences', 'URLs distinctes', 'Type']
                        st.dataframe(disp_dups, use_container_width=True, hide_index=True)

                        # Drill-down — sélection flexible + téléchargement CSV
                        with st.expander("🔍 Voir le détail des lignes des doublons + télécharger"):
                            st.caption(
                                "Affiche uniquement les lignes constituant des doublons "
                                "(triplets pays × reseller × product_id où le product_id apparaît plus d'une fois).")

                            # Toutes les lignes appartenant à un triplet en doublon
                            all_dup_rows = filt.merge(
                                dups_view[['country', 'reseller_norm', 'product_id']],
                                on=['country', 'reseller_norm', 'product_id'],
                                how='inner')

                            mode = st.radio(
                                "Mode de sélection",
                                ["Tout", "Par couple (pays × reseller)", "Par product_id"],
                                horizontal=True, key='t5_drill_mode')

                            if mode == "Tout":
                                rows_to_show = all_dup_rows
                            elif mode == "Par couple (pays × reseller)":
                                pairs = sorted(set(zip(dups_view['country'],
                                                       dups_view['reseller_norm'])))
                                pair_labels = [f"{c} / {r}" for c, r in pairs]
                                sel_pairs = st.multiselect(
                                    "Couple(s) pays × reseller",
                                    pair_labels, default=pair_labels,
                                    key='t5_drill_pairs')
                                if sel_pairs:
                                    sel_tuples = [tuple(s.split(' / ')) for s in sel_pairs]
                                    sel_df = pd.DataFrame(sel_tuples,
                                                          columns=['country', 'reseller_norm'])
                                    rows_to_show = all_dup_rows.merge(
                                        sel_df, on=['country', 'reseller_norm'], how='inner')
                                else:
                                    rows_to_show = all_dup_rows.head(0)
                            else:  # Par product_id
                                pid_options = sorted(dups_view['product_id'].unique().tolist())
                                sel_pids = st.multiselect(
                                    "product_id(s) en doublon",
                                    pid_options,
                                    key='t5_drill_pids')
                                if sel_pids:
                                    rows_to_show = all_dup_rows[
                                        all_dup_rows['product_id'].isin(sel_pids)]
                                else:
                                    rows_to_show = all_dup_rows.head(0)

                            cols_show = ['product_id', 'code', 'country', 'reseller_norm',
                                         'priceCurrent', 'priceMap', 'priceDiscount',
                                         'url', 'crawlDate']
                            cols_present = [c for c in cols_show if c in rows_to_show.columns]

                            if rows_to_show.empty:
                                st.info("Sélectionne au moins un élément pour voir les lignes.")
                            else:
                                st.markdown(
                                    f"**{fmt_int(len(rows_to_show))} ligne(s)** — "
                                    f"{fmt_int(rows_to_show.groupby(['country','reseller_norm','product_id']).ngroups)} triplet(s) doublon(s) couvert(s)")
                                st.dataframe(rows_to_show[cols_present].sort_values(
                                    ['country', 'reseller_norm', 'product_id']),
                                    use_container_width=True, hide_index=True)

                                # Téléchargement CSV (sep ; + BOM pour ouverture Excel directe)
                                csv_bytes = rows_to_show[cols_present].sort_values(
                                    ['country', 'reseller_norm', 'product_id']
                                ).to_csv(index=False, sep=';').encode('utf-8-sig')
                                date_str_dl = pd.Timestamp(sel_date_dup).strftime('%Y-%m-%d')
                                st.download_button(
                                    "📥 Télécharger ces lignes (CSV)",
                                    data=csv_bytes,
                                    file_name=f"doublons_PAARLY_{date_str_dl}.csv",
                                    mime='text/csv',
                                    key='t5_drill_dl')

# ============================================================
# TAB 6 — Valeurs manquantes (#N/A) dans le CSV brut PAARLY
# ============================================================
with tab6:
    st.header("Valeurs manquantes / #N/A dans l'export PAARLY")
    st.markdown(
        "Identifie les cellules vides ou `#N/A` dans le CSV brut PAARLY pour un jour donné, "
        "et te dit **quels product_id** et **quels couples pays × concurrent** sont touchés."
    )

    avail_dates_t6 = list_available_csv_dates()
    if not avail_dates_t6:
        st.warning(
            "⚠️ Aucun CSV brut disponible dans `data/paarly_csv/`. "
            "Dépose les CSV PAARLY quotidiens pour analyser les valeurs manquantes."
        )
    else:
        sel_date_na = st.select_slider(
            "Date",
            options=avail_dates_t6,
            value=avail_dates_t6[-1],
            format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y'),
            key='t6_date',
        )
        raw = load_raw_paarly_csv(sel_date_na)
        if raw.empty:
            st.warning(f"Pas de CSV pour le {pd.Timestamp(sel_date_na).strftime('%d/%m/%Y')}.")
        else:
            # Filtres pays + concurrents
            col_a, col_b = st.columns(2)
            countries_avail = sorted(raw['country'].dropna().unique().tolist())
            sel_countries = col_a.multiselect(
                "Pays (code source : BEL/ESP/ITA/NL)",
                countries_avail, default=countries_avail, key='t6_countries')
            resellers_avail = sorted(
                raw[raw['country'].isin(sel_countries)]['reseller_norm'].dropna().unique().tolist())
            sel_resellers = col_b.multiselect(
                "Concurrent(s)",
                resellers_avail, default=resellers_avail, key='t6_resellers')

            filt = raw[(raw['country'].isin(sel_countries)) &
                       (raw['reseller_norm'].isin(sel_resellers))].copy()

            if filt.empty:
                st.warning("Aucune ligne après filtres.")
            else:
                # Colonnes à analyser pour #N/A (priceCurrent, priceMap, priceDiscount,
                # code, url, crawlDate — pas product_id, country, reseller qui sont les clés)
                cols_to_check = [c for c in
                                 ['code', 'priceCurrent', 'priceMap', 'priceDiscount',
                                  'url', 'crawlDate']
                                 if c in filt.columns]
                price_cols_top = [c for c in ['priceCurrent', 'priceMap', 'priceDiscount']
                                  if c in filt.columns]

                # Comptage des NaN par colonne
                na_counts = {c: int(filt[c].isna().sum()) for c in cols_to_check}
                total_lignes = len(filt)
                lignes_prix_na = (int(filt[price_cols_top].isna().any(axis=1).sum())
                                  if price_cols_top else 0)

                c1, c2, c3 = st.columns(3)
                c1.metric("Lignes filtrées", fmt_int(total_lignes))
                c2.metric("Lignes avec ≥1 prix #N/A", fmt_int(lignes_prix_na),
                          help="Lignes où priceCurrent, priceMap ou priceDiscount est manquant.")
                c3.metric("% prix #N/A",
                          f"{(lignes_prix_na / total_lignes * 100):.1f} %"
                          if total_lignes else "—")

                # Récap par colonne (global, après filtres)
                st.markdown("##### #N/A par colonne (global, après filtres)")
                recap_col = pd.DataFrame([
                    {'Colonne': c,
                     'Nb #N/A': n,
                     '% lignes filtrées': (f"{(n / total_lignes * 100):.1f} %"
                                           if total_lignes else "—")}
                    for c, n in na_counts.items()
                ])
                st.dataframe(recap_col, use_container_width=True, hide_index=True)

                # Pivot par (pays, reseller, colonne) avec ratio par concurrent
                st.markdown("##### #N/A par couple pays × concurrent")
                st.caption(
                    "Chaque cellule colonne affiche **`Nb #N/A (% des lignes du concurrent)`**. "
                    "La colonne **Lignes prix ≥1 #N/A** = nombre de lignes où **au moins un des "
                    "3 prix** (`priceCurrent`, `priceMap`, `priceDiscount`) est manquant — c'est "
                    "le vrai indicateur business. "
                    "Si une colonne comme `code` est vide à 100 % (cas des resellers ES sans EAN), "
                    "c'est probablement attendu — regarde les % par colonne pour comprendre.")

                price_cols = [c for c in ['priceCurrent', 'priceMap', 'priceDiscount']
                              if c in filt.columns]

                def fmt_count_pct(n, total):
                    if total <= 0:
                        return "—"
                    if n == 0:
                        return "0"
                    return f"{fmt_int(n)} ({n / total * 100:.1f} %)"

                pivot_rows = []
                for (country, reseller), sub in filt.groupby(['country', 'reseller_norm']):
                    n_lignes = len(sub)
                    if price_cols:
                        n_prix = int(sub[price_cols].isna().any(axis=1).sum())
                    else:
                        n_prix = 0
                    row = {'Pays': country, 'Reseller': reseller,
                           'Lignes': fmt_int(n_lignes)}
                    for c in cols_to_check:
                        n = int(sub[c].isna().sum())
                        row[c] = fmt_count_pct(n, n_lignes)
                    row['Lignes prix ≥1 #N/A'] = fmt_count_pct(n_prix, n_lignes)
                    # Pour le tri : nb absolu de lignes avec prix manquant (la vraie urgence)
                    row['_sort'] = n_prix
                    pivot_rows.append(row)
                pivot_df = (pd.DataFrame(pivot_rows)
                            .sort_values('_sort', ascending=False)
                            .drop(columns=['_sort']))
                st.dataframe(pivot_df, use_container_width=True, hide_index=True)

                # Drill-down — filtres toujours visibles, export avec colonnes du CSV d'origine
                st.markdown("##### 🔍 Voir le détail des lignes #N/A + télécharger")
                cols_with_na = [c for c in cols_to_check if na_counts[c] > 0]
                if not cols_with_na:
                    st.success("✅ Aucune valeur manquante détectée avec ces filtres.")
                else:
                    # Choix des colonnes à considérer comme #N/A
                    # Par défaut on coche les colonnes prix (= vrai indicateur business)
                    default_na_cols = ([c for c in price_cols_top if c in cols_with_na]
                                       or cols_with_na)
                    sel_na_cols = st.multiselect(
                        "Colonne(s) à considérer comme #N/A",
                        options=cols_with_na,
                        default=default_na_cols,
                        format_func=lambda c: f"{c} ({na_counts[c]} #N/A)",
                        key='t6_na_cols',
                        help="Une ligne est incluse si elle a #N/A dans au moins une des colonnes sélectionnées.")

                    if not sel_na_cols:
                        st.info("Sélectionne au moins une colonne.")
                    else:
                        all_na_rows = filt[filt[sel_na_cols].isna().any(axis=1)].copy()

                        # Filtres TOUJOURS visibles — pas de mode radio
                        st.markdown("**Filtres** (laisse tout coché pour ne pas filtrer)")
                        col_a, col_b = st.columns(2)
                        countries_drill = sorted(
                            all_na_rows['country'].dropna().unique().tolist())
                        sel_countries_drill = col_a.multiselect(
                            "Pays",
                            countries_drill, default=countries_drill,
                            key='t6_d_countries')
                        resellers_avail_drill = sorted(all_na_rows[
                            all_na_rows['country'].isin(sel_countries_drill)
                        ]['reseller_norm'].dropna().unique().tolist())
                        sel_resellers_drill = col_b.multiselect(
                            "Concurrent(s)",
                            resellers_avail_drill, default=resellers_avail_drill,
                            key='t6_d_resellers')

                        # product_id (optionnel — vide = tous)
                        sel_pids_drill = st.multiselect(
                            "product_id (optionnel — laisse vide pour tous)",
                            sorted(all_na_rows['product_id'].dropna().unique().tolist()),
                            key='t6_d_pids')

                        rows_view = all_na_rows[
                            (all_na_rows['country'].isin(sel_countries_drill)) &
                            (all_na_rows['reseller_norm'].isin(sel_resellers_drill))
                        ]
                        if sel_pids_drill:
                            rows_view = rows_view[
                                rows_view['product_id'].isin(sel_pids_drill)]

                        # Colonnes complètes du CSV PAARLY d'origine (mêmes noms, même ordre)
                        original_cols = ['product_id', 'code', 'reseller',
                                         'priceCurrent', 'priceMap', 'priceDiscount',
                                         'url', 'crawlDate', 'country']
                        cols_present_na = [c for c in original_cols if c in rows_view.columns]

                        if rows_view.empty:
                            st.warning("Aucune ligne après filtres.")
                        else:
                            n_ids_uniques = rows_view['product_id'].nunique()
                            n_couples_touches = rows_view.groupby(
                                ['country', 'reseller']).ngroups
                            st.markdown(
                                f"**{fmt_int(len(rows_view))} ligne(s) complètes** — "
                                f"**{fmt_int(n_ids_uniques)} product_id uniques** "
                                f"sur **{n_couples_touches} couple(s) pays × concurrent** "
                                f"— #N/A dans : `{', '.join(sel_na_cols)}`")
                            st.dataframe(rows_view[cols_present_na].sort_values(
                                ['country', 'reseller', 'product_id']),
                                use_container_width=True, hide_index=True)

                            # 2 boutons de téléchargement côte à côte
                            date_str_na = pd.Timestamp(sel_date_na).strftime('%Y-%m-%d')
                            cols_suffix = ('_'.join(sel_na_cols) if len(sel_na_cols) <= 3
                                           else f"{len(sel_na_cols)}cols")
                            dl_col1, dl_col2 = st.columns(2)

                            # (1) Lignes complètes — mêmes colonnes que le CSV d'origine
                            csv_bytes_na = rows_view[cols_present_na].sort_values(
                                ['country', 'reseller', 'product_id']
                            ).to_csv(index=False, sep=';').encode('utf-8-sig')
                            dl_col1.download_button(
                                "📥 Lignes complètes (CSV)",
                                data=csv_bytes_na,
                                file_name=f"NA_lignes_{cols_suffix}_PAARLY_{date_str_na}.csv",
                                mime='text/csv',
                                key='t6_dl',
                                help="Toutes les colonnes du CSV d'origine : product_id, code, reseller, prix, url, crawlDate, country")

                            # (2) Juste les IDs (uniques par couple pays × reseller)
                            ids_only = (rows_view[['product_id', 'country', 'reseller']]
                                        .drop_duplicates()
                                        .sort_values(['country', 'reseller', 'product_id']))
                            ids_only.columns = ['product_id', 'Pays', 'Reseller']
                            csv_bytes_ids = ids_only.to_csv(
                                index=False, sep=';').encode('utf-8-sig')
                            dl_col2.download_button(
                                "📥 IDs uniques par couple (CSV)",
                                data=csv_bytes_ids,
                                file_name=f"NA_IDs_{cols_suffix}_PAARLY_{date_str_na}.csv",
                                mime='text/csv',
                                key='t6_dl_ids',
                                help="Juste product_id × Pays × Reseller — 1 ligne par couple touché.")
