# ois_pass_app.py
# Streamlit PASS Dashboard – GL View, HRT View, Cross-Grade Compare
# Includes gender split analysis at domain level, clusters, insights, and strategies

import io
from typing import Dict, Optional, List, Tuple
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="OIS PASS Dashboard", layout="wide")

# --------- CONFIG ---------
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

DOMAIN_COLORS = {
    "1. Feelings about school": "#4CAF50",      # green
    "2. Perceived learning capability": "#2196F3",  # blue
    "3. Self-regard as a learner": "#9C27B0",   # purple
    "4. Preparedness for learning": "#FF9800",  # orange
    "5. Attitudes to teachers": "#F44336",      # red
    "6. General work ethic": "#795548",         # brown
    "7. Confidence in learning": "#00BCD4",     # cyan
    "8. Attitudes to attendance": "#8BC34A",    # light green
    "9. Response to curriculum demands": "#FFC107", # amber
}

PASS_DOMAINS_NUM = [f"{i+1}. {d}" for i, d in enumerate(PASS_DOMAINS)]
DOMAIN_MAP = dict(zip(PASS_DOMAINS, PASS_DOMAINS_NUM))

THRESHOLDS = {"red": 60.0, "amber": 70.0}

# Cluster groupings
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

# Domain strategies (expandable as needed)
DOMAIN_STRATEGIES = {
    "1. Feelings about school": [
        "Rebuild belonging (circles, advisory games, peer shout-outs)",
        "Use assemblies for positive school identity",
        "Student voice forums",
    ],
    "2. Perceived learning capability": [
        "Growth mindset interventions",
        "Feedback focused on effort/progress",
        "Scaffolded small wins for confidence",
    ],
    "3. Self-regard as a learner": [
        "Celebrate academic progress broadly",
        "Peer tutoring opportunities",
        "Strengths-based teacher feedback",
    ],
    "4. Preparedness for learning": [
        "Planner routines and visible trackers",
        "‘Do Now’ starter tasks",
        "Time management mini-lessons",
    ],
    "5. Attitudes to teachers": [
        "Positive calls/emails home",
        "Advisory sessions to reconnect",
        "Restorative practices",
    ],
    "6. General work ethic": [
        "Weekly planner checks",
        "SEL sessions on perseverance",
        "Recognition for consistent effort",
    ],
    "7. Confidence in learning": [
        "Growth mindset assemblies",
        "Celebrate risk-taking in class",
        "Safe-fail opportunities",
    ],
    "8. Attitudes to attendance": [
        "Monitor attendance closely",
        "Early family contact",
        "Class/HR competitions for attendance",
    ],
    "9. Response to curriculum demands": [
        "Audit workload with HoDs",
        "Space assessments across terms",
        "Differentiate complex tasks",
    ],
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
    """Parse Cohort Analysis sheet (Grade-level domain scores)."""
    try:
        df = pd.read_excel(src, sheet_name=sheet_name, header=4)
    except Exception:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]
    data = {}
    for dom in PASS_DOMAINS:
        for col in df.columns:
            if dom.lower() in col.lower():
                try:
                    val = float(df[col].iloc[0])
                    data[DOMAIN_MAP[dom]] = val
                except Exception:
                    pass
    out = pd.Series(data).rename_axis("Domain").reset_index(name="Score")
    out["Score"] = out["Score"].round(1)
    return out

def parse_individual_profiles(src, sheet_name: Optional[str]) -> pd.DataFrame:
    """Parse Individual Profiles (student-level data)."""
    try:
        df = pd.read_excel(src, sheet_name=sheet_name, header=4)
    except Exception:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]

    # Ensure Group column
    if "Group" not in df.columns:
        for col in df.columns:
            if "group" in col.lower():
                df.rename(columns={col: "Group"}, inplace=True)

    if "Group" not in df.columns:
        df["Group"] = "All"

    # Gender
    for col in df.columns:
        if "gender" in col.lower():
            df.rename(columns={col: "Gender"}, inplace=True)

    # Map domains
    for dom in PASS_DOMAINS:
        for col in df.columns:
            if dom.lower() in col.lower():
                df.rename(columns={col: DOMAIN_MAP[dom]}, inplace=True)

    return df

def parse_item_level(src, sheet_name: Optional[str]) -> pd.DataFrame:
    """Parse Item Level Analysis (gender splits)."""
    try:
        df = pd.read_excel(src, sheet_name=sheet_name, header=4)
    except Exception:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]

    if "Category" not in df.columns:
        for col in df.columns:
            if "category" in col.lower():
                df.rename(columns={col: "Category"}, inplace=True)

    return df

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
    ax.bar(df["Domain"], df["Score"], color="skyblue")
    ax.set_title(title)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    ax.set_xticklabels(df["Domain"], rotation=45, ha="right")
    st.pyplot(fig)

def make_gender_bar(df: pd.DataFrame, title: str):
    doms = [d for d in PASS_DOMAINS_NUM if d in df.columns]
    if not doms:
        st.warning("No domain-level gender data available.")
        return
    boys = df[df["Category"] == "Boys"][doms].mean()
    girls = df[df["Category"] == "Girls"][doms].mean()
    overall = df[df["Category"] == "Overall"][doms].mean()
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
        if d not in df.columns:
            continue
        boys = df[df["Category"] == "Boys"][d].mean()
        girls = df[df["Category"] == "Girls"][d].mean()
        if pd.notna(boys) and pd.notna(girls):
            gap = boys - girls
            if abs(gap) >= 5:
                weaker = "Boys" if gap < 0 else "Girls"
                insights.append(f"- {weaker} weaker in {d} (gap {gap:+.1f})")
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
            scores[cname] = vals.mean().round(1)
    return pd.Series(scores).rename_axis("Cluster").reset_index(name="Score")

# ----------------- Sidebar uploads -----------------
st.sidebar.header("📁 Upload PASS workbooks (G6, G7, G8)")
uploaded = {g: st.sidebar.file_uploader(f"{g} (.xlsx)", type=["xlsx"], key=f"u_{g}") for g in PASS_FILES}

parsed_cohort: Dict[str, pd.DataFrame] = {}
parsed_profiles: Dict[str, pd.DataFrame] = {}
parsed_items: Dict[str, pd.DataFrame] = {}

SHEET_HINTS = {
    "cohort": ["cohort analysis"],
    "profiles": ["individual profiles", "student profiles"],
    "items": ["item level analysis", "item-level analysis"],
}

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
        show["Score"] = show["Score"].round(1)
        show["Status"] = show["Score"].apply(lambda x: "🟥" if x < 60 else "🟧" if x < 70 else "🟩")
        st.dataframe(show, hide_index=True, use_container_width=True)

        # Donut chart
        colors = [DOMAIN_COLORS.get(dom, "#999999") for dom in df["Domain"]]
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(
            df["Score"],
            labels=df["Domain"],
            autopct="%.1f%%",
            startangle=90,
            counterclock=False,
            colors=colors,
            wedgeprops=dict(width=0.4)
        )
        ax.set_title(f"{gsel}: Domain Distribution (Cohort)")
        st.pyplot(fig)

        make_bar(df, f"{gsel}: PASS Domains")

        strengths, concerns = format_insights(df)
        st.markdown("### 🔎 Insights (Cohort)")
        if strengths:
            st.success("**Strengths**\n" + "\n".join(strengths))
        if concerns:
            st.warning("**Concerns**\n" + "\n".join(concerns))

        st.markdown("### ✅ Actionable Strategies")
        domain_strategies(df)

        st.subheader("Cluster Analysis (Cohort)")
        cdf = cluster_scores(df)
        st.dataframe(cdf, use_container_width=True)
        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel}: Cluster Scores")
        top, bot = format_insights(cdf.rename(columns={"Cluster": "Domain"}))
        if top:
            st.success("**Cluster Strengths**\n" + "\n".join(top))
        if bot:
            st.warning("**Cluster Concerns**\n" + "\n".join(bot))

    # Domain domination across HRs
    dfp = parsed_profiles.get(gsel, pd.DataFrame())
    if not dfp.empty and "Group" in dfp.columns:
        st.subheader("Domain Domination Across Homerooms")
    
        dom_cols = [d for d in PASS_DOMAINS_NUM if d in dfp.columns]
        hr_means = dfp.groupby("Group")[dom_cols].mean().round(1)
    
        st.dataframe(hr_means, use_container_width=True)
    
        # Heatmap
        fig, ax = plt.subplots(figsize=(10, 6))
        im = ax.imshow(hr_means.values, aspect="auto", cmap="coolwarm", vmin=0, vmax=100)
        ax.set_xticks(range(len(hr_means.columns)))
        ax.set_xticklabels(hr_means.columns, rotation=45, ha="right")
        ax.set_yticks(range(len(hr_means.index)))
        ax.set_yticklabels(hr_means.index)
        fig.colorbar(im, ax=ax)
        st.pyplot(fig)
    
        # ---- Insights and Actionables for Domain Domination Heatmap ----
        st.markdown("### 🔎 Insights (Across HRs)")
        
        insights = []
        # Calculate variability (range across HRs per domain)
        for dom in hr_means.columns:
            dom_scores = hr_means[dom].dropna()
            if not dom_scores.empty:
                dom_range = dom_scores.max() - dom_scores.min()
                dom_avg = dom_scores.mean()
        
                if dom_range >= 15:  # big spread between HRs
                    insights.append(f"- **{dom}** shows wide variability across HRs (range {dom_range:.1f}).")
                if dom_avg < 65:
                    insights.append(f"- **{dom}** is a weaker domain overall (average {dom_avg:.1f}).")
                if dom_avg >= 75 and dom_range < 10:
                    insights.append(f"- **{dom}** is a consistent strength across HRs (average {dom_avg:.1f}).")
        
        if insights:
            st.info("\n".join(insights))
        else:
            st.success("No major domain-level concerns detected across HRs.")
        
        # Actionables
        st.markdown("### ✅ Actionable Strategies (Across HRs)")
        st.markdown(
            """
        - **Preparedness for learning & General work ethic** → reinforce routines (planners, peer accountability, structured check-ins).  
        - **Attitudes to teachers** → relational focus: student voice surveys, restorative circles, positive reinforcement.  
        - **Weaker HRs** → GLs to coordinate with specific HRTs for class-targeted interventions.  
        - **Stronger HRs** → share practices at staff meetings so successful strategies cascade across the grade.  
        """
        )


    dfi = parsed_items.get(gsel, pd.DataFrame())
    if not dfi.empty:
        st.subheader("Gender Split Analysis (Cohort)")
        if "Category" in dfi.columns:
            doms = [d for d in PASS_DOMAINS_NUM if d in dfi.columns]
            view = dfi[dfi["Category"].isin(["Overall", "Boys", "Girls"])]
            gender_df = view.groupby("Category")[doms].mean().reset_index()
            gender_df[doms] = gender_df[doms].round(1)
            st.dataframe(gender_df, use_container_width=True)
            make_gender_bar(gender_df, f"{gsel}: Gender Comparison (Domains)")
            insights = gender_insights(gender_df)
            if insights:
                st.info("**Gender Gaps**\n" + "\n".join(insights))

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
        class_means["Score"] = class_means["Score"].round(1)

        st.subheader(f"{gsel} {csel}: Class Analysis")
        st.dataframe(class_means, use_container_width=True)

        # Donut chart
        colors = [DOMAIN_COLORS.get(dom, "#999999") for dom in class_means["Domain"]]
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(
            class_means["Score"],
            labels=class_means["Domain"],
            autopct="%.1f%%",
            startangle=90,
            counterclock=False,
            colors=colors,
            wedgeprops=dict(width=0.4)
        )
        ax.set_title(f"{gsel} {csel}: Domain Distribution (Class)")
        st.pyplot(fig)

        strengths, concerns = format_insights(class_means)
        st.markdown("### 🔎 Insights (Class)")
        if strengths:
            st.success("**Strengths**\n" + "\n".join(strengths))
        if concerns:
            st.warning("**Concerns**\n" + "\n".join(concerns))

        st.markdown("### ✅ Actionable Strategies")
        domain_strategies(class_means)

        # Flagged students
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

        # Cluster analysis
        st.subheader(f"{gsel} {csel}: Cluster Analysis")
        cdf = cluster_scores(class_means.rename(columns={"Domain": "Domain"}))
        st.dataframe(cdf, use_container_width=True)
        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel} {csel}: Cluster Scores")
        top, bot = format_insights(cdf.rename(columns={"Cluster": "Domain"}))
        if top:
            st.success("**Cluster Strengths**\n" + "\n".join(top))
        if bot:
            st.warning("**Cluster Concerns**\n" + "\n".join(bot))

        # Gender Split Analysis (per-HR if Gender column exists)
        if "Gender" in class_df.columns:
            st.subheader("Gender Split Analysis (Class-level)")
            gender_df = class_df.groupby("Gender")[dom_cols].mean().reset_index()
            gender_df[dom_cols] = gender_df[dom_cols].round(1)
            st.dataframe(gender_df, use_container_width=True)

            melted = gender_df.melt(id_vars="Gender", value_vars=dom_cols, var_name="Domain", value_name="Score")
            pivot = melted.pivot_table(index="Domain", columns="Gender", values="Score")
            insights = []
            if "Boys" in pivot.columns and "Girls" in pivot.columns:
                for dom in dom_cols:
                    boys = pivot.loc[dom, "Boys"]
                    girls = pivot.loc[dom, "Girls"]
                    if pd.notna(boys) and pd.notna(girls):
                        gap = boys - girls
                        if abs(gap) >= 5:
                            weaker = "Boys" if gap < 0 else "Girls"
                            insights.append(f"- {weaker} weaker in {dom} (gap {gap:+.1f})")
            if insights:
                st.info("**Gender Gaps**\n" + "\n".join(insights))

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

        if mats:
            M = np.column_stack(mats)
            fig, ax = plt.subplots(figsize=(8, 6))
            im = ax.imshow(M, aspect="auto", vmin=0, vmax=100, cmap="coolwarm")
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
        pivot = pivot.reindex(PASS_DOMAINS_NUM)
        st.dataframe(pivot.round(1), use_container_width=True)
                # ---- Cross-Grade Insights + Actionables ----
        st.markdown("### 🔎 Insights (Cross-Grade Trends)")

        insights = []
        # Calculate trends per domain
        for dom in PASS_DOMAINS_NUM:
            if dom in pivot.index:
                vals = pivot.loc[dom].dropna()
                if len(vals) >= 2:
                    trend = vals.iloc[-1] - vals.iloc[0]  # Grade8 - Grade6
                    if trend <= -5:
                        insights.append(f"- **{dom}** declines across grades (drop {trend:.1f})")
                    elif trend >= 5:
                        insights.append(f"- **{dom}** improves across grades (gain {trend:.1f})")

        if insights:
            st.info("\n".join(insights))
        else:
            st.success("No major cross-grade declines detected.")

        # Actionable Strategies
        st.markdown("### ✅ Actionable Strategies (Cross-Grade)")
        st.markdown(
            """
- **Curriculum Demands** → Study skills workshops, scaffolded assignments, targeted Grade 8 support.  
- **Work Ethic & Preparedness** → Structured routines (planners, peer accountability), goal-setting at transitions.  
- **Teacher–Student Relationships** → 1:1 check-ins, positive calls home, teacher PD on relational strategies.  
- **Grade 6** → Maintain motivation, monitor flagged students.  
- **Grade 7** → Sustain engagement with collaborative, project-based learning.  
- **Grade 8** → Focus on time management, mentoring, and restorative dialogue around teacher relationships.  
            """
        )

    else:
        st.info("No cohort data parsed to compare across grades.")
