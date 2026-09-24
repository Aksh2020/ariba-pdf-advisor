import streamlit as st
import pandas as pd
import pdfplumber
from fontTools.ttLib import TTFont
import re
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
            "Field Name": field_name,
            "Current Value": text_str,
            "Value Length": len(text_str),
            "Text Width (pt)": round(calc_width, 1),
            "Box Width (pt)": round(container_width_pt, 1),
            "Overflow Status": status,
            "Overlap Margin (pt)": round(diff_pt, 1) if overflow else 0.0,
            "Max Safe Chars": max_safe_chars
        }

# --- PDF TEXT & KEY-VALUE PARSER ---
def extract_label_data_from_pdf(pdf_file):
    extracted_fields = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text_lines = page.extract_text().split("\n")
            
            for line in text_lines:
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Check for "Label: Value" patterns (e.g. "Supplier Name: GE_Test_R...")
                if ":" in line_str:
                    parts = line_str.split(":", 1)
                    label = parts[0].strip()
                    val = parts[1].strip()
                    
                    if label and val:
                        extracted_fields.append({
                            "Field Name": label,
                            "Value": val,
                            "Box Width (pt)": 180.0,  # Default column width allowance
                            "Font Size (pt)": 10.0
                        })
                else:
                    # Generic line text capture
                    if len(line_str) > 3:
                        extracted_fields.append({
                            "Field Name": line_str[:15] + "...",
                            "Value": line_str,
                            "Box Width (pt)": 200.0,
                            "Font Size (pt)": 10.0
                        })
                        
    return extracted_fields

# --- STREAMLIT UI ---
st.set_page_config(page_title="PDF Label Layout Advisor", layout="wide")
st.title("📄 PDF Label Layout Advisor")
st.markdown("Upload a PDF form or label to automatically extract text fields, detect overflow, and test values in real time.")

engine = PDFAdvisorEngine("Arial.ttf")

uploaded_pdf = st.file_uploader("Upload PDF Label / Form", type=["pdf"])

if uploaded_pdf is not None:
    pdf_fields = extract_label_data_from_pdf(uploaded_pdf)
    
    if pdf_fields:
        st.success(f"Successfully extracted {len(pdf_fields)} text elements from PDF!")
    else:
        st.warning("Could not extract structured text lines. Loading sample data...")
        pdf_fields = [
            {"Field Name": "Supplier Name", "Value": "GE_Test_R_The National Board Of Boiler - TEST", "Box Width (pt)": 180.0, "Font Size (pt)": 10.0},
            {"Field Name": "Delivery Date", "Value": "11/16/2026", "Box Width (pt)": 100.0, "Font Size (pt)": 10.0},
            {"Field Name": "ASN / Packing Slip Number", "Value": "42300296111-3", "Box Width (pt)": 120.0, "Font Size (pt)": 10.0}
        ]

    st.subheader("1. Interactive Field Data Editor")
    st.info("💡 Edit any value or box width below to re-analyze text fit in real time.")

    df_input = pd.DataFrame(pdf_fields)
    
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Field Name": st.column_config.TextColumn("Field Name / Label", required=True),
            "Value": st.column_config.TextColumn("Extracted Value / Text", required=True),
            "Box Width (pt)": st.column_config.NumberColumn("Container Width (pt)", min_value=10, step=5),
            "Font Size (pt)": st.column_config.NumberColumn("Font Size (pt)", min_value=6, max_value=72, step=1)
        }
    )

    st.subheader("2. Layout & Overflow Analysis Output")

    results = []
    for _, row in edited_df.iterrows():
        res = engine.analyze_field(
            field_name=row["Field Name"],
            value=row["Value"],
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
