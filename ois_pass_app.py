
# ois_pass_app.py
# Streamlit PASS Dashboard – Enhanced with dropdowns, bullet insights, color-coded flagged students, numbered domains, and Cross-Grade Compare

import io
from typing import Dict, Tuple, Optional, List

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

SHEET_HINTS = {
    "cohort": ["cohort analysis"],
    "profiles": ["individual profiles", "student profiles"],
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
def parse_cohort_sheet(src, sheet_name: Optional[str]) -> Tuple[pd.DataFrame, Optional[int]]:
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
        return df, None
    return pd.DataFrame(columns=["Domain","Score"]), None

def parse_individual_profiles(src, sheet_name: Optional[str]) -> pd.DataFrame:
    raw = pd.read_excel(src, sheet_name=sheet_name, header=None)
    header_row = None
    for r in range(min(30, len(raw))):
        vals = [_clean(x).lower() for x in raw.iloc[r].values]
        if "upn" in vals and (any("forename" in v for v in vals) or any("first" in v for v in vals)):
            header_row = r; break
    if header_row is not None:
        df = pd.read_excel(src, sheet_name=sheet_name, header=header_row)
    else:
        df = pd.read_excel(src, sheet_name=sheet_name)
    rename_map = {}
    for col in df.columns:
        c = _norm(col)
        if "forename" in c or "first name" in c: rename_map[col] = "Forename"
        elif "surname" in c or "last name" in c: rename_map[col] = "Surname"
        elif c == "upn": rename_map[col] = "UPN"
        elif c.startswith("group"): rename_map[col] = "Group"
        elif "year" in c: rename_map[col] = "Year"
    df = df.rename(columns=rename_map)
    for dom in PASS_DOMAINS:
        if dom in df.columns: df = df.rename(columns={dom: DOMAIN_MAP[dom]})
    return df

def color_for_score(x: float) -> str:
    if pd.isna(x): return ""
    if x < THRESHOLDS["red"]: return "background-color: #f8d7da"  # red
    if x < THRESHOLDS["amber"]: return "background-color: #fff3cd" # amber
    return "background-color: #d4edda"                            # green

def make_bar(df: pd.DataFrame, title: str):
    fig, ax = plt.subplots(figsize=(8,4))
    ax.bar(df["Domain"], df["Score"])
    ax.set_title(title); ax.set_ylabel("Score"); ax.set_ylim(0,100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)

def format_insights(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    if df.empty: return [], []
    top2 = df.sort_values("Score", ascending=False).head(2)
    bot2 = df.sort_values("Score", ascending=True).head(2)
    strengths = [f"- {r.Domain} ({r.Score:.1f})" for r in top2.itertuples()]
    concerns = [f"- {r.Domain} ({r.Score:.1f})" for r in bot2.itertuples()]
    return strengths, concerns

# ----------------- Sidebar uploads -----------------
st.sidebar.header("📁 Upload PASS workbooks (G6, G7, G8)")
uploaded = {g: st.sidebar.file_uploader(f"{g} (.xlsx)", type=["xlsx"], key=f"u_{g}") for g in PASS_FILES}

parsed_cohort: Dict[str, Tuple[pd.DataFrame, Optional[int]]] = {}
parsed_profiles: Dict[str, pd.DataFrame] = {}

for grade in PASS_FILES:
    src = uploaded[grade]
    if src is None:
        parsed_cohort[grade] = (pd.DataFrame(), None)
        parsed_profiles[grade] = pd.DataFrame()
        continue
    sheets = list_sheets(src)
    sh_cohort = choose_sheet(sheets, SHEET_HINTS["cohort"])
    sh_profiles = choose_sheet(sheets, SHEET_HINTS["profiles"])
    try: df_c, n = parse_cohort_sheet(src, sh_cohort)
    except Exception: df_c, n = (pd.DataFrame(), None)
    parsed_cohort[grade] = (df_c.assign(Grade=grade) if not df_c.empty else df_c, n)
    try: df_p = parse_individual_profiles(src, sh_profiles) if sh_profiles else pd.DataFrame()
    except Exception: df_p = pd.DataFrame()
    parsed_profiles[grade] = df_p

# ----------------- UI -----------------
st.title("🧭 OIS PASS Dashboard")

tab_gl, tab_hrt, tab_compare = st.tabs([
    "🧑‍💼 GL View",
    "🧑‍🏫 HRT View",
    "📊 Cross-Grade Compare",
])

with tab_gl:
    gsel = st.selectbox("Select Grade (GL View)", list(PASS_FILES.keys()))
    df, n = parsed_cohort.get(gsel, (pd.DataFrame(), None))
    if not df.empty:
        show = df.copy(); show["Status"] = show["Score"].apply(lambda x: "🟥" if x<60 else "🟧" if x<70 else "🟩")
        st.dataframe(show, hide_index=True, use_container_width=True)
        make_bar(df, f"{gsel}: PASS Domains")
        strengths, concerns = format_insights(df)
        st.markdown("### 🔎 Insights")
        if strengths: st.success("**Strengths**\n" + "\n".join(strengths))
        if concerns: st.warning("**Concerns**\n" + "\n".join(concerns))

with tab_hrt:
    gsel = st.selectbox("Select Grade (HRT View)", list(PASS_FILES.keys()))
    dfp = parsed_profiles.get(gsel, pd.DataFrame())
    if dfp.empty:
        st.warning("No profiles data uploaded for this grade.")
    else:
        classes = sorted(dfp["Group"].dropna().unique())
        csel = st.selectbox("Select HR class", classes)
        class_df = dfp[dfp["Group"] == csel]
        class_means = class_df[PASS_DOMAINS_NUM].mean().reset_index()
        class_means.columns = ["Domain","Score"]
        grade_df, _ = parsed_cohort.get(gsel, (pd.DataFrame(), None))
        if not grade_df.empty:
            comp = class_means.merge(grade_df,on="Domain",suffixes=("_Class","_Grade"))
            st.dataframe(comp, use_container_width=True)
            strengths, concerns = format_insights(class_means)
            st.markdown("### 🔎 Insights")
            if strengths: st.success("**Strengths**\n" + "\n".join(strengths))
            if concerns: st.warning("**Concerns**\n" + "\n".join(concerns))
            st.markdown("### 🚩 Flagged Students")
            dom_cols = [d for d in PASS_DOMAINS_NUM if d in class_df.columns]
            class_df["# Weak Domains"] = (class_df[dom_cols] < 60).sum(axis=1)
            flagged = class_df[class_df["# Weak Domains"] >= 2]
            if not flagged.empty:
                styled = flagged[["Forename","Surname","Group","# Weak Domains"]+dom_cols].style.applymap(color_for_score, subset=dom_cols)
                st.dataframe(styled, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w:
                    flagged.to_excel(w,index=False)
                st.download_button("⬇️ Download flagged students", out.getvalue(), file_name=f"{gsel}_{csel}_Flagged.xlsx")
            else:
                st.success("No students flagged in this HR class.")

with tab_compare:
    st.subheader("Cross-Grade Comparison (Cohort)")
    by_grade = {g:d for g,(d,_) in parsed_cohort.items() if isinstance(d, pd.DataFrame) and not d.empty}
    if by_grade:
        domains = PASS_DOMAINS_NUM
        mats, grades = [], []
        for g, df in by_grade.items():
            ser = df.set_index("Domain")["Score"].reindex(domains)
            mats.append(ser.values); grades.append(g)
        M = np.column_stack(mats) if mats else np.zeros((len(domains), 0))
        fig, ax = plt.subplots()
        im = ax.imshow(M, aspect="auto", vmin=0, vmax=100)
        ax.set_yticks(range(len(domains))); ax.set_yticklabels(domains)
        ax.set_xticks(range(len(grades))); ax.set_xticklabels(grades)
        ax.set_title("PASS Domain Heatmap (by Grade)")
        fig.colorbar(im, ax=ax)
        st.pyplot(fig)
        rows = []
        for g, df in by_grade.items():
            tmp = df.copy(); tmp["Grade"] = g; rows.append(tmp)
        pivot = pd.concat(rows, ignore_index=True)
        pivot = pivot.pivot(index="Domain", columns="Grade", values="Score")
        st.dataframe(pivot.reindex(PASS_DOMAINS_NUM), use_container_width=True)
    else:
        st.info("No cohort data parsed to compare.")
