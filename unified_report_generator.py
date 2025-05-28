import os
import json
import tempfile
from datetime import datetime
from docxtpl import DocxTemplate
import fitz  # PyMuPDF
from openai import Client
import traceback
import pandas as pd

# --- Utility functions ---
def smart_title(text):
    if not isinstance(text, str):
        return text
    lowercase_exceptions = {"de", "da", "do", "das", "dos", "para", "com", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas", "of"}
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
        "language_level": "",
        "level_description": ""
    }]
}

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

def translate_text(text, target_lang):
    if not text or text.strip() == "":
        return text
    client = Client(api_key=os.getenv("OPENAI_API_KEY"))
    sys_prompt = (
        f"You are a translation assistant. Translate the following text to {target_lang.upper()} in a formal, business-appropriate way. "
        "Return only the translated text, without quotes or explanations."
    )
    user_prompt = text
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        if response.choices and hasattr(response.choices[0], "message"):
            return response.choices[0].message.content.strip()
    except Exception as e:
        print("Translation error:", e)
    return text

# --- GOOGLE SHEET LANGUAGE LEVELS ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1q8hKLWcizUK2moUxQpiLHCyB5FHYVpPPNiyvq0NB_mM/export?format=csv"
df_levels = pd.read_csv(SHEET_URL)
df_levels["language_level"] = df_levels["language_level"].astype(str)  # Ensure all keys are str for matching

LANGUAGE_LEVELS_EN = [
    "Elementary (basic knowledge)",
    "Pre-operational (basic with intermediary skill in conversation or writing)",
    "Operational (intermediary knowledge)",
    "Extended (intermediary with advanced skill only in conversation or writing)",
    "Expert (advanced knowledge or native or fluent)"
]
LANGUAGE_LEVELS_PT = [
    "Elementar (conhecimento básico)",
    "Pre-operacional (básico com habilidade intermediária em conversação ou escrita)",
    "Operacional (conhecimento intermediário)",
    "Intermediário (intermediário com habilidade avançada apenas em conversação ou escrita)",
    "Avançado / Fluente (conhecimento avançado, nativo ou fluente)"
]

# Build direct mapping for PT and EN for title and description
PT_LEVELS = {}
EN_LEVELS = {}
for _, row in df_levels.iterrows():
    pt_title = str(row.get("language_level_title_pt", "")).strip().lower()
    en_title = str(row.get("language_level_title_en", "")).strip().lower()
    if pt_title:
        PT_LEVELS[pt_title] = {
            "language_level": row.get("language_level_title_pt", ""),
            "level_description": row.get("level_description_pt", "")
        }
    if en_title:
        EN_LEVELS[en_title] = {
            "language_level": row.get("language_level_title_en", ""),
            "level_description": row.get("level_description_en", "")
        }

def find_level_entry(level_value, report_lang):
    """
    Try to match the OpenAI-provided level (may have accents or case diff) to the correct localized level.
    Returns dict or None.
    """
    if not level_value:
        return None
    key = str(level_value).strip().lower()
    if report_lang.upper() == "PT":
        # Try exact and fuzzy match in PT_LEVELS
        if key in PT_LEVELS:
            return PT_LEVELS[key]
        for k in PT_LEVELS:
            if key in k or k in key:
                return PT_LEVELS[k]
    else:
        # Try exact and fuzzy match in EN_LEVELS
        if key in EN_LEVELS:
            return EN_LEVELS[key]
        for k in EN_LEVELS:
            if key in k or k in key:
                return EN_LEVELS[k]
    return None

# --- CV PARSING ---

def parse_cv_to_json(file_path, report_lang, company_title=None):
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
        # Use correct levels in the prompt
        if report_lang.upper() == "PT":
            language_levels_for_prompt = LANGUAGE_LEVELS_PT
        else:
            language_levels_for_prompt = LANGUAGE_LEVELS_EN

        extraction_prompt = (
            "You are a system that converts resumes (CVs) into structured JSON for automation. "
            "You must extract all possible information from the following CV content and map it into the provided schema. "
            "All keys must be present and correctly named. If a value is missing, use an empty string, empty list, or the correct type. "
            "Do not omit, rename, or add any keys. Do not summarize or invent information."
            "\n\n"
            "All the acronyms must be in uppercase.\n"
            "Nationality (cdd_nationality), if exists, must be corrected instead to the name of the country for the language selected. Eg: Brazilian instead of Brazil.\n"
            "\n\n"
            "For each company (cdd_company), extract all job positions (job_title) the candidate held. "
            "For each job_title, extract all tasks/activities/descriptions performed by the candidate as individual items in the 'job_tasks' list. "
            "Tasks must be separated into items according to their functional category or similarity, "
            "and must remain as close as possible to the original text, only correcting grammar and spelling. "
            "Do NOT summarize, merge, or transform the context of the tasks—just divide them into items according to similarity."
            "\n\n"
            "For the languages section: extract all languages and their level (language_level) the candidate describes except Portuguese language"
            "Map the extracted language level to one of the following five levels exactly (case-insensitive): "
            + "; ".join(language_levels_for_prompt) +
            "."
            "\n\n"
            "If the report language is 'EN', translate ALL string values in the output JSON to English, including nested/list values. "
            "If the report language is 'PT', translate ALL string values in the output JSON to Portuguese, including nested/list values. "
            "Do NOT translate key names, only values. Output only the JSON object."
            "For academics section: academic_conclusion must be the end date of a course when there is a range of dates, always picking the most recent date of the range."
            "\n\n"
            "Schema example:\n"
            f"{schema_example}\n\n"
            "Report language: " + report_lang + "\n"
            "CV Content:\n"
            f"{extracted_text}"
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You output JSON for structured candidate analysis. Follow user instructions."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=0.3
        )
        if not response.choices or not hasattr(response.choices[0], "message"):
            return {"error": "Unexpected response structure from OpenAI"}

        json_output = response.choices[0].message.content

        try:
            parsed_data = json.loads(json_output)
            validated_data = enforce_schema(parsed_data, REQUIRED_SCHEMA)
        except json.JSONDecodeError:
            return {"error": "Could not parse response as JSON. Original content returned.", "json_result": json_output}

        # Inject or correct company_title before translation if present
        if company_title is not None:
            validated_data["company_title"] = company_title

        # --- LANGUAGE LEVELS POST-PROCESSING ---
        updated_languages = []
        for lang_row in validated_data.get("languages", []):
            level_value = lang_row.get("language_level", "")
            level_entry = find_level_entry(level_value, report_lang)
            if level_entry:
                lang_row["language_level"] = level_entry.get("language_level", level_value)
                lang_row["level_description"] = level_entry.get("level_description", "")
            else:
                lang_row["level_description"] = ""
            updated_languages.append(lang_row)
        validated_data["languages"] = updated_languages

        # Step 2: If EN or PT, translate all string values in the JSON, including injected company_title, to the target language.
        if report_lang.upper() in ("EN", "PT"):
            translation_system_prompt = (
                "You are an assistant that ONLY translates the string values in JSON objects, keeping the structure and key names unchanged."
            )
            target_language = "English" if report_lang.upper() == "EN" else "Portuguese"
            translation_user_prompt = (
                f"Translate ALL string values in the following JSON to {target_language} "
                "(do not touch key names, only the values, including nested and list values, and do not skip any field):\n\n"
                f"{json.dumps(validated_data, ensure_ascii=False, indent=2)}"
            )
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
                    translated_data["report_lang"] = report_lang
                    return translated_data
                except Exception as e:
                    return {"error": "Could not parse translated JSON. Original content returned.", "json_result": translation_json_output}
            else:
                return {"error": "Translation step failed."}
        else:
            validated_data["report_lang"] = report_lang
            return validated_data

    except Exception as e:
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
        item["job_posts"] = job_posts
        line_items.append(item)

    # Academics formatting
    for acad in data.get("academics", []):
        acad["academic_course"] = smart_title(acad.get("academic_course", ""))
        acad["academic_institution"] = smart_title(acad.get("academic_institution", ""))

    # Languages formatting
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
        traceback.print_exc()
        raise e

def run_streamlit():
    import streamlit as st
    st.set_page_config(page_title="Gerador de Relatórios", layout="centered")
    st.title("Gerador de Relatórios de Candidatos")

    uploaded_file = st.file_uploader("📎 Faça upload do currículo (PDF)", type=["pdf"])
    language = st.selectbox("🌐 Idioma do relatório", options=["PT", "EN"])
    company = st.text_input("🏢 Nome da empresa")
    company_title = st.text_input("💼 Título da vaga")

    if st.button("▶️ Gerar Relatório") and uploaded_file and company and company_title:
        with st.spinner("Processando o currículo e gerando relatório..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_file.read())
                tmp_pdf_path = tmp_pdf.name

            # Pass company_title for translation and injection before report generation
            json_data = parse_cv_to_json(tmp_pdf_path, language, company_title=company_title)
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
