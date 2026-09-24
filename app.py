import streamlit as st
from fontTools.ttLib import TTFont

# --- ENGINE LOGIC ---
class PDFAdvisorEngine:
    def __init__(self, font_path):
        self.font = TTFont(font_path)
        self.head_table = self.font['head']
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font['hmtx']
        self.units_per_em = self.head_table.unitsPerEm

    def get_char_width(self, char, font_size_pt):
        char_code = ord(char)
        glyph_name = self.cmap.get(char_code)
        if glyph_name:
            advance_width, _ = self.hmtx[glyph_name]
            return (advance_width / self.units_per_em) * font_size_pt
        return font_size_pt * 0.5

    def predict_capacity(self, font_size_pt, width_pt, height_pt, sample_text, line_height_mult=1.2):
        line_height_pt = font_size_pt * line_height_mult
        max_lines = int(height_pt // line_height_pt)
        
        if max_lines < 1:
            return None

        # Sample or standard average character width
        if sample_text:
            sample_widths = [self.get_char_width(c, font_size_pt) for c in sample_text if c != ' ']
            avg_width = sum(sample_widths) / len(sample_widths) if sample_widths else font_size_pt * 0.5
        else:
            avg_width = font_size_pt * 0.5

        wide_width = self.get_char_width('W', font_size_pt)
        narrow_width = self.get_char_width('i', font_size_pt)

        # Capacity metrics
        expected_per_line = int(width_pt // avg_width)
        total_expected = int(max_lines * expected_per_line * 0.88) # 88% wrap efficiency
        total_worst_case = int(max_lines * (width_pt // wide_width))
        total_best_case = int(max_lines * (width_pt // narrow_width))

        return {
            "max_lines": max_lines,
            "expected_safe": total_expected,
            "guaranteed_safe": total_worst_case,
            "absolute_max": total_best_case,
            "expected_per_line": expected_per_line
        }

# --- WEB UI ---
st.set_page_config(page_title="Ariba PDF Layout Advisor", layout="centered")
st.title("📄 PDF Layout Advisor")
st.subheader("Module 1: Character Capacity Predictor")

# Input Form
with st.form("advisor_form"):
    col1, col2 = st.columns(2)
    with col1:
        box_width = st.number_input("Container Width (Points)", value=200, min_value=10)
        box_height = st.number_input("Container Height (Points)", value=36, min_value=5)
    with col2:
        font_size = st.number_input("Font Size (pt)", value=10, min_value=4)
        line_height = st.number_input("Line Height Multiplier", value=1.2, step=0.1)

    sample_data = st.text_input("Sample Data (for character width distribution)", value="Standard PO Line Item Description #1049")
    submit = st.form_submit_button("Calculate Capacity")

# Compute on Submit
if submit:
    try:
        engine = PDFAdvisorEngine("Arial.ttf")
        res = engine.predict_capacity(font_size, box_width, box_height, sample_data, line_height)
        
        if not res:
            st.error("Error: Container height is too small for this font size.")
        else:
            st.success("Analysis Complete!")
            
            # Display Key Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("Recommended Max Chars", f"{res['expected_safe']} chars")
            m2.metric("Guaranteed Safe (Wide)", f"{res['guaranteed_safe']} chars")
            m3.metric("Max Lines Allowed", f"{res['max_lines']} lines")
            
            # Advice Box
            st.info(f"**Field Guidance:** For best results in Ariba PDF generation, cap this field at **{res['expected_safe']} characters**. Expect roughly **{res['expected_per_line']} characters per line**.")
    except Exception as e:
        st.error(f"Error loading font or running analysis: {e}")
