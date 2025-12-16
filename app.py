import streamlit as st
import pikepdf
from pdfminer.layout import LTTextContainer
from pdfminer.high_level import extract_pages
import tempfile
import os
import pandas as pd

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PDF Scope & Scan",
    page_icon="📄",
    layout="wide"
)

# --- CSS FOR STYLING (Compact View) ---
st.markdown("""
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
    }
    hr {
        margin-top: 1rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- LOGIC CLASS (The Engine) ---
class PDFComplexityAssessor:
    def __init__(self, file_stream, is_rush_order):
        self.stream = file_stream
        self.is_rush_order = is_rush_order
        self.report = {
            "is_tagged": False,
            "total_pages": 0,
            "tiers": {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0},
            "elements": {"forms": 0, "images": 0, "tables_suspected": 0},
            "estimated_cost": 0.0,
            "complexity_breakdown": [],
            "pricing_breakdown": {}
        }

    def analyze(self):
        try:
            pdf = pikepdf.Pdf.open(self.stream)
            self.report["total_pages"] = len(pdf.pages)
            
            try:
                mark_info = pdf.Root.MarkInfo
                if mark_info.Marked:
                    self.report["is_tagged"] = True
            except (AttributeError, KeyError):
                self.report["is_tagged"] = False

            for i, page in enumerate(pdf.pages):
                self._assess_page(page, i + 1)
            
            self._calculate_pricing()
            return self.report

        except Exception as e:
            return None

    def _assess_page(self, page, page_num):
        page_score = 0
        
        # 1. Form Detection
        forms_found = 0
        if "/Annots" in page:
            for annot in page.Annots:
                if hasattr(annot, "Subtype") and str(annot.Subtype) == "/Widget":
                    forms_found += 1
                    page_score += 5
        self.report["elements"]["forms"] += forms_found

        # 2. Content Density
        try:
            raw_len = len(page.read_bytes())
            if raw_len > 15000: 
                self.report["elements"]["tables_suspected"] += 1
                page_score += 10
        except:
            pass
            
        # 3. Images
        if "/Resources" in page and "/XObject" in page.Resources:
            try:
                img_count = len(page.Resources.XObject.keys())
                self.report["elements"]["images"] += img_count
                if img_count > 2:
                    page_score += 2
            except:
                pass

        if page_score < 5:
            tier = "Tier 1"
        elif 5 <= page_score < 15:
            tier = "Tier 2"
        else:
            tier = "Tier 3"

        self.report["tiers"][tier] += 1
        self.report["complexity_breakdown"].append(
            {"Page": page_num, "Tier": tier, "Forms": forms_found, "Score": page_score}
        )

    def _calculate_pricing(self):
        rates = {"Tier 1": 10.00, "Tier 2": 17.50, "Tier 3": 35.00}
        MIN_CHARGE = 25.00
        
        multiplier = 2.0 if self.is_rush_order else 1.0
        
        t1_cost = self.report["tiers"]["Tier 1"] * rates["Tier 1"] * multiplier
        t2_cost = self.report["tiers"]["Tier 2"] * rates["Tier 2"] * multiplier
        t3_cost = self.report["tiers"]["Tier 3"] * rates["Tier 3"] * multiplier
        
        raw_total = t1_cost + t2_cost + t3_cost
        final_total = max(raw_total, MIN_CHARGE)
        min_applied = raw_total < MIN_CHARGE
        
        self.report["estimated_cost"] = round(final_total, 2)
        
        self.report["pricing_breakdown"] = {
            "Tier 1 Total": round(t1_cost, 2),
            "Tier 2 Total": round(t2_cost, 2),
            "Tier 3 Total": round(t3_cost, 2),
            "Rush Multiplier Applied": self.is_rush_order,
            "Minimum Applied": min_applied
        }

# --- MAIN APP UI ---

st.title("📄 PDF Scope & Scan")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    is_rush = st.checkbox("🚀 Rush (48hr)", value=False, help="Doubles rates. Does not double min charge.")
    st.divider()
    st.caption("""
    **Pricing Model:**
    * **T1 (Simple):** $10.00/pg
    * **T2 (Struct):** $17.50/pg
    * **T3 (Complex):** $35.00/pg
    * **Min Floor:** $25.00 (per file)
    """)

# Multi-File Upload
uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    results = []
    total_project_cost = 0
    total_pages_all = 0
    
    # Progress bar for batch processing
    progress_bar = st.progress(0)
    
    for i, uploaded_file in enumerate(uploaded_files):
        # Update progress
        progress_bar.progress((i) / len(uploaded_files))
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name

        assessor = PDFComplexityAssessor(tmp_path, is_rush)
        res = assessor.analyze()
        os.remove(tmp_path)
        
        if res:
            res['filename'] = uploaded_file.name
            results.append(res)
            total_project_cost += res['estimated_cost']
            total_pages_all += res['total_pages']
            
    progress_bar.progress(1.0)
    progress_bar.empty()

    if results:
        st.divider()

        # --- 1. AGGREGATE DASHBOARD ---
        h_col1, h_col2, h_col3 = st.columns(3)
        h_col1.metric("Total Files", len(results))
        h_col2.metric("Total Pages", total_pages_all)
        
        rush_label = "Active (2x)" if is_rush else "Standard"
        h_col3.metric("Project Total", f"${total_project_cost:.2f}", delta=rush_label)

        st.divider()

        # --- 2. FILE-BY-FILE BREAKDOWN ---
        st.markdown("##### 📂 File-by-File Analysis")
        
        # Prepare table data
        table_rows = []
        for r in results:
            status_icon = "✅" if r["is_tagged"] else "⚠️"
            min_flag = " (Min Fee)" if r["pricing_breakdown"]["Minimum Applied"] else ""
            
            table_rows.append({
                "File Name": f"{status_icon} {r['filename']}",
                "Pages": r['total_pages'],
                "Tier 1": r['tiers']['Tier 1'],
                "Tier 2": r['tiers']['Tier 2'],
                "Tier 3": r['tiers']['Tier 3'],
                "Cost": f"${r['estimated_cost']:.2f}{min_flag}"
            })
        
        df_files = pd.DataFrame(table_rows)
        st.dataframe(df_files, use_container_width=True, hide_index=True)

        # --- 3. DETAILED BREAKDOWN (Expandable) ---
        with st.expander("View Consolidated Line Items"):
            # Sum up tiers across all files
            grand_t1 = sum(r['tiers']['Tier 1'] for r in results)
            grand_t2 = sum(r['tiers']['Tier 2'] for r in results)
            grand_t3 = sum(r['tiers']['Tier 3'] for r in results)
            
            # Calculate raw costs (re-calculating to handle the aggregation display)
            rates = {1: 10.0, 2: 17.5, 3: 35.0}
            mult = 2.0 if is_rush else 1.0
            
            col_a, col_b = st.columns([1,1])
            with col_a:
                st.markdown("**Consolidated Quantities**")
                st.write(f"- **Tier 1 Pages:** {grand_t1}")
                st.write(f"- **Tier 2 Pages:** {grand_t2}")
                st.write(f"- **Tier 3 Pages:** {grand_t3}")
            
            with col_b:
                st.markdown("**Notes**")
                if is_rush:
                    st.caption("🔴 Rush multiplier applied to all files.")
                st.caption(f"Minimum floor ($25) applies per individual file.")
