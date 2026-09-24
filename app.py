import streamlit as st
import pandas as pd
from pypdf import PdfReader
from fontTools.ttLib import TTFont
import os

# --- LAYOUT ENGINE DEFINITION ---
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
            # Fallback estimation if font file fails to load
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
        
        # Estimate capacity limit
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

# --- HELPER: PARSE PDF FIELDS ---
def extract_pdf_fields(pdf_file):
    reader = PdfReader(pdf_file)
    extracted_fields = []
    
    fields = reader.get_fields()
    if fields:
        for field_key, field_data in fields.items():
            field_name = field_data.get('/T', field_key)
            field_val = field_data.get('/V', '')
            
            box_width = 150.0
            rect = field_data.get('/Rect')
            if rect and len(rect) == 4:
                box_width = float(rect[2]) - float(rect[0])

            extracted_fields.append({
                "Field Name": str(field_name),
                "Value": str(field_val) if field_val else "Sample " + str(field_name),
                "Box Width (pt)": float(box_width),
                "Font Size (pt)": 10.0
            })
            
    return extracted_fields

# --- STREAMLIT UI ---
st.set_page_config(page_title="PDF Label Layout Advisor", layout="wide")
st.title("📄 PDF Label Layout Advisor")
st.markdown("Upload a PDF form or label to automatically extract fields, detect text overflow/column collision, and re-analyze custom values in real time.")

# Initialize Engine
engine = PDFAdvisorEngine("Arial.ttf")

if not engine.font_loaded:
    st.warning("⚠️ `Arial.ttf` was not found in the root repository folder. Using estimated font metrics fallback.")

# 1. File Upload
uploaded_pdf = st.file_uploader("Upload PDF Label / Form", type=["pdf"])

if uploaded_pdf is not None:
    pdf_fields = extract_pdf_fields(uploaded_pdf)
    
    if not pdf_fields:
        st.warning("No interactive form fields found in PDF. Loading demo fields for preview...")
        pdf_fields = [
            {"Field Name": "PO_Number", "Value": "PO-99482019482-X", "Box Width (pt)": 80.0, "Font Size (pt)": 10.0},
            {"Field Name": "Item_Description", "Value": "Stainless Steel Industrial Grade Hex Bolt Assembly Heavy Duty", "Box Width (pt)": 150.0, "Font Size (pt)": 10.0},
            {"Field Name": "Vendor_Code", "Value": "VEND-10492", "Box Width (pt)": 70.0, "Font Size (pt)": 10.0},
            {"Field Name": "Quantity", "Value": "10000 EA", "Box Width (pt)": 40.0, "Font Size (pt)": 10.0}
        ]

    st.subheader("1. Interactive Field Data Editor")
    st.info("💡 Edit any value or box width below to re-analyze text fit in real time.")

    df_input = pd.DataFrame(pdf_fields)
    
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Field Name": st.column_config.TextColumn("Field Name", required=True),
            "Value": st.column_config.TextColumn("Sample Text / Value", required=True),
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
