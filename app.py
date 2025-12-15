import streamlit as st
import pikepdf
from pdfminer.layout import LTTextContainer
from pdfminer.high_level import extract_pages
import tempfile
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PDF Scope & Scan",
    page_icon="📄",
    layout="wide"
)

# --- CSS FOR STYLING ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
    .stAlert {
        font-weight: bold;
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

            # Progress Bar
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Page Loop
            for i, page in enumerate(pdf.pages):
                # Update progress
                progress = (i + 1) / self.report["total_pages"]
                progress_bar.progress(progress)
                status_text.text(f"Scanning page {i+1}...")
                
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

        # 2. Content Density (Heuristic for Tables/Vectors)
        try:
            raw_len = len(page.read_bytes())
            if raw_len > 15000: # Threshold for "Heavy" page
                self.report["elements"]["tables_suspected"] += 1
                page_score += 10
        except:
            pass
            
        # 3. Images (XObjects)
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
        # NEW: Hardcoded Rates
        rates = {
            "Tier 1": 10.00,
            "Tier 2": 17.50,
            "Tier 3": 35.00
        }
        
        # Rush Multiplier (2x if checked, 1x if not)
        multiplier = 2.0 if self.is_rush_order else 1.0
        
        t1_cost = self.report["tiers"]["Tier 1"] * rates["Tier 1"] * multiplier
        t2_cost = self.report["tiers"]["Tier 2"] * rates["Tier 2"] * multiplier
        t3_cost = self.report["tiers"]["Tier 3"] * rates["Tier 3"] * multiplier
        
        total = t1_cost + t2_cost + t3_cost
        self.report["estimated_cost"] = round(total, 2)
        
        # Store breakdown for display
        self.report["pricing_breakdown"] = {
            "Tier 1 Total": round(t1_cost, 2),
            "Tier 2 Total": round(t2_cost, 2),
            "Tier 3 Total": round(t3_cost, 2),
            "Rush Multiplier Applied": "Yes (2x)" if self.is_rush_order else "No"
        }

# --- MAIN APP UI ---

st.title("📄 PDF Scope & Scan")
st.markdown("### Accessibility Remediation Estimator")

# Sidebar: Simple Settings
with st.sidebar:
    st.header("⚙️ Settings")
    
    # NEW: Rush Order Checkbox
    is_rush = st.checkbox("🚀 Rush Processing (48hr)", value=False, help="Doubles the tier rates for expedited delivery.")
    
    st.divider()
    st.info("""
    **Standard Pricing:**
    * **Tier 1 (Simple):** $10.00/pg
    * **Tier 2 (Structured):** $17.50/pg
    * **Tier 3 (Complex):** $35.00/pg
    
    *Rush processing applies 2x multiplier.*
    """)

# Main Area: File Upload
uploaded_file = st.file_uploader("Upload a PDF to Analyze", type=["pdf"])

if uploaded_file is not None:
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    # Run Analysis (Pass in the rush status)
    assessor = PDFComplexityAssessor(tmp_path, is_rush)
    result = assessor.analyze()
    
    # Clean up temp file
    os.remove(tmp_path)

    if result:
        st.divider()
        
        # TOP LINE METRICS
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Pages", result["total_pages"])
        with col2:
            tag_status = "Tagged" if result["is_tagged"] else "Untagged"
            st.metric("Structure", tag_status, delta="OK" if result["is_tagged"] else "Check", delta_color="normal" if result["is_tagged"] else "off")
        with col3:
            rush_label = "Active (2x)" if is_rush else "Standard"
            st.metric("Processing Mode", rush_label)
        with col4:
            st.metric("Est. Quote", f"${result['estimated_cost']}", delta="Total Project")

        # DETAILED BREAKDOWN
        st.subheader("📊 Cost Breakdown")
        
        c1, c2 = st.columns([2, 1])
        
        with c1:
            # Show breakdown chart
            chart_data = {
                "Tier": ["Tier 1 ($10)", "Tier 2 ($17.50)", "Tier 3 ($35)"],
                "Pages": [result["tiers"]["Tier 1"], result["tiers"]["Tier 2"], result["tiers"]["Tier 3"]]
            }
            st.bar_chart(data=chart_data, x="Tier", y="Pages", color=["#4CAF50"])
            
        with c2:
            st.write("**Line Items:**")
            p_data = result["pricing_breakdown"]
            st.write(f"- Tier 1 Content: **${p_data['Tier 1 Total']}**")
            st.write(f"- Tier 2 Content: **${p_data['Tier 2 Total']}**")
            st.write(f"- Tier 3 Content: **${p_data['Tier 3 Total']}**")
            
            if is_rush:
                 st.markdown("---")
                 st.write("🔴 **Rush Surcharge Applied**")
            
            st.markdown("---")
            st.write(f"### Total: ${result['estimated_cost']}")

        # Removed Proposal Language Section as requested
