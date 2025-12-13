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
    def __init__(self, file_stream, base_rate, form_rate):
        self.stream = file_stream
        self.base_rate = base_rate
        self.form_rate = form_rate
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
        # Using raw stream length as a fast proxy for complexity
        try:
            raw_len = len(page.read_bytes())
            if raw_len > 15000: # Threshold for "Heavy" page
                self.report["elements"]["tables_suspected"] += 1
                page_score += 10
        except:
            pass
            
        # 3. Images (XObjects)
        if "/Resources" in page and "/XObject" in page.Resources:
            # Checking resource keys count
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
        # Multipliers
        multipliers = {"Tier 1": 1.0, "Tier 2": 1.75, "Tier 3": 3.5}
        
        t1_cost = self.report["tiers"]["Tier 1"] * self.base_rate * multipliers["Tier 1"]
        t2_cost = self.report["tiers"]["Tier 2"] * self.base_rate * multipliers["Tier 2"]
        t3_cost = self.report["tiers"]["Tier 3"] * self.base_rate * multipliers["Tier 3"]
        
        # Surcharges
        untagged_tax = 0
        if not self.report["is_tagged"]:
            untagged_tax = (t1_cost + t2_cost + t3_cost) * 0.25 # 25% surcharge for untagged
            
        form_cost = self.report["elements"]["forms"] * self.form_rate
        
        total = t1_cost + t2_cost + t3_cost + untagged_tax + form_cost
        self.report["estimated_cost"] = round(total, 2)
        self.report["pricing_breakdown"] = {
            "Content Remediation": round(t1_cost + t2_cost + t3_cost, 2),
            "Untagged Surcharge": round(untagged_tax, 2),
            "Form Remediation": round(form_cost, 2)
        }

# --- MAIN APP UI ---

st.title("📄 PDF Scope & Scan")
st.markdown("### Accessibility Remediation Estimator")

# Sidebar: Settings
with st.sidebar:
    st.header("⚙️ Pricing Configuration")
    base_rate = st.number_input("Base Rate (per page)", value=6.00, step=0.50, help="Your Tier 1 standard text rate.")
    form_rate = st.number_input("Form Field Rate (per field)", value=3.00, step=0.50)
    
    st.info("""
    **Tiers Definition:**
    * **Tier 1 (1.0x):** Simple Text
    * **Tier 2 (1.75x):** Layouts/Simple Tables
    * **Tier 3 (3.5x):** Complex/Technical
    """)

# Main Area: File Upload
uploaded_file = st.file_uploader("Upload a PDF to Analyze", type=["pdf"])

if uploaded_file is not None:
    # Save to temp file to ensure library compatibility
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    # Run Analysis
    assessor = PDFComplexityAssessor(tmp_path, base_rate, form_rate)
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
            st.metric("Structure", tag_status, delta="OK" if result["is_tagged"] else "Critical", delta_color="normal" if result["is_tagged"] else "inverse")
        with col3:
            st.metric("Complex Forms", result["elements"]["forms"])
        with col4:
            st.metric("Est. Quote", f"${result['estimated_cost']}", delta="Total")

        # DETAILED BREAKDOWN
        st.subheader("📊 Complexity Breakdown")
        
        c1, c2 = st.columns([2, 1])
        
        with c1:
            # Show breakdown chart
            chart_data = {
                "Tier": ["Tier 1 (Simple)", "Tier 2 (Medium)", "Tier 3 (Complex)"],
                "Pages": [result["tiers"]["Tier 1"], result["tiers"]["Tier 2"], result["tiers"]["Tier 3"]]
            }
            st.bar_chart(data=chart_data, x="Tier", y="Pages", color=["#4CAF50"])
            
        with c2:
            st.write("**Pricing Details:**")
            p_data = result["pricing_breakdown"]
            st.write(f"- Content Labor: **${p_data['Content Remediation']}**")
            if p_data['Untagged Surcharge'] > 0:
                st.write(f"- Setup Fee (Untagged): **${p_data['Untagged Surcharge']}**")
            st.write(f"- Form Interaction: **${p_data['Form Remediation']}**")
            st.markdown("---")
            st.write(f"### Total: ${result['estimated_cost']}")

        # ACTIONABLE OUTPUT
        st.subheader("📝 Proposal Language")
        st.text_area("Copy/Paste this into your email:", height=150, value=f"""
Based on our structural audit of {uploaded_file.name}:

- The document contains {result['total_pages']} pages.
- Complexity Analysis: {result['tiers']['Tier 3']} pages identified as high-complexity (Technical/Tables).
- Interactive Elements: {result['elements']['forms']} form fields detected.
- Compliance Target: WCAG 2.1 AA.

Estimated Project Cost: ${result['estimated_cost']}
Timeline Estimate: {max(2, result['total_pages'] // 10)} Business Days.
        """)
