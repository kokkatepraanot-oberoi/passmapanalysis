# ois_pass_app.py
# Streamlit PASS Dashboard – GL View, HRT View, Cross-Grade Compare
# Includes gender split analysis at domain level, clusters, insights, and strategies

import io
from typing import Dict, Optional, List, Tuple
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

pd.options.display.float_format = "{:.1f}".format

st.set_page_config(page_title="OIS JVLR - MS PASS Dashboard", layout="wide")

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

def pass_descriptor(score: float) -> str:
    if score >= 91:
        return "Very High"
    elif score >= 81:
        return "Very High"
    elif score >= 71:
        return "High"
    elif score >= 61:
        return "Secure"
    elif score >= 51:
        return "Secure"
    elif score >= 41:
        return "Average"
    elif score >= 31:
        return "Low"
    elif score >= 21:
        return "Cause for Concern"
    elif score >= 7:
        return "Vulnerable"
    else:
        return "Critical"

# Styling for descriptors
def descriptor_color(val):
    mapping = {
        "Very High": "background-color: #006400; color: white",
        "High": "background-color: #228B22; color: white",
        "Secure": "background-color: #ADFF2F; color: black",
        "Average": "background-color: #FFD700; color: black",
        "Low": "background-color: #FFA500; color: black",
        "Cause for Concern": "background-color: #FF4500; color: white",
        "Vulnerable": "background-color: #DC143C; color: white",
        "Critical": "background-color: #8B0000; color: white",
    }
    return mapping.get(val, "")

# ----------------- Parsers -----------------
def parse_cohort_sheet(src, sheet_name: str) -> pd.DataFrame:
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
                    val = pd.to_numeric(df[col].iloc[0], errors="coerce")
                    data[DOMAIN_MAP[dom]] = val
                except Exception:
                    pass
    out = pd.Series(data).rename_axis("Domain").reset_index(name="Score")
    out["Score"] = pd.to_numeric(out["Score"], errors="coerce").round(1)
    return out


def parse_individual_profiles(src, sheet_name: str) -> pd.DataFrame:
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

    # Map domains + enforce numeric
    for dom in PASS_DOMAINS:
        for col in df.columns:
            if dom.lower() in col.lower():
                df.rename(columns={col: DOMAIN_MAP[dom]}, inplace=True)
                df[DOMAIN_MAP[dom]] = pd.to_numeric(df[DOMAIN_MAP[dom]], errors="coerce")

    return df


def parse_item_level(src, sheet_name: str) -> pd.DataFrame:
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

    # Enforce numeric for domain columns
    for dom in PASS_DOMAINS:
        for col in df.columns:
            if dom.lower() in col.lower():
                df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_all_pass_files(pass_files):
    parsed_profiles = {}
    parsed_cohort = {}
    parsed_items = {}

    for grade, filepath in pass_files.items():
        try:
            sheets = list_sheets(filepath)
            profile_sheet = choose_sheet(sheets, ["profile"])
            cohort_sheet = choose_sheet(sheets, ["cohort"])
            item_sheet = choose_sheet(sheets, ["item"])

            parsed_profiles[grade] = parse_individual_profiles(filepath, profile_sheet)
            parsed_cohort[grade] = parse_cohort_sheet(filepath, cohort_sheet)
            parsed_items[grade] = parse_item_level(filepath, item_sheet)
        except Exception as e:
            st.error(f"❌ Failed to load {grade}: {e}")

    return parsed_profiles, parsed_cohort, parsed_items


# ----------------- Initialize -----------------
parsed_profiles, parsed_cohort, parsed_items = load_all_pass_files(PASS_FILES)


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
    fig, ax = plt.subplots(figsize=(6, 3))
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

# ---------------- Sidebar Navigation ----------------
st.sidebar.title("")



# ----------------- UI -----------------
st.title("🧭 OIS JVLR - MS PASS Dashboard")

tab_gl, tab_hrt, tab_compare = st.tabs([
    "🧑‍💼 GL View",
    "🧑‍🏫 HRT View",
    "📊 Cross-Grade Compare",
])

with tab_gl:
    gsel = st.selectbox("Select Grade (GL View)", list(PASS_FILES.keys()), key="gl_grade")
    df = parsed_cohort.get(gsel, pd.DataFrame())
    dfp = parsed_profiles.get(gsel, pd.DataFrame())

    if not df.empty:
        st.subheader("Cohort Analysis")
        show = df.copy()
        show["Score"] = show["Score"].round(1)
        show["Descriptor"] = show["Score"].apply(pass_descriptor)
        styled = show.style.applymap(descriptor_color, subset=["Descriptor"])
        st.dataframe(styled, hide_index=True, use_container_width=True)

        # --- Donut chart ---
        colors = [DOMAIN_COLORS.get(dom, "#999999") for dom in df["Domain"]]
        fig, ax = plt.subplots(figsize=(4, 4))
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

        # --- Cluster Analysis ---
        st.subheader("Cluster Analysis (Cohort)")
        st.caption("""
        **Cluster Definitions:**  
        - **Self:** PASS 2, PASS 3  
        - **Study:** PASS 4, PASS 6, PASS 7  
        - **School:** PASS 1, PASS 5, PASS 8, PASS 9
        """)
        cdf = cluster_scores(df)
        cdf["Descriptor"] = cdf["Score"].apply(pass_descriptor)
        styled = cdf.style.applymap(descriptor_color, subset=["Descriptor"])
        st.dataframe(styled, use_container_width=True)

        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel}: Cluster Scores")

        # --- Domain Domination Across Homerooms ---
        if not dfp.empty and "Group" in dfp.columns:
            st.subheader("Domain Domination Across Homerooms")

            dom_cols = [d for d in PASS_DOMAINS_NUM if d in dfp.columns]
            hr_means = dfp.groupby("Group")[dom_cols].mean().round(1)

            formatted = hr_means.copy()
            for col in dom_cols:
                formatted[col] = (
                    hr_means[col].round(1).astype(str)
                    + " (" + hr_means[col].apply(pass_descriptor) + ")"
                )

            def colorize(val):
                if "(" in val:
                    desc = val.split("(")[-1].strip(")")
                    return descriptor_color(desc)
                return ""

            styled = formatted.style.applymap(colorize)
            st.dataframe(styled, use_container_width=True)

        # 🚩 Flagged Students (Low & below ≤40)
            st.markdown("### 🚩 Flagged Students (Low & below ≤40)")
        
            # ✅ Only students with ANY domain <= 40
            flagged = dfp_num[dfp_num[dom_cols].le(40).any(axis=1)]
        
            if not flagged.empty:
                flagged_formatted = flagged.copy()
        
                # Clean Group numbers (6.1 not 6.100000)
                flagged_formatted["Group"] = (
                    flagged_formatted["Group"]
                    .astype(str)
                    .str.replace(".0", "", regex=False)
                )
        
                # Add descriptors
                for col in dom_cols:
                    flagged_formatted[col] = (
                        flagged_formatted[col].round(1).astype(str)
                        + " (" + flagged_formatted[col].apply(pass_descriptor) + ")"
                    )
        
                styled_flagged = flagged_formatted.style.applymap(colorize, subset=dom_cols)
        
                st.dataframe(
                    styled_flagged,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("✅ No flagged students (Low or below) in this grade.")

with tab_hrt:
    gsel = st.selectbox("Select Grade (HRT View)", list(PASS_FILES.keys()), key="hrt_grade")
    dfp = parsed_profiles.get(gsel, pd.DataFrame())

    if dfp.empty:
        st.warning("No profiles data uploaded for this grade.")
    else:
        classes = sorted(set(dfp["Group"].dropna().unique()))
        csel = st.selectbox("Select HR class", classes, key="hrt_class")
        class_df = dfp[dfp["Group"] == csel]
        dom_cols = [d for d in PASS_DOMAINS_NUM if d in class_df.columns]

        # ✅ Class means
        class_means = class_df[dom_cols].mean().reset_index()
        class_means.columns = ["Domain", "Score"]
        class_means["Score"] = class_means["Score"].round(1)
        class_means["Descriptor"] = class_means["Score"].apply(pass_descriptor)

        styled = class_means.style.applymap(descriptor_color, subset=["Descriptor"])
        st.subheader(f"{gsel} {csel}: Class Analysis")
        st.dataframe(styled, use_container_width=True)

        # ✅ Donut chart
        colors = [DOMAIN_COLORS.get(dom, "#999999") for dom in class_means["Domain"]]
        fig, ax = plt.subplots(figsize=(4, 4))
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

        # ✅ Insights
        strengths, concerns = format_insights(class_means)
        st.markdown("### 🔎 Insights (Class)")
        if strengths:
            st.success("**Strengths**\n" + "\n".join(strengths))
        if concerns:
            st.warning("**Concerns**\n" + "\n".join(concerns))

        # ✅ Actionable Strategies
        st.markdown("### ✅ Actionable Strategies (Class)")
        weak_domains = []
        for _, row in class_means.iterrows():
            if row["Score"] < 65:
                weak_domains.append(row["Domain"])
        if weak_domains:
            for dom in weak_domains:
                strategies = DOMAIN_STRATEGIES.get(dom, [])
                if strategies:
                    st.markdown(f"**{dom}:**")
                    for s in strategies:
                        st.markdown(f"- {s}")
        else:
            st.success("No domain-specific strategies required. Maintain current strengths.")

        # 🚩 Flagged Students (Low & below ≤40)
        if not class_df.empty:
            st.markdown("### 🚩 Flagged Students (Low & below ≤40)")

            # Convert only domain columns to numeric
            class_num = class_df.copy()
            for col in dom_cols:
                class_num[col] = pd.to_numeric(class_num[col], errors="coerce")

            # ✅ Only students with ANY domain <= 40
            flagged = class_num[class_num[dom_cols].le(40).any(axis=1)]

            if not flagged.empty:
                flagged_formatted = flagged.copy()

                # Clean Group numbers like 6.1 instead of 6.100000
                flagged_formatted["Group"] = (
                    flagged_formatted["Group"]
                    .astype(str)
                    .str.replace(".0", "", regex=False)
                )

                # Format scores with descriptors
                for col in dom_cols:
                    flagged_formatted[col] = (
                        flagged_formatted[col].round(1).astype(str)
                        + " (" + flagged_formatted[col].apply(pass_descriptor) + ")"
                    )

                # Apply descriptor-based color coding
                def colorize(val):
                    if "(" in str(val):
                        desc = val.split("(")[-1].strip(")")
                        return descriptor_color(desc)
                    return ""

                styled_flagged = flagged_formatted[
                    ["Forename", "Surname", "Group"] + dom_cols
                ].style.applymap(colorize, subset=dom_cols)

                st.dataframe(styled_flagged, use_container_width=True, hide_index=True)

            else:
                st.success("✅ No flagged students (Low or below) in this class.")


        # ✅ Cluster Analysis
        st.subheader(f"{gsel} {csel}: Cluster Analysis")
        st.caption("""
        **Cluster Definitions:**  
        - **Self:** PASS 2 (Perceived Learning Capability), PASS 3 (Self-regard as a Learner)  
        - **Study:** PASS 4 (Preparedness for Learning), PASS 6 (General Work Ethic), PASS 7 (Confidence in Learning)  
        - **School:** PASS 1 (Feelings about School), PASS 5 (Attitudes to Teachers), PASS 8 (Attitudes to Attendance), PASS 9 (Response to Curriculum)
        """)
        cdf = cluster_scores(class_means.rename(columns={"Domain": "Domain"}))
        cdf["Descriptor"] = cdf["Score"].apply(pass_descriptor)
        styled = cdf.style.applymap(descriptor_color, subset=["Descriptor"])
        st.dataframe(styled, use_container_width=True)

        make_bar(cdf.rename(columns={"Cluster": "Domain"}), f"{gsel} {csel}: Cluster Scores")
        top, bot = format_insights(cdf.rename(columns={"Cluster": "Domain"}))
        if top:
            st.success("**Cluster Strengths**\n" + "\n".join(top))
        if bot:
            st.warning("**Cluster Concerns**\n" + "\n".join(bot))

with tab_compare:
    st.subheader("Cross-Grade Comparison (Cohort)")
    by_grade = {g: d for g, d in parsed_cohort.items() if isinstance(d, pd.DataFrame) and not d.empty}
    if by_grade:
        domains = PASS_DOMAINS_NUM
        rows = []
        for g, df in by_grade.items():
            tmp = df.copy()
            tmp["Grade"] = g
            tmp["Score"] = tmp["Score"].round(1)  # ensure 1 decimal
            rows.append(tmp)

        combined = pd.concat(rows)

        # Pivot table: Domain x Grade (scores only)
        pivot = combined.pivot_table(index="Domain", columns="Grade", values="Score")
        pivot = pivot.reindex(PASS_DOMAINS_NUM)

        # Build combined Score (Descriptor) manually
        pivot_combined = pivot.copy()
        for grade in pivot.columns:
            descs = pivot[grade].apply(pass_descriptor)
            pivot_combined[grade] = pivot[grade].round(1).astype(str) + " (" + descs + ")"

        # Apply color coding
        def highlight_descriptor(val):
            if "(" in val:
                desc = val.split("(")[-1].strip(")")
                return descriptor_color(desc)
            return ""

        styled = pivot_combined.style.applymap(highlight_descriptor)
        st.dataframe(styled, use_container_width=True)

        # Heatmap (smaller size so table is main focus)
        M = pivot.values
        fig, ax = plt.subplots(figsize=(6, 4))  # smaller plot
        im = ax.imshow(M, aspect="auto", vmin=0, vmax=100, cmap="coolwarm")
        ax.set_yticks(range(len(domains)))
        ax.set_yticklabels(domains)
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns)
        ax.set_title("PASS Domain Heatmap (by Grade)")
        fig.colorbar(im, ax=ax)
        st.pyplot(fig)

        # ---- Cross-Grade Insights + Actionables ----
        st.markdown("### 🔎 Insights (Cross-Grade Trends)")
        insights = []
        for dom in PASS_DOMAINS_NUM:
            if dom in pivot.index:
                vals = pivot.loc[dom].dropna()
                if len(vals) >= 2:
                    trend = vals.iloc[-1] - vals.iloc[0]
                    if trend <= -5:
                        insights.append(f"- **{dom}** declines across grades (drop {trend:.1f})")
                    elif trend >= 5:
                        insights.append(f"- **{dom}** improves across grades (gain {trend:.1f})")

        if insights:
            st.info("\n".join(insights))
        else:
            st.success("No major cross-grade declines detected.")

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

