import os
import json
import tempfile
from datetime import datetime
from docxtpl import DocxTemplate
import fitz  # PyMuPDF
from openai import Client
import traceback

# --- CONSTANTS AND SCHEMA ---
UPLOAD_FOLDER = 'uploads'
TEMPLATE_FOLDER = 'template'
STATIC_FOLDER = 'static'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMPLATE_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

REQUIRED_SCHEMA = {
    "company": "",
    "company_title": "",
    "cdd_name": "",
    "cdd_email": "",
    "cdd_city": "",
    "cdd_state": "",
    "cdd_cel": "",
    "cdd_age": "",
    "cdd_nationality": "",
    "abt_background": "",
    "bhv_profile": "",
    "job_bond": "",
    "job_wage": "",
    "job_variable": "",
    "job_meal": "",
    "job_food": "",
    "job_health": "",
    "job_dental": "",
    "job_life": "",
    "job_pension": "",
    "job_others": "",
    "job_expectation": "",
    "last_company": "",
    "report_lang": "",
    "report_date": "",
    "line_items": [{
        "cdd_company": "",
        "company_desc": "",
        "job_posts": [{
            "job_title": "",
            "start_date": "",
            "end_date": "",
            "job_tasks": [{"task": ""}]
        }]
    }],
    "academics": [{
        "academic_course": "",
        "academic_institution": "",
        "academic_conclusion": ""
    }],
    "languages": [{
        "language": "",
        "language_level": ""
    }]
}

# --- UTILS ---

def enforce_schema(data, schema):
    if isinstance(schema, dict):
        result = {}
        for key, default in schema.items():
            if key in data:
                result[key] = enforce_schema(data[key], default)
            else:
                result[key] = enforce_schema(default, default)
        return result
    elif isinstance(schema, list):
        if not isinstance(data, list) or not data:
            return schema
        template = schema[0]
        return [enforce_schema(item, template) for item in data]
    else:
        return data if data is not None else schema

# --- CV PARSING ---

def parse_cv_to_json(file_path, report_lang):
    client = Client(api_key=os.getenv("OPENAI_API_KEY"))
    if not file_path:
        return {"error": "Missing CV file"}

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            with open(file_path, "rb") as source_file:
                tmp.write(source_file.read())
            pdf_path = tmp.name

        extracted_text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                extracted_text += page.get_text()

        extracted_text = extracted_text.replace("{", "{{").replace("}", "}}")

        schema_example = json.dumps(REQUIRED_SCHEMA, ensure_ascii=False, indent=2)
        system_prompt = (
            "You are a system that converts resumes into structured JSON for automation. "
            "You must follow exactly the structure of the provided schema. "
            "All keys must be present and correctly named. If a value is missing, use an empty string, empty list, or the correct type. "
            "Do not omit, rename, or add any keys."
        )

        user_prompt = (
            "Extract ALL possible information from the following CV content and map it into the provided schema. "
            "Your response must be a single well-formatted JSON object with exactly the same keys and structure as the schema below. "
            "If you cannot fill a value, leave it blank or as an empty list/object. "
            "Do not explain, only output the JSON object.\n\n"
            "Schema example:\n"
            f"{schema_example}\n\n"
            "CV Content:\n"
            f"{extracted_text}"
        )
        print("🟢 Início do parse_cv_to_json")
        print("🗂️ Caminho do arquivo:", file_path)
        print("🌐 Idioma:", report_lang)
        print("🧠 Preparando prompt para envio ao OpenAI")
        print("📜 Texto extraído:", extracted_text[:200])  # mostra trecho

        print("📤 Enviando prompt para OpenAI...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        print("📥 Resposta recebida da OpenAI.")
        if not response.choices or not hasattr(response.choices[0], "message"):
            return {"error": "Unexpected response structure from OpenAI"}

        json_output = response.choices[0].message.content

        try:
            parsed_data = json.loads(json_output)
            print("✅ JSON interpretado com sucesso.")
            validated_data = enforce_schema(parsed_data, REQUIRED_SCHEMA)
        except json.JSONDecodeError:
            print("⚠️ Falha ao converter resposta do OpenAI para JSON. Conteúdo bruto será retornado.")
            return {"error": "Could not parse response as JSON. Original content returned.", "json_result": json_output}

        # NEW: If requested language is EN, translate all string values.
        if report_lang.upper() == "EN":
            translation_system_prompt = (
                "You are an assistant that ONLY translates the string values in JSON objects, keeping the structure and key names unchanged."
            )
            translation_user_prompt = (
                f"Translate ALL string values in the following JSON to English (do not touch key names, only the values, including nested and list values, and do not skip any field):\n\n"
                f"{json.dumps(validated_data, ensure_ascii=False, indent=2)}"
            )
            print("📤 Enviando prompt para OpenAI (translation)...")
            translation_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": translation_system_prompt},
                    {"role": "user", "content": translation_user_prompt}
                ],
                temperature=0.3
            )
            if translation_response.choices and hasattr(translation_response.choices[0], "message"):
                translation_json_output = translation_response.choices[0].message.content
                try:
                    translated_data = json.loads(translation_json_output)
                    print("✅ JSON traduzido com sucesso.")
                    translated_data["report_lang"] = report_lang
                    return translated_data
                except Exception as e:
                    print("⚠️ Falha ao converter JSON traduzido:", e)
                    return {"error": "Could not parse translated JSON. Original content returned.", "json_result": translation_json_output}
            else:
                print("⚠️ Falha na resposta de tradução.")
                return {"error": "Translation step failed."}
        else:
            validated_data["report_lang"] = report_lang
            return validated_data

    except Exception as e:
        print("Erro durante o parsing do currículo:")
        traceback.print_exc()
        return {"error": str(e)}

# --- REPORT GENERATION ---

def generate_report_from_data(data, template_path, output_path):
    context = {
        "company": data.get("company", ""),
        "company_title": data.get("company_title", ""),
        "cdd_name": data.get("cdd_name", ""),
        "cdd_email": data.get("cdd_email", ""),
        "cdd_city": data.get("cdd_city", ""),
        "cdd_state": data.get("cdd_state", ""),
        "cdd_cel": data.get("cdd_cel", ""),
        "cdd_age": data.get("cdd_age", ""),
        "cdd_nationality": data.get("cdd_nationality", ""),
        "abt_background": data.get("abt_background", ""),
        "bhv_profile": data.get("bhv_profile", ""),
        "job_bond": data.get("job_bond", ""),
        "job_wage": data.get("job_wage", ""),
        "job_variable": data.get("job_variable", ""),
        "job_meal": data.get("job_meal", ""),
        "job_food": data.get("job_food", ""),
        "job_health": data.get("job_health", ""),
        "job_dental": data.get("job_dental", ""),
        "job_life": data.get("job_life", ""),
        "job_pension": data.get("job_pension", ""),
        "job_others": data.get("job_others", ""),
        "job_expectation": data.get("job_expectation", ""),
        "last_company": data.get("last_company", ""),
        "report_lang": data.get("report_lang", ""),
        "report_date": data.get("report_date", ""),
        "academics": data.get("academics", []),
        "languages": data.get("languages", [])
    }

    # Process line_items
    line_items = []
    for item in data.get("line_items", []):
        job_posts = []
        for job in item.get("job_posts", []):
            job_posts.append({
                "job_title": job.get("job_title", ""),
                "start_date": job.get("start_date", ""),
                "end_date": job.get("end_date", ""),
                "job_tasks": job.get("job_tasks", [])
            })
        line_items.append({
            "cdd_company": item.get("cdd_company", ""),
            "company_desc": item.get("company_desc", ""),
            "job_posts": job_posts
        })
    context["line_items"] = line_items

    try:
        doc = DocxTemplate(template_path)
        doc.render(context)
        doc.save(output_path)
    except Exception as e:
        print("Erro ao gerar o relatório:")
        traceback.print_exc()
        raise e  # let the exception be visible for debugging

# --- MAIN STREAMLIT APP ---

def run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="Gerador de Relatórios", layout="centered")
    st.title("📄 Gerador de Relatórios de Candidatos")

    # Inputs do formulário
    uploaded_file = st.file_uploader("📎 Faça upload do currículo (PDF)", type=["pdf"])
    language = st.selectbox("🌐 Idioma do relatório", options=["PT", "EN"])
    company = st.text_input("🏢 Nome da empresa")
    company_title = st.text_input("💼 Título da vaga")

    if st.button("▶️ Gerar Relatório") and uploaded_file and company and company_title:
        with st.spinner("Processando o currículo e gerando relatório..."):
            # Salvar PDF temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_file.read())
                tmp_pdf_path = tmp_pdf.name

            # Processar PDF para gerar JSON
            json_data = parse_cv_to_json(tmp_pdf_path, language)
            st.subheader("🔎 Dados extraídos do currículo:")
            st.json(json_data)

            if "error" in json_data:
                st.error("❌ Erro retornado pelo parser:")
                st.stop()

            # Adiciona os novos campos ao JSON
            json_data["company"] = company
            json_data["company_title"] = company_title

            # Escolher o template correto
            template_path = os.path.join(TEMPLATE_FOLDER, f"Template_Placeholders_{language}.docx")

            # Gerar nome do arquivo
            safe_name = json_data.get('cdd_name', 'candidato').lower().replace(" ", "_")
            output_filename = f"Relatorio_{safe_name}_{datetime.today().strftime('%Y%m%d')}.docx"
            output_path = os.path.join(tempfile.gettempdir(), output_filename)

            # Gerar o relatório .docx
            try:
                generate_report_from_data(json_data, template_path, output_path)
            except Exception as e:
                st.error("❌ Erro ao gerar o relatório:")
                st.code(traceback.format_exc())
                st.stop()

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

if __name__ == "__main__":
    run_streamlit()