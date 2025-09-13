
# ois_pass_app.py
# Streamlit PASS Dashboard (GL + HRT + Profiles + Item-Level) with automatic sheet parsing
# Run: streamlit run ois_pass_app.py

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
    "cohort_pct": ["cohort - mean percentages", "mean percentages"],
    "profiles": ["individual profiles", "student profiles"],
    "items": ["item level analysis", "item-level analysis"],
}

# =============== Helpers ===============
def _clean(s):
    if pd.isna(s):
        return ""
    return str(s).strip()

def _norm_sheet_name(name: str) -> str:
    return _clean(name).lower().replace("_", " ").replace("-", " ")

def list_sheets(file_or_buffer) -> List[str]:
    try:
        return pd.ExcelFile(file_or_buffer).sheet_names
    except Exception:
        return []

def choose_sheet(sheet_names: List[str], hints: List[str]) -> Optional[str]:
    names_norm = {n: _norm_sheet_name(n) for n in sheet_names}
    for n, norm in names_norm.items():
        for h in hints:
            if h in norm:
                return n
    # fallback: first sheet if nothing matches
    return sheet_names[0] if sheet_names else None

# ---------- Parsers ----------
def parse_cohort_sheet(file_or_buffer, sheet_name: Optional[str]) -> Tuple[pd.DataFrame, Optional[int]]:
    raw = pd.read_excel(file_or_buffer, sheet_name=sheet_name, header=None)
    # detect respondents (Frequency)
    n = None
    for r in range(min(15, len(raw))):
        row = [_clean(x) for x in raw.iloc[r].values]
        if any(x.lower() == "frequency" for x in row):
            nums = [x for x in row if str(x).replace('.', '', 1).isdigit()]
            if nums:
                try:
                    n = int(float(nums[-1]))
                except Exception:
                    pass
    # wide header then values next row
    header_row = None
    for r in range(min(15, len(raw))):
        vals = [_clean(x) for x in raw.iloc[r].values]
        hits = [i for i, v in enumerate(vals) if v in PASS_DOMAINS]
        if len(hits) >= 5:
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
                except Exception:
                    continue
        df = pd.Series(data).rename_axis("Domain").reset_index(name="Score")
        return df, n
    # fallback: scan rows
    rows = []
    for r in range(len(raw)):
        row = raw.iloc[r].values
        for c in range(min(6, raw.shape[1])):
            dom = _clean(row[c] if c < len(row) else "")
            if dom in PASS_DOMAINS:
                # first numeric to right
                val = None
                for c2 in range(c+1, raw.shape[1]):
                    v = row[c2]
                    if isinstance(v, (int,float)) and not pd.isna(v):
                        val = float(v); break
                    try:
                        val = float(str(v)); break
                    except Exception:
                        pass
                if val is not None:
                    rows.append({"Domain": dom, "Score": val})
    return (pd.DataFrame(rows).drop_duplicates(subset=["Domain"]), n) if rows else (pd.DataFrame(columns=["Domain","Score"]), n)

def parse_cohort_mean_pct(file_or_buffer, sheet_name: Optional[str]) -> pd.DataFrame:
    try:
        raw = pd.read_excel(file_or_buffer, sheet_name=sheet_name, header=None)
    except Exception:
        return pd.DataFrame(columns=["Domain", "Score"])
    # attempt same pattern as cohort
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
                except Exception: pass
        return pd.Series(data).rename_axis("Domain").reset_index(name="Score")
    return pd.DataFrame(columns=["Domain","Score"])

def parse_individual_profiles(file_or_buffer, sheet_name: Optional[str]) -> pd.DataFrame:
    # Read with headers guessed from first non-empty row that contains 'UPN' or 'Forename'
    df = pd.read_excel(file_or_buffer, sheet_name=sheet_name)
    # standardise col names
    rename_map = {}
    for col in df.columns:
        c = _norm_sheet_name(col)
        if "forename" in c or "firstname" in c or "first name" in c: rename_map[col] = "Forename"
        elif "surname" in c or "last name" in c: rename_map[col] = "Surname"
        elif c == "upn": rename_map[col] = "UPN"
        elif c == "group": rename_map[col] = "Group"
        elif "year" in c: rename_map[col] = "Year"
    df = df.rename(columns=rename_map)
    # keep known columns
    keep = [c for c in ["UPN","Forename","Surname","Group","Year"] if c in df.columns]
    for dom in PASS_DOMAINS:
        if dom in df.columns:
            keep.append(dom)
    df = df[keep] if keep else pd.DataFrame(columns=["UPN","Forename","Surname","Group","Year"]+PASS_DOMAINS)
    return df

def parse_item_level(file_or_buffer, sheet_name: Optional[str]) -> pd.DataFrame:
    raw = pd.read_excel(file_or_buffer, sheet_name=sheet_name)
    # Expect columns like Category, Frequency, Q1..Q56 (some exports have 50+ items)
    cols = [c for c in raw.columns]
    # normalise Category/Frequency
    cat_col = next((c for c in cols if _norm_sheet_name(c).startswith("category")), None)
    freq_col = next((c for c in cols if _norm_sheet_name(c).startswith("frequency")), None)
    # find Q columns
    q_cols = [c for c in cols if _norm_sheet_name(c).startswith("q")]
    if not q_cols:
        # sometimes Qs start after a blank block—try from row 0 to detect 'Q1' style headers
        raw2 = pd.read_excel(file_or_buffer, sheet_name=sheet_name, header=None)
        header_row = None
        for r in range(min(10, len(raw2))):
            vals = [_clean(x) for x in raw2.iloc[r].values]
            if any(v.lower().startswith("q1") for v in vals if isinstance(v, str)):
                header_row = r; break
        if header_row is not None:
            raw = pd.read_excel(file_or_buffer, sheet_name=sheet_name, header=header_row)
            cols = [c for c in raw.columns]
            cat_col = next((c for c in cols if _norm_sheet_name(c).startswith("category")), None)
            freq_col = next((c for c in cols if _norm_sheet_name(c).startswith("frequency")), None)
            q_cols = [c for c in cols if _norm_sheet_name(c).startswith("q")]
    if not q_cols or cat_col is None:
        return pd.DataFrame()
    keep_cols = [cat_col] + ([freq_col] if freq_col in cols else []) + q_cols
    df = raw[keep_cols].rename(columns={cat_col:"Category", **({freq_col:"Frequency"} if freq_col in cols else {})})
    return df

def color_for_score(x: float) -> str:
    if pd.isna(x): return "🟦"
    if x < THRESHOLDS["red"]: return "🟥"
    if x < THRESHOLDS["amber"]: return "🟧"
    return "🟩"

def make_bar(df: pd.DataFrame, title: str):
    fig, ax = plt.subplots()
    ax.bar(df["Domain"], df["Score"])
    ax.set_title(title); ax.set_ylabel("Score"); ax.set_ylim(0, 100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)

def make_heatmap_domain(by_grade: Dict[str, pd.DataFrame]):
    domains = PASS_DOMAINS
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

def narrative(df: pd.DataFrame, grade: str, n: Optional[int]) -> str:
    if df.empty: return f"No data parsed for {grade}."
    top2 = df.sort_values("Score", ascending=False).head(2)
    bot2 = df.sort_values("Score", ascending=True).head(2)
    parts = []
    if n is not None: parts.append(f"{grade}: {n} respondents.")
    parts.append("Strengths → " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in top2.itertuples()))
    parts.append("Concerns → " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in bot2.itertuples()))
    flags = df[df["Score"] < THRESHOLDS["amber"]]
    if not flags.empty:
        parts.append("Watchlist (≤70): " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in flags.sort_values("Score").itertuples()))
    return "\n".join(parts)

def actions_gl(df: pd.DataFrame) -> List[str]:
    a = []
    if df.empty: return ["No data available."]
    idx = df.set_index("Domain")["Score"]
    if "Attitudes to teachers" in idx and idx["Attitudes to teachers"] < THRESHOLDS["amber"]:
        a.append("Run grade-wide teacher–student relationship initiatives (advisory check-ins, mentor matching).")
    if "Preparedness for learning" in idx and idx["Preparedness for learning"] < THRESHOLDS["amber"]:
        a.append("Study-skills workshop: planners, routines, goal-setting; share resources with HRTs.")
    if "Response to curriculum demands" in idx and idx["Response to curriculum demands"] < THRESHOLDS["amber"]:
        a.append("Meet HoDs: audit workload, scaffolds, differentiation. Sequence assessments more evenly.")
    if "Confidence in learning" in idx and idx["Confidence in learning"] < THRESHOLDS["amber"]:
        a.append("Assembly focus on growth mindset; celebrate small wins and progress evidence.")
    if not a: a.append("Maintain strengths; monitor until next PASS.")
    return a

def actions_hrt(df: pd.DataFrame) -> List[str]:
    a = []
    if df.empty: return ["No data available."]
    idx = df.set_index("Domain")["Score"]
    if "Feelings about school" in idx and idx["Feelings about school"] < THRESHOLDS["amber"]:
        a.append("Bonding & belonging: circles, peer shout-outs, advisory games.")
    if "General work ethic" in idx and idx["General work ethic"] < THRESHOLDS["amber"]:
        a.append("Introduce weekly routines: planner checks, Do Now, visible goal trackers.")
    if "Attitudes to attendance" in idx and idx["Attitudes to attendance"] < THRESHOLDS["amber"]:
        a.append("Track absences/tardies, early family contact, communicate attendance value.")
    if "Attitudes to teachers" in idx and idx["Attitudes to teachers"] < THRESHOLDS["amber"]:
        a.append("Increase 1:1 check-ins; positive calls/emails home to build trust.")
    if not a: a.append("Sustain current practices; recognise positive trends in class meetings.")
    return a

# =============== Sidebar: uploads ===============
st.sidebar.header("📁 Upload PASS workbooks for each grade")
uploaded = {g: st.sidebar.file_uploader(f"{g} (.xlsx)", type=["xlsx"], key=f"u_{g}") for g in PASS_FILES.keys()}

# Load sheets for each grade, detect target sheets by name hints
parsed_cohort: Dict[str, Tuple[pd.DataFrame, Optional[int]]] = {}
parsed_profiles: Dict[str, pd.DataFrame] = {}
parsed_items: Dict[str, pd.DataFrame] = {}
parsed_cohort_pct: Dict[str, pd.DataFrame] = {}

for grade, default in PASS_FILES.items():
    source = uploaded[grade] if uploaded[grade] is not None else default
    try:
        sheets = list_sheets(source)
    except Exception:
        sheets = []
    # choose sheets by hints
    sh_cohort = choose_sheet(sheets, SHEET_HINTS["cohort"]) if sheets else None
    sh_pct = choose_sheet(sheets, SHEET_HINTS["cohort_pct"]) if sheets else None
    sh_profiles = choose_sheet(sheets, SHEET_HINTS["profiles"]) if sheets else None
    sh_items = choose_sheet(sheets, SHEET_HINTS["items"]) if sheets else None

    # parse
    try:
        df_c, n = parse_cohort_sheet(source, sh_cohort)
    except Exception:
        df_c, n = (pd.DataFrame(), None)
    parsed_cohort[grade] = (df_c.assign(Grade=grade) if not df_c.empty else df_c, n)

    try:
        df_pct = parse_cohort_mean_pct(source, sh_pct) if sh_pct else pd.DataFrame()
    except Exception:
        df_pct = pd.DataFrame()
    parsed_cohort_pct[grade] = df_pct.assign(Grade=grade) if not df_pct.empty else df_pct

    try:
        df_p = parse_individual_profiles(source, sh_profiles) if sh_profiles else pd.DataFrame()
    except Exception:
        df_p = pd.DataFrame()
    parsed_profiles[grade] = df_p

    try:
        df_i = parse_item_level(source, sh_items) if sh_items else pd.DataFrame()
    except Exception:
        df_i = pd.DataFrame()
    parsed_items[grade] = df_i

# =============== Top summary ===============
st.title("🧭 OIS PASS Dashboard")
st.caption("Auto-parsed: Cohort, Individual Profiles, Item-Level. Optional QA from 'Cohort - Mean Percentages' if present.")

cols = st.columns(4)
grades_loaded = sum(1 for g,(d,_) in parsed_cohort.items() if isinstance(d, pd.DataFrame) and not d.empty)
cols[0].metric("Grades parsed (Cohort)", f"{grades_loaded}/3")
resp = {g:n for g,(d,n) in parsed_cohort.items() if n is not None}
cols[1].metric("Respondents", ", ".join(f"{g}: {n}" for g,n in resp.items()) if resp else "n/a")
pct_present = sum(1 for g,d in parsed_cohort_pct.items() if isinstance(d, pd.DataFrame) and not d.empty)
cols[2].metric("'Mean %' sheets found", f"{pct_present}/3")
cols[3].metric("Generated", datetime.now().strftime("%d %b %Y, %H:%M"))

# =============== Tabs ===============
tab_gl, tab_hrt, tab_profiles, tab_items, tab_compare = st.tabs([
    "🧑‍💼 GL View (Cohort)",
    "🧑‍🏫 HRT View",
    "🧍 Individual Profiles",
    "🧩 Item-Level Analysis",
    "📊 Cross-Grade Compare",
])

# ----- GL View -----
with tab_gl:
    st.subheader("Grade Leaders (Cohort Analysis)")
    for grade in PASS_FILES.keys():
        df, n = parsed_cohort.get(grade, (pd.DataFrame(), None))
        st.markdown(f"### {grade}")
        if isinstance(df, pd.DataFrame) and not df.empty:
            show = df.copy()
            show["Status"] = show["Score"].apply(color_for_score)
            st.dataframe(show[["Domain","Score","Status"]], hide_index=True, use_container_width=True)
            make_bar(df, f"{grade}: PASS Domains")
            st.markdown("**Insights**")
            st.write(narrative(df, grade, n))
            st.markdown("**Actionable Points for GLs**")
            for a in actions_gl(df): st.write(f"- {a}")
            # QA check vs Cohort - Mean Percentages if available
            qa = parsed_cohort_pct.get(grade)
            if isinstance(qa, pd.DataFrame) and not qa.empty:
                merged = df.merge(qa[["Domain","Score"]].rename(columns={"Score":"Mean % (sheet)"}), on="Domain", how="left")
                merged["Δ (Cohort - Mean %)"] = merged["Score"] - merged["Mean % (sheet)"]
                st.caption("QA: Cohort vs 'Cohort - Mean Percentages'")
                st.dataframe(merged, use_container_width=True)
        else:
            st.info("No cohort data parsed.")
        st.divider()

# ----- HRT View (uses cohort until class-level available) -----
with tab_hrt:
    st.subheader("Homeroom Teachers (by Grade)")
    gsel = st.selectbox("Select grade", list(PASS_FILES.keys()))
    df, _ = parsed_cohort.get(gsel, (pd.DataFrame(), None))
    if isinstance(df, pd.DataFrame) and not df.empty:
        show = df.copy(); show["Status"] = show["Score"].apply(color_for_score)
        st.dataframe(show[["Domain","Score","Status"]], hide_index=True, use_container_width=True)
        make_bar(df, f"{gsel}: PASS Domains")
        st.markdown("**Actionable Points for HRTs**")
        for a in actions_hrt(df): st.write(f"- {a}")
    else:
        st.info("No data parsed for selected grade.")

# ----- Individual Profiles -----
with tab_profiles:
    st.subheader("Individual Profiles (Student-level)")
    gsel = st.selectbox("Select grade (profiles)", list(PASS_FILES.keys()), key="prof_g")
    dfp = parsed_profiles.get(gsel, pd.DataFrame())
    if isinstance(dfp, pd.DataFrame) and not dfp.empty:
        # filters
        c1, c2, c3 = st.columns(3)
        name_q = c1.text_input("Search name (contains)", "")
        group_q = c2.text_input("Filter by Group (e.g., 6.1, 7.3)", "")
        threshold = c3.slider("Flag threshold (concern if below)", 0, 100, 60)
        view = dfp.copy()
        if name_q:
            name_q_low = name_q.lower()
            view = view[view[["Forename","Surname"]].astype(str).apply(lambda s: s.str.lower().str.contains(name_q_low)).any(axis=1)]
        if group_q:
            view = view[view["Group"].astype(str).str.contains(group_q, case=False, na=False)]
        # flag columns
        dom_cols = [d for d in PASS_DOMAINS if d in view.columns]
        if dom_cols:
            view["# Domains < threshold"] = (view[dom_cols] < threshold).sum(axis=1)
        st.dataframe(view, use_container_width=True)
        # flagged export
        if dom_cols:
            flagged = view[view["# Domains < threshold"] >= 2]  # 2+ weak domains
            st.markdown("**Flagged students (2+ domains below threshold)**")
            st.dataframe(flagged, use_container_width=True)
            # export
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as w:
                view.to_excel(w, index=False, sheet_name="Profiles_Filtered")
                flagged.to_excel(w, index=False, sheet_name="Flagged")
            st.download_button("⬇️ Download Profiles (filtered + flagged)", out.getvalue(), file_name=f"{gsel}_Profiles_Flagged.xlsx")
        st.caption("Use filters to prepare HRT intervention lists. Threshold defaults to 60 (red band).")
    else:
        st.info("No 'Individual Profiles' sheet found/parsed for this grade.")

# ----- Item-Level Analysis -----
with tab_items:
    st.subheader("Item-Level Analysis (Q1…Qn)")
    gsel = st.selectbox("Select grade (items)", list(PASS_FILES.keys()), key="items_g")
    dfi = parsed_items.get(gsel, pd.DataFrame())
    if isinstance(dfi, pd.DataFrame) and not dfi.empty:
        # let user choose group rows to compare
        cats = dfi["Category"].dropna().astype(str).tolist()
        default_cats = [c for c in cats if c.lower() in ["overall","boys","girls"]]
        sel = st.multiselect("Choose categories to view", cats, default=default_cats[:3] if default_cats else cats[:3])
        view = dfi[dfi["Category"].isin(sel)].copy()
        st.dataframe(view, use_container_width=True)
        # weakest items within selected categories
        q_cols = [c for c in view.columns if str(c).lower().startswith("q")]
        if q_cols:
            weak = (view.set_index("Category")[q_cols]
                    .stack().rename("Score").reset_index()
                    .rename(columns={"level_1":"Question"}))
            weak = weak.sort_values("Score").groupby("Category").head(5)
            st.markdown("**Weakest items (bottom 5 per category)**")
            st.dataframe(weak, use_container_width=True)
            # bar chart for one selected category
            cat_pick = st.selectbox("Bar chart for category", sel)
            sub = view[view["Category"] == cat_pick]
            if not sub.empty:
                s = sub[q_cols].T.reset_index().rename(columns={"index":"Question"})
                fig, ax = plt.subplots()
                ax.bar(s["Question"], s.iloc[:,1].values)
                ax.set_title(f"{gsel} – {cat_pick}")
                ax.set_ylim(0,100)
                ax.set_xticklabels(s["Question"], rotation=90)
                st.pyplot(fig)
        # narrative
        st.markdown("**Actionable Points (based on weak items)**")
        st.write("- Use weak items to select SEL/advisory mini-lessons (e.g., safety, confidence, motivation).")
        st.write("- If gender gaps appear (e.g., Boys vs Girls on Q18), plan targeted mentoring or small groups.")
        st.write("- Review classroom routines/expectations if multiple motivation/effort items are weak.")
    else:
        st.info("No 'Item Level Analysis' sheet found/parsed for this grade.")

# ----- Cross-Grade Compare -----
with tab_compare:
    st.subheader("Cross-Grade Comparison (Cohort)")
    by_grade = {g:d for g,(d,_) in parsed_cohort.items() if isinstance(d, pd.DataFrame) and not d.empty}
    if by_grade:
        def make_heatmap_domain(by_grade):
            domains = PASS_DOMAINS
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
        make_heatmap_domain(by_grade)
        pivot = pd.concat(by_grade).reset_index().rename(columns={"level_0":"Grade"})
        pivot = pivot.pivot_table(index="Domain", columns="Grade", values="Score")
        st.dataframe(pivot.reindex(PASS_DOMAINS), use_container_width=True)
    else:
        st.info("No cohort data parsed to compare.")

st.caption("© Oberoi International School – JVLR | PASS Dashboard")
