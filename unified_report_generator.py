import os
import json
import tempfile
from datetime import datetime
from docxtpl import DocxTemplate
import fitz  # PyMuPDF
from openai import Client
import traceback

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

# --- Utility functions ---
def smart_title(text):
    if not isinstance(text, str):
        return text
    lowercase_exceptions = {"de", "da", "do", "das", "dos", "para", "com", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas"}
    words = text.lower().split()
    return " ".join(
        word if word in lowercase_exceptions else word.capitalize()
        for word in words
    )

def format_caps(text):
    return text.upper() if isinstance(text, str) else text

def format_first(text):
    return text.capitalize() if isinstance(text, str) else text

def safe_date(text):
    try:
        return datetime.strptime(text, "%m/%Y")
    except Exception:
        return None

def parse_date_safe(text):
    try:
        return datetime.strptime(text, "%m/%Y")
    except:
        return None

def trim_text(text, max_chars):
    if not isinstance(text, str):
        return ""
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0]
    return trimmed + "..."

def format_report_date(lang_code):
    today = datetime.today()
    day = today.day
    year = today.year
    month_pt = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
    ]
    month_en = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_index = today.month - 1

    def ordinal(n):
        return f"{n}th" if 11 <= n % 100 <= 13 else f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n % 10]}"

    if lang_code == "PT":
        return f"{day} de {month_pt[month_index]} de {year}"
    else:
        return f"{ordinal(day)} {month_en[month_index]}, {year}"

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
            f"Report language: {report_lang}\n"
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
        if response and hasattr(response, "choices"):
            print("✅ Estrutura válida da resposta:", response.choices[0].message.content)

        if not response.choices or not hasattr(response.choices[0], "message"):
            return {"error": "Unexpected response structure from OpenAI"}

        json_output = response.choices[0].message.content
        print("📥 Conteúdo bruto recebido do modelo:\n", json_output)

        try:
            parsed_data = json.loads(json_output)
            print("✅ JSON interpretado com sucesso.")
            validated_data = enforce_schema(parsed_data, REQUIRED_SCHEMA)
            return validated_data
        except json.JSONDecodeError:
            print("⚠️ Falha ao converter resposta do OpenAI para JSON. Conteúdo bruto será retornado.")
            return {"error": "Could not parse response as JSON. Original content returned.", "json_result": json_output}

    except Exception as e:
        print("Erro durante o parsing do currículo:")
        traceback.print_exc()
        return {"error": str(e)}

# --- REPORT GENERATION ---

def build_context(data):
    # Preprocess line_items for job counts, company dates, and last company logic
    line_items = []
    latest_date = None
    last_company = ""
    for item in data.get("line_items", []):
        # Format company fields
        item["cdd_company"] = format_caps(item.get("cdd_company", ""))
        raw_desc = item.get("company_desc", "")
        item["company_desc"] = trim_text(format_first(raw_desc), 89)
        job_posts = []
        start_dates = []
        end_dates = []

        for job in item.get("job_posts", []):
            job["job_title"] = smart_title(job.get("job_title", ""))
            start = safe_date(job.get("start_date", ""))
            end_str = job.get("end_date", "")
            end = safe_date(end_str) if isinstance(end_str, str) and end_str.lower() != "presente" else None

            if start:
                start_dates.append(start)
            if end:
                end_dates.append(end)

            for task in job.get("job_tasks", []):
                task["task"] = format_first(task.get("task", ""))

            job_posts.append(job)

        item["company_start_date"] = min(start_dates).strftime("%m/%Y") if start_dates else "N/A"
        item["company_end_date"] = max(end_dates).strftime("%m/%Y") if end_dates else "presente"
        item["job_count"] = len(job_posts)
        print("job_count:\n", item["job_count"])
        item["job_posts"] = job_posts
        line_items.append(item)

    # Academics formatting
    for acad in data.get("academics", []):
        acad["academic_course"] = smart_title(acad.get("academic_course", ""))
        acad["academic_institution"] = smart_title(acad.get("academic_institution", ""))

    # Languages formatting (language table mapping is omitted for simplicity)
    for lang in data.get("languages", []):
        lang["language"] = smart_title(lang.get("language", ""))

    # Find the last company worked at (latest end date)
    for item in line_items:
        end_date_str = item.get("company_end_date", "")
        end_date = parse_date_safe(end_date_str)
        if end_date and (latest_date is None or end_date > latest_date):
            latest_date = end_date
            last_company = item.get("cdd_company", "")

    context = {
        "company": format_caps(data.get("company", "")),
        "company_title": format_caps(data.get("company_title", "")),
        "cdd_name": format_caps(data.get("cdd_name", "")),
        "cdd_city": smart_title(data.get("cdd_city", "")),
        "cdd_state": format_caps(data.get("cdd_state", "")),
        "cdd_cel": data.get("cdd_cel", ""),
        "cdd_email": data.get("cdd_email", ""),
        "cdd_nationality": smart_title(data.get("cdd_nationality", "")),
        "cdd_age": data.get("cdd_age", ""),
        "abt_background": data.get("abt_background",""),
        "bhv_profile": data.get("bhv_profile",""),
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
        "line_items": line_items,
        "academics": data.get("academics", []),
        "languages": data.get("languages", []),
        "last_company": last_company,
        "report_lang": data.get("report_lang", "PT"),
        "report_date": format_report_date(data.get("report_lang", "PT"))
    }

    return context

def generate_report_from_data(data, template_path, output_path):
    context = build_context(data)
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
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_file.read())
                tmp_pdf_path = tmp_pdf.name

            json_data = parse_cv_to_json(tmp_pdf_path, language)
            st.subheader("🔎 Dados extraídos do currículo:")
            st.json(json_data)

            if "error" in json_data:
                st.error("❌ Erro retornado pelo parser:")
                st.stop()

            json_data["company"] = company
            json_data["company_title"] = company_title

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
