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
    "School": [
        "1. Feelings about school",
        "5. Attitudes to teachers",
        "8. Attitudes to attendance",
        "9. Response to curriculum demands",
    ],
}

DOMAIN_STRATEGIES = {
    "1. Feelings about school": [
        "Rebuild belonging (circles, advisory games, peer shout-outs)",
        "Use assemblies for positive school identity",
        "Student voice forums",
    ],
    "2. Perceived learning capability": [
        "Growth mindset interventions",
        "Teacher feedback focused on effort/progress",
        "Small wins / scaffolding for success",
    ],
    "3. Self-regard as a learner": [
        "Celebrate academic progress (not just high achievers)",
        "Peer tutoring opportunities",
        "Strengths-based feedback from teachers",
    ],
    "4. Preparedness for learning": [
        "Planner routines, visible goal trackers",
        "‘Do Now’ tasks in class for structure",
        "Time management mini-lessons",
    ],
    "5. Attitudes to teachers": [
        "Positive calls/emails home",
        "Advisory ‘Meet the Teacher’ sessions",
        "Restorative practices, reconnection strategies",
    ],
    "6. General work ethic": [
        "Weekly routines: planner checks, visible targets",
        "Advisory SEL sessions on perseverance & resilience",
        "Recognition for consistent effort",
    ],
    "7. Confidence in learning": [
        "Growth mindset assemblies",
        "Celebrating risk-taking in learning",
        "Peer support & ‘safe fail’ opportunities",
    ],
    "8. Attitudes to attendance": [
        "Monitor attendance/tardies closely",
        "Early family contact",
        "HR/class competitions for attendance",
    ],
    "9. Response to curriculum demands": [
        "Audit workload with HoDs",
        "Space out assessments",
        "Scaffolding & differentiation for complex tasks",
    ],
}

SHEET_HINTS = {
    "cohort": ["cohort analysis"],
    "profiles": ["individual profiles", "student profiles"],
    "items": ["item level analysis", "item-level analysis"],
}

# ----------------- Helpers -----------------
def _clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def _norm(s: str) -> str:
    return _clean(s).lower().replace("_", " ").replace("-", " ").replace("  ", " ")

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
            header_row = r
            break
    if header_row is not None and header_row + 1 < len(raw):
        headers = [_clean(x) for x in raw.iloc[header_row].values]
        scores = raw.iloc[header_row + 1].values
        data = {}
        for h, s in zip(headers, scores):
            if h in PASS_DOMAINS:
                try:
                    data[h] = float(s)
                except:
                    pass
        df = pd.Series(data).rename_axis("Domain").reset_index(name="Score")
        df["Domain"] = df["Domain"].map(DOMAIN_MAP)
        return df
    return pd.DataFrame(columns=["Domain", "Score"])

def parse_individual_profiles(src, sheet_name: Optional[str]) -> pd.DataFrame:
    try:
        raw = pd.read_excel(src, sheet_name=sheet_name, header=None)
    except Exception:
        return pd.DataFrame()

    # Find header row
    header_row = None
    for r in range(min(20, len(raw))):
        row_vals = [str(x).strip().lower() for x in raw.iloc[r].values]
        if any("forename" in v or "group" in v for v in row_vals):
            header_row = r
            break
    if header_row is None:
        return pd.DataFrame()

    df = pd.read_excel(src, sheet_name=sheet_name, header=header_row)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # If there are multiple "group-like" columns, prefer the one with values like "6.1", "7.2"
    group_col = None
    for col in df.columns:
        if any(key in col for key in ["group", "class", "form", "hr"]):
            sample_vals = df[col].dropna().astype(str).head(20)
            if any("." in v for v in sample_vals):  # looks like "6.1"
                group_col = col
                break
            # Otherwise treat it as UPN
            if all(v.startswith("B") for v in sample_vals):
                df.rename(columns={col: "UPN"}, inplace=True)

    if group_col:
        df.rename(columns={group_col: "Group"}, inplace=True)
    else:
        df["Group"] = "All"

    # Gender
    for col in df.columns:
        if "gender" in col:
            df.rename(columns={col: "Gender"}, inplace=True)

    # Rename domains
    for dom in PASS_DOMAINS:
        for col in df.columns:
            if dom.lower() in col:
                df.rename(columns={col: DOMAIN_MAP[dom]}, inplace=True)

    return df



def parse_item_level(src, sheet_name: Optional[str]) -> pd.DataFrame:
    try:
        raw = pd.read_excel(src, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()

    # Normalize headers
    clean_cols = {c: str(c).strip().lower() for c in raw.columns}
    raw.rename(columns=clean_cols, inplace=True)

    # Detect Category column
    cat_col = None
    for col in raw.columns:
        if "category" in col:
            cat_col = col
            break
    if cat_col:
        raw.rename(columns={cat_col: "Category"}, inplace=True)
    else:
        return pd.DataFrame()

    # Rename domains
    for dom in PASS_DOMAINS:
        for col in raw.columns:
            if dom.lower() in col:
                raw.rename(columns={col: DOMAIN_MAP[dom]}, inplace=True)

    return raw


# ----------------- Visualization + Analysis -----------------
def color_for_score(x: float) -> str:
    if pd.isna(x):
        return ""
    if x < THRESHOLDS["red"]:
        return "background-color: #f8d7da"
    if x < THRESHOLDS["amber"]:
        return "background-color: #fff3cd"
    return "background-color: #d4edda"

def make_bar(df: pd.DataFrame, title: str):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df["Domain"], df["Score"])
    ax.set_title(title)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)

def make_gender_bar(df: pd.DataFrame, title: str):
    doms = [d for d in PASS_DOMAINS_NUM if d in df.columns]
    boys = df[df["Category"] == "Boys"][doms].iloc[0]
    girls = df[df["Category"] == "Girls"][doms].iloc[0]
    overall = df[df["Category"] == "Overall"][doms].iloc[0]
    x = np.arange(len(doms))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(x - 0.25, boys, width=0.25, label="Boys")
    ax.bar(x, girls, width=0.25, label="Girls")
    ax.bar(x + 0.25, overall, width=0.25, label="Overall")
    ax.set_xticks(x)
    ax.set_xticklabels(doms, rotation=45, ha="right")
    ax.set_ylim(0, 100)
    ax.set_title(title)
    ax.legend()
    st.pyplot(fig)

def format_insights(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    if df.empty:
        return [], []
    top2 = df.sort_values("Score", ascending=False).head(2)
    bot2 = df.sort_values("Score", ascending=True).head(2)
    strengths = [f"- {r.Domain} ({r.Score:.1f})" for r in top2.itertuples()]
    concerns = [f"- {r.Domain} ({r.Score:.1f})" for r in bot2.itertuples()]
    return strengths, concerns

def gender_insights(df: pd.DataFrame) -> List[str]:
    insights = []
    if df.empty:
        return insights
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

# ----------------- Sidebar uploads -----------------
st.sidebar.header("📁 Upload PASS workbooks (G6, G7, G8)")
uploaded = {g: st.sidebar.file_uploader(f"{g} (.xlsx)", type=["xlsx"], key=f"u_{g}") for g in PASS_FILES}

parsed_cohort: Dict[str, pd.DataFrame] = {}
parsed_profiles: Dict[str, pd.DataFrame] = {}
parsed_items: Dict[str, pd.DataFrame] = {}

for grade in PASS_FILES:
    src = uploaded[grade]
    if src is None:
        parsed_cohort[grade] = pd.DataFrame()
        parsed_profiles[grade] = pd.DataFrame()
        parsed_items[grade] = pd.DataFrame()
        continue
    sheets = list_sheets(src)
    sh_cohort = choose_sheet(sheets, SHEET_HINTS["cohort"])
    sh_profiles = choose_sheet(sheets, SHEET_HINTS["profiles"])
    sh_items = choose_sheet(sheets, SHEET_HINTS["items"])
    try:
        parsed_cohort[grade] = parse_cohort_sheet(src, sh_cohort)
    except Exception:
        parsed_cohort[grade] = pd.DataFrame()
    try:
        parsed_profiles[grade] = parse_individual_profiles(src, sh_profiles)
    except Exception:
        parsed_profiles[grade] = pd.DataFrame()
    try:
        parsed_items[grade] = parse_item_level(src, sh_items)
    except Exception:
        parsed_items[grade] = pd.DataFrame()

# ----------------- UI -----------------
st.title("🧭 OIS PASS Dashboard")

tab_gl, tab_hrt, tab_compare = st.tabs([
    "🧑‍💼 GL View",
    "🧑‍🏫 HRT View",
    "📊 Cross-Grade Compare",
])

with tab_gl:
    gsel = st.selectbox("Select Grade (GL View)", list(PASS_FILES.keys()))
    df = parsed_cohort.get(gsel, pd.DataFrame())
    if not df.empty:
        st.subheader("Cohort Analysis")
        show = df.copy()
        show["Status"] = show["Score"].apply(lambda x: "🟥" if x < 60 else "🟧" if x < 70 else "🟩")
        st.dataframe(show, hide_index=True, use_container_width=True)
        make_bar(df, f"{gsel}: PASS Domains")

        strengths, concerns = format_insights(df)
        st.markdown("### 🔎 Insights (Cohort)")
        if strengths:
            st.success("**Strengths**\\n" + "\\n".join(strengths))
        if concerns:
            st.warning("**Concerns**\\n" + "\\n".join(concerns))

        st.markdown("### ✅ Actionable Strategies")
        domain_strategies(df)

        st.subheader("Cluster Analysis (Cohort)")
        cdf = cluster_scores(df)
        st.dataframe(cdf, use_container_width=True)
        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel}: Cluster Scores")
        top, bot = format_insights(cdf.rename(columns={"Cluster": "Domain"}))
        if top:
            st.success("**Cluster Strengths**\\n" + "\\n".join(top))
        if bot:
            st.warning("**Cluster Concerns**\\n" + "\\n".join(bot))

    dfi = parsed_items.get(gsel, pd.DataFrame())
    if not dfi.empty:
        st.subheader("Gender Split Analysis")
        view = dfi[dfi["Category"].isin(["Overall", "Boys", "Girls"])]
        st.dataframe(view, use_container_width=True)
        make_gender_bar(view, f"{gsel}: Gender Comparison")
        insights = gender_insights(view)
        if insights:
            st.info("**Gender Gaps**\\n" + "\\n".join(insights))

with tab_hrt:
    gsel = st.selectbox("Select Grade (HRT View)", list(PASS_FILES.keys()))
    dfp = parsed_profiles.get(gsel, pd.DataFrame())
    if dfp.empty:
        st.warning("No profiles data uploaded for this grade.")
    else:
        classes = sorted(set(dfp["Group"].dropna().unique()))
        csel = st.selectbox("Select HR class", classes)
        class_df = dfp[dfp["Group"] == csel]
        dom_cols = [d for d in PASS_DOMAINS_NUM if d in class_df.columns]
        class_means = class_df[dom_cols].mean().reset_index()
        class_means.columns = ["Domain", "Score"]

        st.subheader(f"{gsel} {csel}: Class Analysis")
        st.dataframe(class_means, use_container_width=True)

        strengths, concerns = format_insights(class_means)
        st.markdown("### 🔎 Insights (Class)")
        if strengths:
            st.success("**Strengths**\\n" + "\\n".join(strengths))
        if concerns:
            st.warning("**Concerns**\\n" + "\\n".join(concerns))

        st.markdown("### ✅ Actionable Strategies")
        domain_strategies(class_means)

        st.markdown("### 🚩 Flagged Students")
        class_df["# Weak Domains"] = (class_df[dom_cols] < 60).sum(axis=1)
        flagged = class_df[class_df["# Weak Domains"] >= 2]
        if not flagged.empty:
            styled = flagged[["Forename", "Surname", "Group", "# Weak Domains"] + dom_cols].style.applymap(
                color_for_score, subset=dom_cols
            )
            st.dataframe(styled, use_container_width=True)
        else:
            st.success("No flagged students in this HR class.")

        st.subheader(f"{gsel} {csel}: Cluster Analysis")
        cdf = cluster_scores(class_means.rename(columns={"Domain": "Domain"}))
        st.dataframe(cdf, use_container_width=True)
        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel} {csel}: Cluster Scores")
        top, bot = format_insights(cdf.rename(columns={"Cluster": "Domain"}))
        if top:
            st.success("**Cluster Strengths**\\n" + "\\n".join(top))
        if bot:
            st.warning("**Cluster Concerns**\\n" + "\\n".join(bot))

        if "Gender" in class_df.columns:
            st.subheader("Gender Split Analysis (Class-level)")
            view = class_df.groupby("Gender")[dom_cols].mean().reset_index()
            st.dataframe(view, use_container_width=True)

    dfi = parsed_items.get(gsel, pd.DataFrame())
    if not dfi.empty:
        st.subheader("Gender Split Analysis (Grade-level)")
        view = dfi[dfi["Category"].isin(["Overall", "Boys", "Girls"])]
        st.dataframe(view, use_container_width=True)
        make_gender_bar(view, f"{gsel}: Gender Comparison")
        insights = gender_insights(view)
        if insights:
            st.info("**Gender Gaps**\\n" + "\\n".join(insights))

with tab_compare:
    st.subheader("Cross-Grade Comparison (Cohort)")
    by_grade = {g: d for g, d in parsed_cohort.items() if isinstance(d, pd.DataFrame) and not d.empty}
    if by_grade:
        domains = PASS_DOMAINS_NUM
        mats, grades = [], []
        for g, df in by_grade.items():
            ser = df.set_index("Domain")["Score"].reindex(domains)
            mats.append(ser.values)
            grades.append(g)

        M = np.column_stack(mats) if mats else np.zeros((len(domains), 0))
        fig, ax = plt.subplots()
        im = ax.imshow(M, aspect="auto", vmin=0, vmax=100)
        ax.set_yticks(range(len(domains)))
        ax.set_yticklabels(domains)
        ax.set_xticks(range(len(grades)))
        ax.set_xticklabels(grades)
        ax.set_title("PASS Domain Heatmap (by Grade)")
        fig.colorbar(im, ax=ax)
        st.pyplot(fig)

        rows = []
        for g, df in by_grade.items():
            tmp = df.copy()
            tmp["Grade"] = g
            rows.append(tmp)
        pivot = pd.concat(rows).pivot_table(index="Domain", columns="Grade", values="Score")
        st.dataframe(pivot.reindex(PASS_DOMAINS_NUM), use_container_width=True)
    else:
        st.info("No cohort data parsed to compare across grades.")
