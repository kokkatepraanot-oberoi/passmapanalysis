
# ois_pass_app.py
# Streamlit PASS Dashboard (GL view & HRT view)
# Run with: streamlit run ois_pass_app.py

import io
from datetime import datetime
from typing import Dict, Tuple, Optional, List

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================
# CONFIG
# =========================
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

THRESHOLDS = {
    "red": 60.0,
    "amber": 70.0,
}

# =========================
# HELPERS
# =========================
def _clean_col(col):
    if pd.isna(col):
        return ""
    return str(col).strip()


def detect_wide_format(df: pd.DataFrame) -> bool:
    """Heuristic: look for a row whose cells contain many PASS domain names across columns."""
    for r in range(min(10, len(df))):
        row_values = [_clean_col(x) for x in df.iloc[r].values]
        hit = sum(1 for v in row_values if v in PASS_DOMAINS)
        if hit >= 5:  # enough domains detected in a single row
            return True
    return False


def parse_pass_excel(path: str) -> Tuple[pd.DataFrame, Optional[int]]:
    """Parse the vendor PASS workbook into a tidy long dataframe:
    columns => ['Domain', 'Score', 'Grade', 'n']

    Returns (df, n) where n is the number of respondents if detected.
    The parser is defensive and supports both wide and long-ish layouts seen in vendor exports.
    """
    raw = pd.read_excel(path, header=None)

    # Try to grab 'n' (frequency/participants) from the first 10 rows
    n: Optional[int] = None
    for r in range(min(12, len(raw))):
        row = [_clean_col(x) for x in raw.iloc[r].values]
        # Typical patterns: a cell 'Frequency' followed by an integer in same row or next column/row
        if any(x.lower() == "frequency" for x in row):
            # pick the last numeric in the row
            nums = [x for x in row if str(x).replace('.', '', 1).isdigit()]
            if nums:
                try:
                    n = int(float(nums[-1]))
                except Exception:
                    pass

    # Heuristic 1: wide format (domains in a header row, scores in the next row)
    if detect_wide_format(raw):
        header_row = None
        for r in range(min(12, len(raw))):
            vals = [_clean_col(x) for x in raw.iloc[r].values]
            hits = [i for i, v in enumerate(vals) if v in PASS_DOMAINS]
            if len(hits) >= 5:
                header_row = r
                break
        if header_row is not None and header_row + 1 < len(raw):
            headers = [_clean_col(x) for x in raw.iloc[header_row].values]
            scores = raw.iloc[header_row + 1].values
            data = {}
            for h, s in zip(headers, scores):
                if h in PASS_DOMAINS:
                    try:
                        data[h] = float(s)
                    except Exception:
                        continue
            df = (
                pd.Series(data)
                .rename_axis("Domain")
                .reset_index(name="Score")
            )
            return df, n

    # Heuristic 2: look for a two-column layout with domain + score down the rows
    # Find rows where first col is a PASS domain; second/next numeric col is a score
    rows = []
    for r in range(len(raw)):
        row_vals = raw.iloc[r].values
        for c in range(min(6, raw.shape[1])):
            dom = _clean_col(row_vals[c] if c < len(row_vals) else "")
            if dom in PASS_DOMAINS:
                # find first numeric to the right
                numeric_score = None
                for c2 in range(c + 1, raw.shape[1]):
                    v = row_vals[c2]
                    if isinstance(v, (int, float)) and not pd.isna(v):
                        numeric_score = float(v)
                        break
                    try:
                        vv = float(str(v))
                        numeric_score = vv
                        break
                    except Exception:
                        continue
                if numeric_score is not None:
                    rows.append({"Domain": dom, "Score": numeric_score})
    if rows:
        return pd.DataFrame(rows).drop_duplicates(subset=["Domain"]), n

    # Fallback: empty
    return pd.DataFrame(columns=["Domain", "Score"]), n


def color_for_score(x: float) -> str:
    if pd.isna(x):
        return "🟦"
    if x < THRESHOLDS["red"]:
        return "🟥"
    if x < THRESHOLDS["amber"]:
        return "🟧"
    return "🟩"


def top_bottom(df: pd.DataFrame, k: int = 2) -> Tuple[pd.DataFrame, pd.DataFrame]:
    d2 = df.sort_values("Score", ascending=False)
    return d2.head(k), d2.tail(k)


def make_bar_chart(df: pd.DataFrame, title: str):
    fig, ax = plt.subplots()
    ax.bar(df["Domain"], df["Score"])
    ax.set_title(title)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)


def make_heatmap(grades_to_df: Dict[str, pd.DataFrame]):
    # Build matrix: rows=domains, cols=grades
    all_domains = PASS_DOMAINS
    mat = []
    cols = []
    for grade, df in grades_to_df.items():
        ser = df.set_index("Domain")["Score"].reindex(all_domains)
        mat.append(ser.values)
        cols.append(grade)
    M = np.column_stack(mat) if mat else np.zeros((len(all_domains), 0))
    fig, ax = plt.subplots()
    cax = ax.imshow(M, aspect="auto", vmin=0, vmax=100)
    ax.set_yticks(range(len(all_domains)))
    ax.set_yticklabels(all_domains)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols)
    ax.set_title("PASS Category Heatmap (by Grade)")
    fig.colorbar(cax, ax=ax)
    st.pyplot(fig)


def narrative_insights(df: pd.DataFrame, grade: str, n: Optional[int]) -> str:
    if df.empty:
        return f"No data parsed for {grade}."
    top2, bottom2 = top_bottom(df, 2)
    lines = []
    if n is not None:
        lines.append(f"{grade}: {int(n)} respondents.")
    lines.append(f"Strengths → " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in top2.itertuples()))
    lines.append(f"Concerns → " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in bottom2.itertuples()))
    # flag sub-70s
    flags = df[df["Score"] < THRESHOLDS["amber"]].sort_values("Score")
    if not flags.empty:
        lines.append("Watchlist (≤70): " + ", ".join(f"{r.Domain} ({r.Score:.1f})" for r in flags.itertuples()))
    return "\n".join(lines)


def actionable_gl(df: pd.DataFrame) -> List[str]:
    if df.empty:
        return ["No data available."]
    acts = []
    if (df["Domain"] == "Attitudes to teachers").any():
        val = df.set_index("Domain").loc["Attitudes to teachers", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Plan grade-wide teacher–student relationship initiatives (advisory check-ins, mentor matching).")
    if (df["Domain"] == "Preparedness for learning").any():
        val = df.set_index("Domain").loc["Preparedness for learning", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Run study-skills & organisation workshops (planners, goal-setting, routines).")
    if (df["Domain"] == "Response to curriculum demands").any():
        val = df.set_index("Domain").loc["Response to curriculum demands", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Coordinate with HoDs to review workload, scaffolds, and differentiation strategies.")
    if (df["Domain"] == "Confidence in learning").any():
        val = df.set_index("Domain").loc["Confidence in learning", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Embed growth-mindset messaging in assemblies; celebrate small academic wins.")
    if not acts:
        acts.append("Maintain strengths; set a light-touch monitoring cycle until next PASS.")
    return acts


def actionable_hrt(df: pd.DataFrame) -> List[str]:
    if df.empty:
        return ["No data available."]
    acts = []
    if (df["Domain"] == "Feelings about school").any():
        val = df.set_index("Domain").loc["Feelings about school", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Plan class bonding: circles, games, peer recognition to uplift belonging.")
    if (df["Domain"] == "General work ethic").any():
        val = df.set_index("Domain").loc["General work ethic", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Introduce weekly routines: planners, Do Now tasks, and visible goal trackers.")
    if (df["Domain"] == "Attitudes to attendance").any():
        val = df.set_index("Domain").loc["Attitudes to attendance", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Monitor absences/tardies early, contact families, and reinforce attendance value.")
    if (df["Domain"] == "Attitudes to teachers").any():
        val = df.set_index("Domain").loc["Attitudes to teachers", "Score"]
        if val < THRESHOLDS["amber"]:
            acts.append("Increase 1:1 check-ins; use positive calls/emails home to build trust.")
    if not acts:
        acts.append("Sustain current practices; recognise positive trends in class meetings.")
    return acts


# =========================
# SIDEBAR (File inputs)
# =========================
st.sidebar.header("📁 Upload PASS reports")
uploaded = {}
for grade, default_name in PASS_FILES.items():
    uploaded[grade] = st.sidebar.file_uploader(f"{grade} file (.xlsx)", type=["xlsx"], key=f"u_{grade}")

# Fallback to local files if running where default files exist
parsed: Dict[str, Tuple[pd.DataFrame, Optional[int]]] = {}
for grade, default_name in PASS_FILES.items():
    if uploaded[grade] is not None:
        df, n = parse_pass_excel(uploaded[grade])
        parsed[grade] = (df.assign(Grade=grade), n)
    else:
        try:
            df, n = parse_pass_excel(default_name)
            parsed[grade] = (df.assign(Grade=grade), n)
        except Exception:
            parsed[grade] = (pd.DataFrame(columns=["Domain", "Score", "Grade"]), None)

# Build combined tidy dataframe
combined = []
respondents = {}
for grade, (df, n) in parsed.items():
    if n is not None:
        respondents[grade] = n
    if not df.empty:
        combined.append(df)
tidy = pd.concat(combined, ignore_index=True) if combined else pd.DataFrame(columns=["Domain", "Score", "Grade"])

st.title("🧭 OIS PASS Dashboard")
st.caption("Two-level layout for Grade Leaders (GLs) and Homeroom Teachers (HRTs) — generated from PASS reports.")

# =========================
# TOP SUMMARY
# =========================
with st.expander("What is PASS? (9 domains)", expanded=False):
    st.write(", ".join(PASS_DOMAINS))

cols = st.columns(3)
cols[0].metric("Grades loaded", f"{len([g for g, (df, _) in parsed.items() if not df.empty])}/3")
cols[1].metric("Respondents (detected)", ", ".join(f"{g}: {n}" for g, n in respondents.items()) if respondents else "n/a")
cols[2].metric("Generated", datetime.now().strftime("%d %b %Y, %H:%M"))

# =========================
# TABS: GL view and HRT view
# =========================
tab_gl, tab_hrt, tab_compare = st.tabs(["🧑‍💼 GL View", "🧑‍🏫 HRT View", "📊 Cross-Grade Compare"])

# ========== GL VIEW ==========
with tab_gl:
    st.subheader("Grade Leaders (GL)")
    st.write("Use this view to see grade-wide patterns, identify systemic concerns, and plan grade-level actions.")

    # Per-grade panels
    for grade in ["Grade 6", "Grade 7", "Grade 8"]:
        df, n = parsed.get(grade, (pd.DataFrame(), None))
        st.markdown(f"### {grade}")
        if df.empty:
            st.info("No data parsed.")
            continue

        # Table with status emoji
        show = df.copy()
        show["Status"] = show["Score"].apply(color_for_score)
        show = show[["Domain", "Score", "Status"]]
        st.dataframe(show, hide_index=True, use_container_width=True)

        # Chart
        make_bar_chart(df, f"{grade}: PASS Domain Scores")

        # Narrative + Actions
        st.markdown("**Insights**")
        st.write(narrative_insights(df, grade, n))

        st.markdown("**Actionable Points for GLs**")
        for item in actionable_gl(df):
            st.write(f"- {item}")

        st.divider()

    # Export GL summary
    if not tidy.empty:
        gl_summary = tidy.groupby(["Grade", "Domain"], as_index=False)["Score"].mean()
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            gl_summary.to_excel(writer, index=False, sheet_name="GL Summary")
        st.download_button("⬇️ Download GL Summary (XLSX)", data=bio.getvalue(), file_name="OIS_PASS_GL_Summary.xlsx")

# ========== HRT VIEW ==========
with tab_hrt:
    st.subheader("Homeroom Teachers (HRT)")
    st.write("Compare your homeroom (or class) to the grade average and get suggested actions.")
    st.caption("Note: If student- or class-level files are uploaded in future cycles, this view will auto-expand to those details.")

    # For now, we use grade-level data as proxy and compare to overall grade average.
    grade_choice = st.selectbox("Select Grade", ["Grade 6", "Grade 7", "Grade 8"])
    df, n = parsed.get(grade_choice, (pd.DataFrame(), None))

    if df.empty:
        st.info("No data parsed for the selected grade.")
    else:
        # Show table + highlights
        show = df.copy()
        show["Status"] = show["Score"].apply(color_for_score)
        st.dataframe(show[["Domain", "Score", "Status"]], hide_index=True, use_container_width=True)

        # Chart
        make_bar_chart(df, f"{grade_choice}: PASS Domain Scores")

        # Suggested actions for HRTs based on grade profile
        st.markdown("**Actionable Points for HRTs**")
        for item in actionable_hrt(df):
            st.write(f"- {item}")

        # Placeholder: class vs grade comparison (when class-level data is available)
        st.info("When class-level data is available, this panel will show: Class vs Grade averages, heatmaps, and flagged students (confidential).")

# ========== CROSS-GRADE COMPARE ==========
with tab_compare:
    st.subheader("Cross-Grade Comparison")
    if tidy.empty:
        st.info("No data parsed.")
    else:
        by_grade = {g: d for g, (d, _) in parsed.items() if not d.empty}
        make_heatmap(by_grade)
        st.caption("Heatmap scale: 0–100. Use this to see where attitudes strengthen or decline across grades.")

        # Quick compare table
        pivot = tidy.pivot_table(index="Domain", columns="Grade", values="Score", aggfunc="mean")
        st.dataframe(pivot.reindex(PASS_DOMAINS), use_container_width=True)

        # Export compare pack
        bio2 = io.BytesIO()
        with pd.ExcelWriter(bio2, engine="xlsxwriter") as writer:
            tidy.to_excel(writer, index=False, sheet_name="Tidy")
            pivot.to_excel(writer, sheet_name="Compare")
        st.download_button("⬇️ Download Compare Pack (XLSX)", data=bio2.getvalue(), file_name="OIS_PASS_Compare_Pack.xlsx")

st.caption("© Oberoi International School – JVLR | PASS Dashboard")
