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

# --- ROBUST SPATIAL PARSER ---
def extract_clean_kv_pairs(pdf_file):
    extracted_fields = []
    page_images = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # 1. Render page preview
            p_img = page.to_image(resolution=150).original
            page_images.append(p_img)
            
            # 2. Extract words with precise coordinates
            words = page.extract_words()
            
            # Group words by line (within 4pt vertical position tolerance)
            lines = []
            for word in words:
                assigned = False
                for line in lines:
                    if abs(line['top'] - word['top']) <= 4:
                        line['words'].append(word)
                        assigned = True
                        break
                if not assigned:
                    lines.append({'top': word['top'], 'words': [word]})

            # Sort lines top-to-bottom
            lines = sorted(lines, key=lambda l: l['top'])

            for i, line in enumerate(lines):
                # Sort words left-to-right within line
                line_words = sorted(line['words'], key=lambda w: w['x0'])
                line_text = " ".join([w['text'] for w in line_words])

                # Check if line contains a field label ending with ":" or known headers
                if ":" in line_text:
                    parts = line_text.split(":")
                    header = parts[0].strip()
                    val = ":".join(parts[1:]).strip()

                    # If value is on the line immediately below the header
                    if not val and i + 1 < len(lines):
                        next_line_words = sorted(lines[i + 1]['words'], key=lambda w: w['x0'])
                        val = " ".join([w['text'] for w in next_line_words if abs(w['x0'] - line_words[0]['x0']) < 150])

                    if header:
                        extracted_fields.append({
                            "Extracted Value / Text": val if val else "—",
                            "Constant Header / Field Name": header,
                            "Box Width (pt)": 150.0,
                            "Font Size (pt)": 10.0
                        })

    # Deduplicate while preserving order
    seen = set()
    clean_fields = []
    for item in extracted_fields:
        identifier = (item["Constant Header / Field Name"], item["Extracted Value / Text"])
        if identifier not in seen:
            seen.add(identifier)
            clean_fields.append(item)

    return clean_fields, page_images

# --- STREAMLIT UI ---
st.set_page_config(page_title="PDF Label Layout Advisor", layout="wide")
st.title("📄 PDF Label Layout Advisor")
st.markdown("Upload a PDF form or label to extract text fields, preview the label visually, and analyze text overflow in real time.")

engine = PDFAdvisorEngine("Arial.ttf")

uploaded_pdf = st.file_uploader("Upload PDF Label / Form", type=["pdf"])

if uploaded_pdf is not None:
    pdf_fields, page_images = extract_clean_kv_pairs(uploaded_pdf)
    
    st.subheader("1. Visual Reference & Data Editor")
    col_img, col_data = st.columns([1, 2])
    
    with col_img:
        st.markdown("**PDF Visual Reference:**")
        for img in page_images:
            st.image(img, use_container_width=True)

    with col_data:
        st.markdown("**Interactive Field Data Editor:**")
        st.info("👈 Column 1: **Extracted Value** | Column 2: **Constant Header**")

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

    st.subheader("2. Layout & Overflow Analysis Output")

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
