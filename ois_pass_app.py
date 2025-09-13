
# ois_pass_app.py
# Streamlit PASS Dashboard – Cohort, HR, Gender, Cluster-level analysis + Strategies

import io
from typing import Dict, Optional, List, Tuple

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="OIS PASS Dashboard", layout="wide")

PASS_FILES = {
    "Grade 6": "Grade 6 - PASS Report Sept 2025.xlsx",
    "Grade 7": "Grade 7 - PASS Report Sept 2025.xlsx",
    "Grade 8": "Grade 8 - PASS Report Sept 2025.xlsx",
}

PASS_DOMAINS = [
    "Feelings about school",
    "Perceived learning capability",
    "Self-regard as a learner",
    "Preparedness for learning",
    "Attitudes to teachers",
    "General work ethic",
    "Confidence in learning",
    "Attitudes to attendance",
    "Response to curriculum demands",
]
PASS_DOMAINS_NUM = [f"{i+1}. {d}" for i, d in enumerate(PASS_DOMAINS)]
DOMAIN_MAP = dict(zip(PASS_DOMAINS, PASS_DOMAINS_NUM))
THRESHOLDS = {"red": 60.0, "amber": 70.0}

CLUSTERS = {
    "Self": ["2. Perceived learning capability", "3. Self-regard as a learner"],
    "Study": ["4. Preparedness for learning", "6. General work ethic", "7. Confidence in learning"],
    "School": ["1. Feelings about school", "5. Attitudes to teachers", "8. Attitudes to attendance", "9. Response to curriculum demands"],
}

DOMAIN_STRATEGIES = {
    "1. Feelings about school": [
        "Rebuild belonging (circles, advisory games, peer shout-outs)",
        "Use assemblies for positive school identity",
        "Student voice forums"
    ],
    "2. Perceived learning capability": [
        "Growth mindset interventions",
        "Teacher feedback focused on effort/progress",
        "Small wins / scaffolding for success"
    ],
    "3. Self-regard as a learner": [
        "Celebrate academic progress (not just high achievers)",
        "Peer tutoring opportunities",
        "Strengths-based feedback from teachers"
    ],
    "4. Preparedness for learning": [
        "Planner routines, visible goal trackers",
        "‘Do Now’ tasks in class for structure",
        "Time management mini-lessons"
    ],
    "5. Attitudes to teachers": [
        "Positive calls/emails home",
        "Advisory ‘Meet the Teacher’ sessions",
        "Restorative practices, reconnection strategies"
    ],
    "6. General work ethic": [
        "Weekly routines: planner checks, visible targets",
        "Advisory SEL sessions on perseverance & resilience",
        "Recognition for consistent effort"
    ],
    "7. Confidence in learning": [
        "Growth mindset assemblies",
        "Celebrating risk-taking in learning",
        "Peer support & ‘safe fail’ opportunities"
    ],
    "8. Attitudes to attendance": [
        "Monitor attendance/tardies closely",
        "Early family contact",
        "HR/class competitions for attendance"
    ],
    "9. Response to curriculum demands": [
        "Audit workload with HoDs",
        "Space out assessments",
        "Scaffolding & differentiation for complex tasks"
    ]
}

SHEET_HINTS = {
    "cohort": ["cohort analysis"],
    "profiles": ["individual profiles", "student profiles"],
    "items": ["item level analysis","item-level analysis"],
}

# ----------------- Helpers -----------------
def _clean(x):
    if pd.isna(x): return ""
    return str(x).strip()
def _norm(s: str) -> str:
    return _clean(s).lower().replace("_"," ").replace("-"," ").replace("  "," ")
def list_sheets(src) -> List[str]:
    try:
        return pd.ExcelFile(src).sheet_names
    except Exception:
        return []
def choose_sheet(sheet_names: List[str], hints: List[str]) -> Optional[str]:
    for name in sheet_names:
        n = _norm(name)
        if any(h in n for h in hints):
            return name
    return sheet_names[0] if sheet_names else None

# ----------------- Parsers -----------------
def parse_cohort_sheet(src, sheet_name: Optional[str]) -> pd.DataFrame:
    raw = pd.read_excel(src, sheet_name=sheet_name, header=None)
    header_row = None
    for r in range(min(15, len(raw))):
        vals = [_clean(x) for x in raw.iloc[r].values]
        if sum(1 for v in vals if v in PASS_DOMAINS) >= 5:
            header_row = r; break
    if header_row is not None and header_row + 1 < len(raw):
        headers = [_clean(x) for x in raw.iloc[header_row].values]
        scores = raw.iloc[header_row + 1].values
        data = {}
        for h, s in zip(headers, scores):
            if h in PASS_DOMAINS:
                try: data[h] = float(s)
                except: pass
        df = pd.Series(data).rename_axis("Domain").reset_index(name="Score")
        df["Domain"] = df["Domain"].map(DOMAIN_MAP)
        return df
    return pd.DataFrame(columns=["Domain","Score"])

def parse_individual_profiles(src, sheet_name: Optional[str]) -> pd.DataFrame:
    try:
        df = pd.read_excel(src, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()
    for dom in PASS_DOMAINS:
        if dom in df.columns: df = df.rename(columns={dom: DOMAIN_MAP[dom]})
    # Standardize Group column
    GROUP_ALIASES = ["Group","Class","Form","HR"]
    found = None
    for alias in GROUP_ALIASES:
        if alias in df.columns:
            found = alias
            break
    if found:
        df = df.rename(columns={found:"Group"})
    else:
        # only fallback if absolutely no group column
        df["Group"] = "All"
    return df

def parse_item_level(src, sheet_name: Optional[str]) -> pd.DataFrame:
    try:
        raw = pd.read_excel(src, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()
    if "Category" not in raw.columns:
        return pd.DataFrame()
    for dom in PASS_DOMAINS:
        if dom in raw.columns: raw = raw.rename(columns={dom: DOMAIN_MAP[dom]})
    return raw

def color_for_score(x: float) -> str:
    if pd.isna(x): return ""
    if x < THRESHOLDS["red"]: return "background-color: #f8d7da"
    if x < THRESHOLDS["amber"]: return "background-color: #fff3cd"
    return "background-color: #d4edda"

def make_bar(df: pd.DataFrame, title: str):
    fig, ax = plt.subplots(figsize=(8,4))
    ax.bar(df["Domain"], df["Score"])
    ax.set_title(title); ax.set_ylabel("Score"); ax.set_ylim(0,100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)

def make_gender_bar(df: pd.DataFrame, title: str):
    doms = [d for d in PASS_DOMAINS_NUM if d in df.columns]
    boys = df[df["Category"]=="Boys"][doms].iloc[0]
    girls = df[df["Category"]=="Girls"][doms].iloc[0]
    overall = df[df["Category"]=="Overall"][doms].iloc[0]
    x = np.arange(len(doms))
    fig, ax = plt.subplots(figsize=(10,4))
    ax.bar(x-0.25, boys, width=0.25, label="Boys")
    ax.bar(x, girls, width=0.25, label="Girls")
    ax.bar(x+0.25, overall, width=0.25, label="Overall")
    ax.set_xticks(x); ax.set_xticklabels(doms, rotation=45, ha="right")
    ax.set_ylim(0,100); ax.set_title(title)
    ax.legend()
    st.pyplot(fig)

def format_insights(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    if df.empty: return [], []
    top2 = df.sort_values("Score", ascending=False).head(2)
    bot2 = df.sort_values("Score", ascending=True).head(2)
    strengths = [f"- {r.Domain} ({r.Score:.1f})" for r in top2.itertuples()]
    concerns = [f"- {r.Domain} ({r.Score:.1f})" for r in bot2.itertuples()]
    return strengths, concerns

def gender_insights(df: pd.DataFrame) -> List[str]:
    insights = []
    if df.empty: return insights
    doms = [d for d in PASS_DOMAINS_NUM if d in df.columns]
    for d in doms:
        row = df.set_index("Category")[d]
        if "Boys" in row and "Girls" in row:
            gap = row["Boys"] - row["Girls"]
            if abs(gap) >= 10:
                who = "Boys" if gap < 0 else "Girls"
                insights.append(f"- {who} weaker in {d} (gap {gap:+.1f})")
    return insights

def domain_strategies(df: pd.DataFrame):
    flagged = df[df["Score"] < THRESHOLDS["amber"]]
    for r in flagged.itertuples():
        dom = r.Domain
        st.markdown(f"**{dom} Strategies:**")
        for s in DOMAIN_STRATEGIES.get(dom, []):
            st.write(f"- {s}")

def cluster_scores(df: pd.DataFrame) -> pd.DataFrame:
    scores = {}
    for cname, doms in CLUSTERS.items():
        vals = df[df["Domain"].isin(doms)]["Score"]
        if not vals.empty:
            scores[cname] = vals.mean()
    return pd.Series(scores).rename_axis("Cluster").reset_index(name="Score")
