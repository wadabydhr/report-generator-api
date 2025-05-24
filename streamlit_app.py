
import streamlit as st
import tempfile
import os
import json
from datetime import datetime
from parse_cv_to_json import parse_cv_to_json  # função esperada no seu arquivo
from app import generate_report  # função esperada no seu arquivo

st.set_page_config(page_title="Gerador de Relatórios", layout="centered")

st.title("📄 Gerador de Relatórios de Candidatos")

# Inputs do formulário
uploaded_file = st.file_uploader("📎 Faça upload do currículo (PDF)", type=["pdf"])
language = st.selectbox("🌐 Idioma do relatório", options=["PT", "EN"])
company = st.text_input("🏢 Nome da empresa")
job_title = st.text_input("💼 Título da vaga")

# Botão de geração
if st.button("▶️ Gerar Relatório") and uploaded_file and company and job_title:
    with st.spinner("Processando o currículo e gerando relatório..."):
        # Salvar PDF temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(uploaded_file.read())
            tmp_pdf_path = tmp_pdf.name

        # Processar PDF para gerar JSON
        json_data = parse_cv_to_json(
            tmp_pdf_path,
            language,
            inputBenefits
        )

        # Adiciona os novos campos ao JSON
        json_data["company"] = company
        json_data["job_title"] = job_title

        # Salvar JSON temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp_json:
            json.dump(json_data, tmp_json, ensure_ascii=False, indent=2)
            tmp_json_path = tmp_json.name

        # Escolher o template correto
        template_path = os.path.join("template", f"Template_Placeholders_{language}.docx")

        # Gerar nome do arquivo
        output_filename = f"Relatorio_{json_data.get('cdd_name','candidato')}_{datetime.today().strftime('%Y%m%d')}.docx"
        output_path = os.path.join(tempfile.gettempdir(), output_filename)

        # Gerar o relatório .docx
        generate_report(json_path=tmp_json_path, template_path=template_path, output_path=output_path)

        # Exibir link de download
        with open(output_path, "rb") as f:
            st.download_button(
                label="📥 Baixar Relatório",
                data=f,
                file_name=output_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
else:
    st.info("Por favor, preencha todos os campos e faça o upload do PDF.")
