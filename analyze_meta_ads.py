#!/usr/bin/env python3
"""
Analyse de campagnes Meta Ads via l'API Graph Facebook (Marketing API).

Usage:
    python analyze_meta_ads.py [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--level {campaign,adset,ad}]

Configuration:
    Copie .env.example en .env et renseigne FB_ACCESS_TOKEN et FB_AD_ACCOUNT_ID.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
except ImportError:
    print("Installe les dépendances : pip install -r requirements.txt")
    sys.exit(1)

try:
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.exceptions import FacebookRequestError
except ImportError:
    print("Installe les dépendances : pip install -r requirements.txt")
    sys.exit(1)

try:
    import pandas as pd
    from tabulate import tabulate
except ImportError:
    print("Installe les dépendances : pip install -r requirements.txt")
    sys.exit(1)

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("FB_AD_ACCOUNT_ID")

INSIGHTS_FIELDS = [
    "campaign_name",
    "adset_name",
    "ad_name",
    "impressions",
    "reach",
    "frequency",
    "clicks",
    "unique_clicks",
    "ctr",
    "cpc",
    "cpm",
    "cpp",
    "spend",
    "actions",
    "action_values",
    "cost_per_action_type",
    "conversions",
    "conversion_values",
    "purchase_roas",
    "objective",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_action_value(action_list, action_type, key="value"):
    """Extrait la valeur d'un type d'action depuis une liste d'actions."""
    if not action_list:
        return 0.0
    for action in action_list:
        if action.get("action_type") == action_type:
            return safe_float(action.get(key, 0))
    return 0.0


def format_currency(value):
    return f"{value:,.2f} €"


def format_pct(value):
    return f"{value:.2f}%"


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def init_api():
    if not ACCESS_TOKEN:
        print("Erreur : FB_ACCESS_TOKEN manquant dans le fichier .env")
        sys.exit(1)
    if not AD_ACCOUNT_ID:
        print("Erreur : FB_AD_ACCOUNT_ID manquant dans le fichier .env")
        sys.exit(1)
    FacebookAdsApi.init(access_token=ACCESS_TOKEN)


def fetch_insights(since: str, until: str, level: str = "campaign"):
    """Récupère les insights de toutes les campagnes pour la période donnée."""
    account = AdAccount(AD_ACCOUNT_ID)
    params = {
        "level": level,
        "time_range": {"since": since, "until": until},
        "time_increment": 1,  # données journalières
    }
    try:
        insights = account.get_insights(fields=INSIGHTS_FIELDS, params=params)
        return list(insights)
    except FacebookRequestError as e:
        print(f"Erreur API Facebook : {e.api_error_message()}")
        print(f"Code : {e.api_error_code()}")
        sys.exit(1)


def fetch_campaigns():
    """Récupère la liste des campagnes avec leur statut."""
    account = AdAccount(AD_ACCOUNT_ID)
    fields = [
        Campaign.Field.name,
        Campaign.Field.status,
        Campaign.Field.objective,
        Campaign.Field.daily_budget,
        Campaign.Field.lifetime_budget,
        Campaign.Field.start_time,
        Campaign.Field.stop_time,
    ]
    try:
        return list(account.get_campaigns(fields=fields))
    except FacebookRequestError as e:
        print(f"Erreur API Facebook : {e.api_error_message()}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def build_dataframe(insights):
    rows = []
    for insight in insights:
        row = {
            "date": insight.get("date_start", ""),
            "campaign": insight.get("campaign_name", ""),
            "adset": insight.get("adset_name", ""),
            "ad": insight.get("ad_name", ""),
            "impressions": safe_float(insight.get("impressions", 0)),
            "reach": safe_float(insight.get("reach", 0)),
            "frequency": safe_float(insight.get("frequency", 0)),
            "clicks": safe_float(insight.get("clicks", 0)),
            "unique_clicks": safe_float(insight.get("unique_clicks", 0)),
            "ctr": safe_float(insight.get("ctr", 0)),
            "cpc": safe_float(insight.get("cpc", 0)),
            "cpm": safe_float(insight.get("cpm", 0)),
            "spend": safe_float(insight.get("spend", 0)),
            "purchases": extract_action_value(
                insight.get("actions"), "purchase"
            ),
            "purchase_value": extract_action_value(
                insight.get("action_values"), "purchase"
            ),
            "roas": extract_action_value(
                insight.get("purchase_roas"), "omni_purchase", key="value"
            ),
            "leads": extract_action_value(insight.get("actions"), "lead"),
            "link_clicks": extract_action_value(
                insight.get("actions"), "link_click"
            ),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def analyze(df: pd.DataFrame, level: str):
    print("\n" + "=" * 70)
    print("  ANALYSE META ADS")
    print("=" * 70)

    # --- Vue globale ---
    total_spend = df["spend"].sum()
    total_impressions = df["impressions"].sum()
    total_clicks = df["clicks"].sum()
    total_purchases = df["purchases"].sum()
    total_purchase_value = df["purchase_value"].sum()
    total_leads = df["leads"].sum()
    avg_ctr = (total_clicks / total_impressions * 100) if total_impressions else 0
    avg_cpc = (total_spend / total_clicks) if total_clicks else 0
    avg_cpm = (total_spend / total_impressions * 1000) if total_impressions else 0
    overall_roas = (total_purchase_value / total_spend) if total_spend else 0
    cpp = (total_spend / total_purchases) if total_purchases else 0
    cpl = (total_spend / total_leads) if total_leads else 0

    summary = [
        ["Dépenses totales", format_currency(total_spend)],
        ["Impressions", f"{int(total_impressions):,}"],
        ["Clics", f"{int(total_clicks):,}"],
        ["CTR moyen", format_pct(avg_ctr)],
        ["CPC moyen", format_currency(avg_cpc)],
        ["CPM moyen", format_currency(avg_cpm)],
        ["Achats", f"{int(total_purchases):,}"],
        ["Valeur des achats", format_currency(total_purchase_value)],
        ["ROAS global", f"{overall_roas:.2f}x"],
        ["Coût par achat", format_currency(cpp)],
        ["Leads", f"{int(total_leads):,}"],
        ["Coût par lead", format_currency(cpl)],
    ]
    print("\n--- Résumé global ---")
    print(tabulate(summary, headers=["Métrique", "Valeur"], tablefmt="rounded_outline"))

    # --- Par campagne ---
    if level in ("campaign", "adset", "ad"):
        group_col = "campaign"
        group_label = "Campagne"
        campaign_group = (
            df.groupby(group_col)
            .agg(
                spend=("spend", "sum"),
                impressions=("impressions", "sum"),
                clicks=("clicks", "sum"),
                purchases=("purchases", "sum"),
                purchase_value=("purchase_value", "sum"),
                leads=("leads", "sum"),
            )
            .reset_index()
        )
        campaign_group["CTR"] = (
            campaign_group["clicks"] / campaign_group["impressions"] * 100
        ).fillna(0)
        campaign_group["CPC"] = (
            campaign_group["spend"] / campaign_group["clicks"]
        ).replace([float("inf"), float("nan")], 0)
        campaign_group["ROAS"] = (
            campaign_group["purchase_value"] / campaign_group["spend"]
        ).replace([float("inf"), float("nan")], 0)
        campaign_group = campaign_group.sort_values("spend", ascending=False)

        table_data = []
        for _, row in campaign_group.iterrows():
            table_data.append(
                [
                    row[group_col][:40],
                    format_currency(row["spend"]),
                    f"{int(row['impressions']):,}",
                    f"{int(row['clicks']):,}",
                    format_pct(row["CTR"]),
                    format_currency(row["CPC"]),
                    f"{int(row['purchases']):,}",
                    f"{row['ROAS']:.2f}x",
                ]
            )
        print(f"\n--- Performance par {group_label} ---")
        print(
            tabulate(
                table_data,
                headers=[
                    group_label,
                    "Dépenses",
                    "Impressions",
                    "Clics",
                    "CTR",
                    "CPC",
                    "Achats",
                    "ROAS",
                ],
                tablefmt="rounded_outline",
            )
        )

    # --- Évolution journalière ---
    daily = (
        df.groupby("date")
        .agg(
            spend=("spend", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            purchases=("purchases", "sum"),
        )
        .reset_index()
        .sort_values("date")
    )
    daily["CTR"] = (daily["clicks"] / daily["impressions"] * 100).fillna(0)
    daily_data = [
        [
            row["date"],
            format_currency(row["spend"]),
            f"{int(row['impressions']):,}",
            f"{int(row['clicks']):,}",
            format_pct(row["CTR"]),
            f"{int(row['purchases']):,}",
        ]
        for _, row in daily.iterrows()
    ]
    print("\n--- Évolution journalière ---")
    print(
        tabulate(
            daily_data,
            headers=["Date", "Dépenses", "Impressions", "Clics", "CTR", "Achats"],
            tablefmt="rounded_outline",
        )
    )

    # --- Recommandations automatiques ---
    print("\n--- Recommandations ---")
    recommendations = []

    if avg_ctr < 1.0:
        recommendations.append(
            "CTR faible (< 1%) : teste de nouveaux visuels ou copies publicitaires."
        )
    if overall_roas > 0 and overall_roas < 2.0:
        recommendations.append(
            "ROAS < 2x : vérifie ta page de destination et ton tunnel de conversion."
        )
    if overall_roas >= 4.0:
        recommendations.append(
            "ROAS excellent (>= 4x) : envisage d'augmenter le budget sur les campagnes performantes."
        )
    if avg_cpc > 1.5:
        recommendations.append(
            f"CPC élevé ({format_currency(avg_cpc)}) : optimise le ciblage ou l'enchère."
        )

    best_campaigns = campaign_group.nlargest(3, "ROAS") if len(campaign_group) > 0 else pd.DataFrame()
    worst_campaigns = campaign_group.nsmallest(3, "spend").query("spend > 0")

    if not best_campaigns.empty:
        names = ", ".join(best_campaigns["campaign"].str[:30].tolist())
        recommendations.append(f"Meilleures campagnes (ROAS) : {names}")

    if not recommendations:
        recommendations.append("Les performances semblent équilibrées. Continue à monitorer.")

    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")

    print("\n" + "=" * 70)

    # Export CSV
    export_path = "meta_ads_export.csv"
    df.to_csv(export_path, index=False)
    print(f"\nDonnées exportées dans : {export_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="Analyse de campagnes Meta Ads")
    default_until = datetime.today().strftime("%Y-%m-%d")
    default_since = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    parser.add_argument(
        "--since",
        default=default_since,
        help=f"Date de début (YYYY-MM-DD). Défaut : {default_since}",
    )
    parser.add_argument(
        "--until",
        default=default_until,
        help=f"Date de fin (YYYY-MM-DD). Défaut : {default_until}",
    )
    parser.add_argument(
        "--level",
        choices=["campaign", "adset", "ad"],
        default="campaign",
        help="Niveau de granularité (défaut : campaign)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Connexion à l'API Facebook Marketing...")
    init_api()
    print(f"Récupération des insights du {args.since} au {args.until} (niveau : {args.level})...")
    insights = fetch_insights(args.since, args.until, args.level)
    if not insights:
        print("Aucune donnée trouvée pour cette période.")
        sys.exit(0)
    print(f"{len(insights)} enregistrement(s) récupéré(s).")
    df = build_dataframe(insights)
    analyze(df, args.level)


if __name__ == "__main__":
    main()
