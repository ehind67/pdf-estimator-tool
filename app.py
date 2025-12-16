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
    /* Shrink the big Metric numbers */
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    /* Shrink Metric Labels */
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
            "complexity_breakdown": []
        }

    def analyze(self):
        try:
            # Open PDF from stream
            pdf = pikepdf.Pdf.open(self.stream)
            self.report["total_pages"] = len(pdf.pages)
            
            # Check Tagging
            try:
                mark_info = pdf.Root.MarkInfo
                if mark_info.Marked:
                    self.report["is_tagged"] = True
            except (AttributeError, KeyError):
                self.report["is_tagged"] = False

            # Progress Bar (Small)
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Page Loop
            for i, page in enumerate(pdf.pages):
                progress = (i + 1) / self.report["total_pages"]
                progress_bar.progress(progress)
                self._assess_page(page, i + 1)

            status_text.empty()
            progress_bar.empty()
            
            self._calculate_pricing()
            return self.report

        except Exception as e:
            st.error(f"Error analyzing PDF: {str(e)}")
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

        # Determine Tier
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
        # Rates
        rates = {
            "Tier 1": 10.00,
            "Tier 2": 17.50,
            "Tier 3": 35.00
        }
        MIN_CHARGE = 25.00
        
        # 1. Apply Multiplier
        multiplier = 2.0 if self.is_rush_order else 1.0
        
        t1_cost = self.report["tiers"]["Tier 1"] * rates["Tier 1"] * multiplier
        t2_cost = self.report["tiers"]["Tier 2"] * rates["Tier 2"] * multiplier
        t3_cost = self.report["tiers"]["Tier 3"] * rates["Tier 3"] * multiplier
        
        raw_total = t1_cost + t2_cost + t3_cost
        
        # 2. Min Charge Logic
        final_total = max(raw_total, MIN_CHARGE)
        min_applied = raw_total < MIN_CHARGE
        
        self.report["estimated_cost"] = round(final_total, 2)
        
        # Store formatted breakdown
        self.report["pricing_breakdown"] = {
            "Tier 1 Total": round(t1_cost, 2),
            "Tier 2 Total": round(t2_cost, 2),
            "Tier 3 Total": round(t3_cost, 2),
            "Rush Multiplier Applied": "Yes (2x)" if self.is_rush_order else "No",
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
    * **Min Floor:** $25.00
    """)

# File Upload
uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    assessor = PDFComplexityAssessor(tmp_path, is_rush)
    result = assessor.analyze()
    os.remove(tmp_path)

    if result:
        st.divider()

        # --- 1. HEADER & STATUS CALLOUT ---
        # Using columns to put File Name and Status side-by-side
        h_col1, h_col2 = st.columns([3, 1])
        
        with h_col1:
            st.markdown(f"### 📂 {uploaded_file.name}")
        
        with h_col2:
            if result["is_tagged"]:
                st.success("✅ Tagged / PDF/UA Ready")
            else:
                st.error("⚠️ Untagged / Critical")

        st.markdown("---") # Thin separator
        
        # --- 2. COMPACT METRICS (3 Columns Only) ---
        c1, c2, c3 = st.columns(3)
        c1.metric("Pages", result["total_pages"])

        rush_label = "Active (2x)" if is_rush else "Standard"
        c2.metric("Mode", rush_label)

        c3.metric("Est. Quote", f"${result['estimated_cost']:.2f}")

        st.divider()

        # --- 3. LINE ITEMS SUMMARY ---
        st.markdown("##### 🧾 Line Items Summary")
        
        # Create a clean dataframe for display
        p_data = result["pricing_breakdown"]
        
        # Prepare data rows
        rows = [
            ["Tier 1 (Simple Content)", f"{result['tiers']['Tier 1']} pgs", f"${p_data['Tier 1 Total']:.2f}"],
            ["Tier 2 (Structured)",    f"{result['tiers']['Tier 2']} pgs", f"${p_data['Tier 2 Total']:.2f}"],
            ["Tier 3 (Complex/Tables)",f"{result['tiers']['Tier 3']} pgs", f"${p_data['Tier 3 Total']:.2f}"],
        ]
        
        # Convert to DataFrame
        df_display = pd.DataFrame(rows, columns=["Item Description", "Quantity", "Subtotal"])
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        if is_rush:
            st.caption("🔴 *Rush surcharge (2x) included in subtotals above.*")
        
        if p_data["Minimum Applied"]:
            st.warning("⚠️ Minimum Project Floor ($25.00) Applied")

        # --- 4. COST BREAKDOWN GRAPH ---
        st.markdown("##### 📊 Page Tier Distribution")
        
        chart_data = {
            "Tier": ["Tier 1", "Tier 2", "Tier 3"],
            "Pages": [result["tiers"]["Tier 1"], result["tiers"]["Tier 2"], result["tiers"]["Tier 3"]]
        }
        st.bar_chart(data=chart_data, x="Tier", y="Pages", color=["#4CAF50"], height=250)
