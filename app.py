import streamlit as st
import pandas as pd
import pdfplumber
from fontTools.ttLib import TTFont
import os

# --- LAYOUT ENGINE ---
class PDFAdvisorEngine:
    def __init__(self, font_path):
        self.font_loaded = False
        if os.path.exists(font_path):
            try:
                self.font = TTFont(font_path)
                self.head_table = self.font['head']
                self.cmap = self.font.getBestCmap()
                self.hmtx = self.font['hmtx']
                self.units_per_em = self.head_table.unitsPerEm
                self.font_loaded = True
            except Exception:
                self.font_loaded = False

    def get_char_width(self, char, font_size_pt):
        if not self.font_loaded:
            return font_size_pt * 0.55
        
        char_code = ord(char)
        glyph_name = self.cmap.get(char_code)
        if glyph_name:
            advance_width, _ = self.hmtx[glyph_name]
            return (advance_width / self.units_per_em) * font_size_pt
        return font_size_pt * 0.5

    def measure_text_width(self, text, font_size_pt):
        if not text:
            return 0.0
        return sum(self.get_char_width(c, font_size_pt) for c in str(text))

    def analyze_field(self, field_name, value, container_width_pt, font_size_pt=10):
        text_str = str(value) if value is not None else ""
        calc_width = self.measure_text_width(text_str, font_size_pt)
        
        overflow = calc_width > container_width_pt
        diff_pt = calc_width - container_width_pt
        
        avg_char_w = calc_width / len(text_str) if len(text_str) > 0 else font_size_pt * 0.5
        max_safe_chars = int(container_width_pt // avg_char_w) if avg_char_w > 0 else 0

        status = "⚠️ OVERFLOW" if overflow else "OK"

        return {
            "Extracted Value / Text": text_str,
            "Constant Header / Field Name": field_name,
            "Value Length": len(text_str),
            "Text Width (pt)": round(calc_width, 1),
            "Box Width (pt)": round(container_width_pt, 1),
            "Overflow Status": status,
            "Overlap Margin (pt)": round(diff_pt, 1) if overflow else 0.0,
            "Max Safe Chars": max_safe_chars
        }

# --- PDF SPATIAL PARSER & VISUAL RENDERER ---
def extract_label_data_spatially(pdf_file):
    extracted_fields = []
    page_images = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # Render visual reference image of PDF page
            p_img = page.to_image(resolution=150).original
            page_images.append(p_img)
            
            # Group words by vertical line position (y-axis)
            words = page.extract_words()
            lines_dict = {}
            for w in words:
                top_key = round(w["top"], -1)  # group words within 10pt vertical height
                lines_dict.setdefault(top_key, []).append(w)

            # Process line by line
            for top_pos in sorted(lines_dict.keys()):
                line_words = sorted(lines_dict[top_pos], key=lambda x: x["x0"])
                
                # Split line into Left Column (x0 < midpoint) and Right Column (x0 >= midpoint)
                midpoint = page.width / 2.0
                left_words = [w["text"] for w in line_words if w["x0"] < midpoint]
                right_words = [w["text"] for w in line_words if w["x0"] >= midpoint]
                
                # Parse Left Column
                if left_words:
                    l_text = " ".join(left_words)
                    if ":" in l_text:
                        parts = l_text.split(":", 1)
                        header = parts[0].strip()
                        val = parts[1].strip()
                    else:
                        header = "Field_" + str(len(extracted_fields) + 1)
                        val = l_text
                    
                    if val:
                        extracted_fields.append({
                            "Extracted Value / Text": val,
                            "Constant Header / Field Name": header,
                            "Box Width (pt)": round(midpoint - 20, 1),
                            "Font Size (pt)": 10.0
                        })

                # Parse Right Column
                if right_words:
                    r_text = " ".join(right_words)
                    if ":" in r_text:
                        parts = r_text.split(":", 1)
                        header = parts[0].strip()
                        val = parts[1].strip()
                    else:
                        header = "Field_" + str(len(extracted_fields) + 1)
                        val = r_text

                    if val:
                        extracted_fields.append({
                            "Extracted Value / Text": val,
                            "Constant Header / Field Name": header,
                            "Box Width (pt)": round(midpoint - 20, 1),
                            "Font Size (pt)": 10.0
                        })

    return extracted_fields, page_images

# --- STREAMLIT UI ---
st.set_page_config(page_title="PDF Label Layout Advisor", layout="wide")
st.title("📄 PDF Label Layout Advisor")
st.markdown("Upload a PDF form or label to extract text fields, preview the label visually, and analyze text overflow in real time.")

engine = PDFAdvisorEngine("Arial.ttf")

uploaded_pdf = st.file_uploader("Upload PDF Label / Form", type=["pdf"])

if uploaded_pdf is not None:
    pdf_fields, page_images = extract_label_data_spatially(uploaded_pdf)
    
    st.subheader("1. Visual Reference Preview")
    col_img, col_data = st.columns([1, 2])
    
    with col_img:
        st.markdown("**PDF Visual Reference:**")
        for img in page_images:
            st.image(img, use_container_width=True)

    with col_data:
        st.markdown("**2. Interactive Field Data Editor:**")
        st.info("💡 Header is on the Right side and Value on the Left. Edit any cell below to re-analyze fit!")

        df_input = pd.DataFrame(pdf_fields)
        
        edited_df = st.data_editor(
            df_input,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Extracted Value / Text": st.column_config.TextColumn("Extracted Value / Text (LEFT)", required=True),
                "Constant Header / Field Name": st.column_config.TextColumn("Constant Header / Field Name (RIGHT)", required=True),
                "Box Width (pt)": st.column_config.NumberColumn("Container Width (pt)", min_value=10, step=5),
                "Font Size (pt)": st.column_config.NumberColumn("Font Size (pt)", min_value=6, max_value=72, step=1)
            }
        )

    st.subheader("3. Layout & Overflow Analysis Output")

    results = []
    for _, row in edited_df.iterrows():
        res = engine.analyze_field(
            field_name=row["Constant Header / Field Name"],
            value=row["Extracted Value / Text"],
            container_width_pt=float(row["Box Width (pt)"]),
            font_size_pt=float(row["Font Size (pt)"])
        )
        results.append(res)

    df_results = pd.DataFrame(results)

    def highlight_overflow(val):
        color = '#ff4b4b' if val == '⚠️ OVERFLOW' else '#28a745'
        return f'background-color: {color}; color: white; font-weight: bold;'

    st.dataframe(
        df_results.style.map(highlight_overflow, subset=['Overflow Status']),
        use_container_width=True
    )

    overflow_count = sum(1 for r in results if r["Overflow Status"] == "⚠️ OVERFLOW")
    if overflow_count > 0:
        st.error(f"⚠️ Warning: {overflow_count} field(s) exceed their container width and risk spilling into adjacent columns!")
    else:
        st.success("✅ All fields fit within their allotted box dimensions!")
else:
    st.info("👆 Please upload a PDF file above to begin analysis.")
