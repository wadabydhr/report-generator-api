import os
import json
import tempfile
from datetime import datetime
from docxtpl import DocxTemplate
import fitz  # PyMuPDF
from openai import Client
import traceback
import pandas as pd
import re

# ... [all your previous code, prompt, utility functions, classes, etc. remain UNCHANGED] ...

def run_streamlit():
    import streamlit as st
    st.set_page_config(page_title="Gerador de Relatórios", layout="centered")
    st.title("📄 Gerador de Relatórios de Candidatos")

    uploaded_file = st.file_uploader("📎 Faça upload do currículo (PDF)", type=["pdf"])
    language = st.selectbox("🌐 Idioma do relatório", options=["PT", "EN"])
    company = st.text_input("🏢 Nome da empresa")
    company_title = st.text_input("💼 Título da vaga")

    if st.button("▶️ Gerar Relatório") and uploaded_file and company and company_title:
        with st.spinner("Processando o currículo e gerando relatório..."):
            file_bytes = uploaded_file.read()
            # Save PDF to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(file_bytes)
                tmp_pdf.flush()
                tmp_pdf_path = tmp_pdf.name

            json_data = parse_cv_to_json(tmp_pdf_path, language, company_title=company_title)
            # Clean up PDF temp file after parse
            try:
                os.remove(tmp_pdf_path)
            except Exception:
                pass

            st.subheader("🔎 Dados extraídos do currículo:")
            st.json(json_data)
            if "error" in json_data:
                st.error("❌ Erro retornado pelo parser:")
                st.stop()

            json_data["company"] = company  # always inject or overwrite

            template_path = os.path.join(TEMPLATE_FOLDER, f"Template_Placeholders_{language}.docx")
            safe_name = json_data.get('cdd_name', 'candidato').lower().replace(" ", "_")
            output_filename = f"Relatorio_{safe_name}_{datetime.today().strftime('%Y%m%d')}.docx"
            output_path = os.path.join(tempfile.gettempdir(), output_filename)

            try:
                generate_report_from_data(json_data, template_path, output_path)
            except Exception as e:
                st.error("❌ Erro ao gerar o relatório:")
                st.code(traceback.format_exc())
                st.stop()

            # Read the DOCX as bytes (not as file object) for Streamlit download
            try:
                with open(output_path, "rb") as f:
                    file_bytes = f.read()
                if not file_bytes.startswith(b'PK\x03\x04'):
                    st.error("❌ O arquivo gerado não é um DOCX válido.")
                    st.stop()
                st.download_button(
                    label="📥 Baixar Relatório",
                    data=file_bytes,
                    file_name=output_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error("❌ Erro ao baixar o relatório:")
                st.code(traceback.format_exc())
    else:
        st.info("Por favor, preencha todos os campos e faça o upload do PDF.")

if __name__ == "__main__":
    run_streamlit()