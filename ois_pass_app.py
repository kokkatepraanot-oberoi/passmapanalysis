
# ois_pass_app.py
# Streamlit PASS Dashboard – GL + HRT with class-level insights and auto-flag

import io
from datetime import datetime
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
THRESHOLDS = {"red": 60.0, "amber": 70.0}

SHEET_HINTS = {
    "cohort": ["cohort analysis"],
    "profiles": ["individual profiles", "student profiles"],
    "items": ["item level analysis", "item-level analysis"],
    "cohort_pct": ["cohort - mean percentages", "mean percentages"],
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
    n = None
    for r in range(min(15, len(raw))):
        row = [_clean(x) for x in raw.iloc[r].values]
        if any(x.lower() == "frequency" for x in row):
            nums = [x for x in row if str(x).replace('.','',1).isdigit()]
            if nums:
                try: n = int(float(nums[-1]))
                except: pass
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
        return df, n
    return pd.DataFrame(columns=["Domain","Score"]), n

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
    keep = [c for c in ["UPN","Forename","Surname","Group","Year"] if c in df.columns]
    for dom in PASS_DOMAINS:
        if dom in df.columns: keep.append(dom)
    return df[keep] if keep else pd.DataFrame()

def color_for_score(x: float) -> str:
    if pd.isna(x): return "🟦"
    if x < THRESHOLDS["red"]: return "🟥"
    if x < THRESHOLDS["amber"]: return "🟧"
    return "🟩"

def make_bar_compare(df_class: pd.DataFrame, df_grade: pd.DataFrame, title: str):
    domains = PASS_DOMAINS
    c = df_class.set_index("Domain")["Score"].reindex(domains)
    g = df_grade.set_index("Domain")["Score"].reindex(domains)
    x = np.arange(len(domains))
    fig, ax = plt.subplots(figsize=(10,4))
    ax.bar(x-0.2, c, width=0.4, label="Class")
    ax.bar(x+0.2, g, width=0.4, label="Grade")
    ax.set_xticks(x); ax.set_xticklabels(domains, rotation=45, ha="right")
    ax.set_ylim(0,100)
    ax.set_title(title)
    ax.legend()
    st.pyplot(fig)

def make_insights(df: pd.DataFrame, label: str, n: Optional[int] = None):
    if df.empty: return "No data."
    top2 = df.sort_values("Score", ascending=False).head(2)
    bot2 = df.sort_values("Score", ascending=True).head(2)
    parts = []
    if n is not None: parts.append(f"{label}: {n} respondents.")
    parts.append("**Strengths:** " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in top2.itertuples()))
    parts.append("**Concerns:** " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in bot2.itertuples()))
    flags = df[df["Score"] < THRESHOLDS["amber"]]
    if not flags.empty:
        parts.append("**Watchlist (≤70):** " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in flags.sort_values("Score").itertuples()))
    return "\n".join(parts)

def actions_gl(df: pd.DataFrame) -> List[str]:
    if df.empty: return ["No data available."]
    idx = df.set_index("Domain")["Score"]
    a = []
    if "Attitudes to teachers" in idx and idx["Attitudes to teachers"] < THRESHOLDS["amber"]:
        a.append("📌 Run grade-wide teacher–student relationship initiatives.")
    if "Preparedness for learning" in idx and idx["Preparedness for learning"] < THRESHOLDS["amber"]:
        a.append("📌 Organise study-skills workshops across the grade.")
    if "Response to curriculum demands" in idx and idx["Response to curriculum demands"] < THRESHOLDS["amber"]:
        a.append("📌 Meet HoDs to audit workload and assessment spread.")
    if "Confidence in learning" in idx and idx["Confidence in learning"] < THRESHOLDS["amber"]:
        a.append("📌 Focus on growth mindset assemblies.")
    return a or ["Maintain strengths and monitor until next PASS."]

def actions_hrt(df: pd.DataFrame) -> List[str]:
    if df.empty: return ["No data available."]
    idx = df.set_index("Domain")["Score"]
    a = []
    if "Feelings about school" in idx and idx["Feelings about school"] < THRESHOLDS["amber"]:
        a.append("📌 Strengthen bonding and belonging activities in HR time.")
    if "General work ethic" in idx and idx["General work ethic"] < THRESHOLDS["amber"]:
        a.append("📌 Reinforce routines: planner checks, visible goal trackers.")
    if "Attitudes to attendance" in idx and idx["Attitudes to attendance"] < THRESHOLDS["amber"]:
        a.append("📌 Monitor attendance closely and involve parents early.")
    if "Attitudes to teachers" in idx and idx["Attitudes to teachers"] < THRESHOLDS["amber"]:
        a.append("📌 Build stronger individual relationships with students.")
    return a or ["Sustain current practices; recognise positives."]

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
st.caption("Cohort + Class + Student-level PASS analysis with insights and actionable points.")

tab_gl, tab_hrt = st.tabs([
    "🧑‍💼 GL View",
    "🧑‍🏫 HRT View",
])

with tab_gl:
    st.subheader("Grade Leaders – Cohort Analysis")
    for grade in PASS_FILES:
        df, n = parsed_cohort.get(grade, (pd.DataFrame(), None))
        if not df.empty:
            show = df.copy(); show["Status"] = show["Score"].apply(color_for_score)
            st.dataframe(show, hide_index=True, use_container_width=True)
            make_bar_compare(df, df, f"{grade}: PASS Domains")
            st.markdown("### 🔎 Insights")
            st.info(make_insights(df, grade, n))
            st.markdown("### ✅ Actionable Points")
            for a in actions_gl(df): st.write(a)
        else:
            st.warning(f"No cohort data for {grade}")

with tab_hrt:
    st.subheader("Homeroom Teachers – Class Analysis")
    gsel = st.selectbox("Select grade", list(PASS_FILES.keys()))
    dfp = parsed_profiles.get(gsel, pd.DataFrame())
    if dfp.empty:
        st.warning("No profiles data uploaded for this grade.")
    else:
        classes = sorted(dfp["Group"].dropna().unique())
        csel = st.selectbox("Select HR class", classes)
        # class averages
        class_df = dfp[dfp["Group"] == csel]
        class_means = class_df[PASS_DOMAINS].mean().reset_index()
        class_means.columns = ["Domain","Score"]
        grade_df, _ = parsed_cohort.get(gsel, (pd.DataFrame(), None))
        if not grade_df.empty:
            comp = class_means.merge(grade_df,on="Domain",suffixes=("_Class","_Grade"))
            st.dataframe(comp, use_container_width=True)
            make_bar_compare(class_means, grade_df, f"{gsel} {csel}: Class vs Grade")
            st.markdown("### 🔎 Insights")
            diffs = comp.assign(Diff=comp["Score_Class"]-comp["Score_Grade"])
            weaker = diffs.nsmallest(2,"Diff")
            stronger = diffs.nlargest(2,"Diff")
            txt = []
            txt.append(f"{csel} is weaker than {gsel} in: " + ", ".join(f"{r.Domain} ({r.Diff:.1f})" for r in weaker.itertuples()))
            txt.append(f"{csel} is stronger than {gsel} in: " + ", ".join(f"{r.Domain} ({r.Diff:.1f})" for r in stronger.itertuples()))
            st.info("\n".join(txt))
            st.markdown("### ✅ Actionable Points")
            for a in actions_hrt(class_means): st.write(a)
            # flagged students
            st.markdown("### 🚩 Flagged Students")
            dom_cols = [d for d in PASS_DOMAINS if d in class_df.columns]
            class_df["# Weak Domains"] = (class_df[dom_cols] < 60).sum(axis=1)
            flagged = class_df[class_df["# Weak Domains"] >= 2]
            if not flagged.empty:
                st.dataframe(flagged[["Forename","Surname","Group","# Weak Domains"]+dom_cols], use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w:
                    flagged.to_excel(w,index=False)
                st.download_button("⬇️ Download flagged students", out.getvalue(), file_name=f"{gsel}_{csel}_Flagged.xlsx")
            else:
                st.success("No students flagged in this HR class.")
