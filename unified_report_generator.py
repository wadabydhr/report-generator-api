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

# --- Extraction Prompt ---
EXTRACTION_PROMPT = """
You are an expert system for extracting structured JSON from resumes (CVs) for HR automation.
Strictly follow the rules below for every field.
Never invent, summarize, or infer data not present. Just do spelling and grammar correction when necessary according to the report language.
Output only valid JSON matching the provided schema.

# GLOBAL RULES
- For more than one column text document, every column must be read from left to right and top to down, before move to the next text column. The continuity of text logic follows this rule for two or more columns.
- Every key in the schema must appear in the output, even if its value is empty.
- If a value is missing or unparseable, fill with an empty string (""), empty list ([]), or the correct empty type.
- Never invent, summarize, or infer data not found in the input.
- Never translate key names, only values.
- All string values must be stripped of leading/trailing whitespace.
- All string values must be normalized per field rules below.
- Dates must be normalized as per date rules below.
- Output must be valid, parseable JSON matching the schema.

# CRUCIAL EXTRACTION RULES FOR COMPANIES AND JOBS
- Do not skip, merge, or omit any company or employer from the CV. All the companies and jobs worked must be extracted.
- For each distinct company, create one line_items[] entry, grouping all jobs at that company.
- If the candidate worked at N companies, your output must have N line_items[] entries.
- If you miss any, your output is invalid.
- Never summarize, merge, or omit any company, employer, or position. If the CV lists 5 companies, your output MUST contain 5 items in line_items.
- Do not omit, merge, or skip any company.
- Usually companies, job_title, start_date, end_date, job_tasks are bellow of block of text under titles like: experience, experiences, professional experience, professional experiences, experiência, experiências, experiência profissional, experiências profissionais, etc.

# FIELD-SPECIFIC RULES


## company
- The official name of the company hiring for a job position.
- Output in UPPERCASE.
- If not present, output "Beyond HR".

## company_title
- The job title or position being applied for.
- Output in UPPERCASE.
- Remove any company name, location, or extraneous info.

## cdd_name
- Candidate’s full name.
- Use Title Case (capitalize each word).
- Remove extra spaces.

## cdd_email
- Must be a valid email address.
- If multiple found, use the first.
- If not found, output "".

## cdd_cel
- Extract only digits, plus (+), and spaces allowed.
- Must start with country code if present.
- If not found, output "".

## cdd_city, cdd_state
- Use Title Case.
- Only the city or state name, no country.

## cdd_age
- Integer only. If not found, output "".

## cdd_nationality
- Use the demonym (e.g., "Brazilian", "Brasileiro"), not the country name. Don't put the country name but the nationality.
- Must be in the report language.
- If not found, output "".

## abt_background, bhv_profile
- Use the most complete, descriptive paragraph found for each.
- Output in the report language.

## job_bond, job_wage, job_variable, job_meal, job_food, job_health, job_dental, job_life, job_pension, job_others, job_expectation
- Extract as described in the schema.
- Output in the report language.
- If not found, output "".

## last_company
- The "company" field of the most recent job.
- Must match the value in line_items[].cdd_company.

## report_lang
- Must be "PT" or "EN" per user selection.

## report_date
- Format as "DD de <month> de YYYY" if PT, or "<Month> <DayOrdinal>, YYYY" if EN (e.g., "29 de maio de 2025" or "May 29th, 2025").

## line_items (array)
- Each item is a unique company the candidate worked for.
- The order of line_items must be by the most recent company_end_date to the older one.
- See sub-fields below.

### line_items[].cdd_company
- Official company name, in UPPERCASE.

### line_items[].company_desc
- Short description of the company (max 89 characters).

### line_items[].company_start_date
- Earliest start date among all jobs at this company, in "MM/YYYY".
- If missing, output "00/0000".

### line_items[].company_end_date
- Latest end date among all jobs at this company, in "MM/YYYY".
- If any job at this company is ongoing (see end_date rules), output "PRESENT".

### line_items[].job_count
- Integer, number of jobs at this company.

### line_items[].job_posts (array)
- Each job/position held by the candidate at this company.
- See sub-fields below.

#### line_items[].job_posts[].job_title
- Title Case (capitalize each word), remove company or location.
- Must be translated to Portuguese or English language according to the report language defined by report_lang value (PT or EN).

#### line_items[].job_posts[].start_date
- Must be in "MM/YYYY".
- If only one digit for month, pad with zero (e.g., "6/2024" → "06/2024").
- If month name (e.g., "April 2024" or "abril 2024"), convert to "MM/YYYY".
- If only year, use "01/YYYY".
- If missing/unparseable, use "00/0000".

#### line_items[].job_posts[].end_date
- Same date rules as start_date.
- If value means present (see below), output "PRESENT".
- English present terms: present, current, currently, actual, nowadays, this moment, today.
- Portuguese present terms: presente, atual, atualmente, no presente, neste momento, data atual, presente momento, agora.

#### line_items[].job_posts[].job_tasks (array)
- Each item is a task performed in the job.
- Each task must be a distinct activity, not merged or summarized.
- Start with uppercase letter.
- Use the report language.

##### line_items[].job_posts[].job_tasks[].task
- The task description, as above.

## academics (array)
- Academic background entries.

### academics[].academic_course
- Title Case.

### academics[].academic_institution
- Title Case.

### academics[].academic_conclusion
- "YYYY" or "0000".

### languages[].level_description
- Use the standard description for the language level and report language.
- If not found, output "".

# OUTPUT FORMAT
Output only valid JSON matching this schema:

"""

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
    "cdd_ddi": "",
    "cdd_ddd": "",
    "cdd_cel": "",
    "cdd_age": "",
    "cdd_nationality": "",
    "cdd_personal": "",
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

def smart_title(text):
    if not isinstance(text, str):
        return text
    lowercase_exceptions = {"de", "da", "do", "das", "dos", "para", "com", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas", "of", "and", "in", "on", "to", "from", "with", "by", "for", "at"}
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
        return f"{month_en[month_index]} {ordinal(day)}, {year}"

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

SHEET_URL = "https://docs.google.com/spreadsheets/d/1q8hKLWcizUK2moUxQpiLHCyB5FHYVpPPNiyvq0NB_mM/export?format=csv"
df_levels = pd.read_csv(SHEET_URL)
df_levels["language_level"] = df_levels["language_level"].astype(str)

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


def canonicalize_language_level(raw_level, report_lang):
    if not isinstance(raw_level, str):
        return ""
    raw_level = raw_level.strip().lower()
    lang_key = "pt" if report_lang.upper() == "PT" else "en"
    for lvl in CANONICAL_LANGUAGE_LEVELS:
        if raw_level == lvl[lang_key].lower():
            return lvl[lang_key]
        for pattern in lvl["matches"]:
            if pattern in raw_level:
                return lvl[lang_key]
    return ""

def find_level_entry(level_value, report_lang):
    if not level_value:
        return None
    key = str(level_value).strip().lower()
    if report_lang.upper() == "PT":
        if key in PT_LEVELS:
            return PT_LEVELS[key]
        for k in PT_LEVELS:
            if key in k or k in key:
                return PT_LEVELS[k]
    else:
        if key in EN_LEVELS:
            return EN_LEVELS[key]
        for k in EN_LEVELS:
            if key in k or k in key:
                return EN_LEVELS[k]
    return None

PRESENT_TERMS_EN = ["present", "current", "currently", "actual", "nowadays", "this moment", "today"]
PRESENT_TERMS_PT = ["presente", "atual", "atualmente", "no presente", "neste momento", "data atual", "presente momento", "agora"]

def is_present_term(end_str, report_lang):
    if not isinstance(end_str, str):
        return False
    term = end_str.strip().lower()
    if report_lang.upper() == "PT":
        return any(term == t or t in term for t in PRESENT_TERMS_PT)
    else:
        return any(term == t or t in term for t in PRESENT_TERMS_EN)

MONTHS_EN = {
    "january": "01", "february": "02", "march": "03", "april": "04", "may": "05", "june": "06",
    "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
}
MONTHS_PT = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03", "abril": "04", "maio": "05", "junho": "06",
    "julho": "07", "agosto": "08", "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12",
    "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
    "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12"
}

def normalize_to_mm_yyyy(date_str, report_lang):
    if not isinstance(date_str, str):
        return date_str
    s = date_str.strip().lower()
    if valid_mm_yyyy(s):
        return s
    match = re.match(r"([a-zçãéíôúàõ]+)\s+(\d{4})", s)
    if match:
        month_name, year = match.groups()
        if report_lang.upper() == "PT":
            month_num = MONTHS_PT.get(month_name)
        else:
            month_num = MONTHS_EN.get(month_name)
        if month_num:
            return f"{month_num}/{year}"
    match = re.match(r"(\d{4})", s)
    if match:
        return f"01/{match.group(1)}"
    return date_str

def valid_mm_yyyy(date_str):
    if isinstance(date_str, str) and len(date_str) == 7 and date_str[2] == "/":
        mm, yyyy = date_str[:2], date_str[3:]
        return mm.isdigit() and yyyy.isdigit() and 1 <= int(mm) <= 12
    return False

def parse_mm_yyyy(date_str):
    try:
        return datetime.strptime(date_str, "%m/%Y")
    except Exception:
        return None

def translate_text(text, target_lang="EN"):
    if not isinstance(text, str) or not text.strip():
        return text
    # ENFORCE only English or Portuguese translation, never Spanish or any other language
    if target_lang.upper() not in ("EN", "PT"):
        return text
    try:
        client = Client(api_key=os.getenv("OPENAI_API_KEY"))
        if target_lang.upper() == "EN":
            system_prompt = "You are a translation assistant. Translate ONLY to English. Never use Spanish or any language but English."
            prompt = f"Translate the following text to English. Never use Spanish or any language but English:\n\n{text.strip()}"
        else:
            system_prompt = "Você é um assistente de tradução. Traduza SOMENTE para o português. Nunca use espanhol nem outro idioma além de português."
            prompt = f"Traduza o texto abaixo para o português. Nunca use espanhol nem outro idioma além de português:\n\n{text.strip()}"
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        result = response.choices[0].message.content.strip()
        # ENFORCE Spanish is never accepted: if the result contains any Spanish language marker, keep original
        if not result or result.lower().startswith("i'm sorry") or result.lower().startswith("sorry") or result.lower().startswith("as an") or result.lower().startswith("as a") or "could stand for man" in result.lower():
            return text
        if result.strip() == text.strip():
            return text
        # Strong filter for Spanish: if result has common Spanish words, keep original
        spanish_keywords = ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas ", "de ", "que ", "y ", "en ", "por ", "con ", "para "]
        if any(kw in result.lower() for kw in spanish_keywords) and target_lang.upper() in ("EN", "PT"):
            return text
        return result
    except Exception:
        return text

def translate_json_values(data, target_lang="EN", skip_keys=None):
    default_skip = {
        "language_level", "level_description", "report_lang", "report_date", "company_title", "cdd_name", "last_company",
        "cdd_email", "cdd_cel", "cdd_ddd", "cdd_ddi", "cdd_age", "cdd_state", "cdd_city", "cdd_company","language",
        "company_start_date", "company_end_date", "start_date", "end_date", "academic_conclusion", "academic_institution"
    }
    if skip_keys is None:
        skip_keys = default_skip
    else:
        skip_keys = set(skip_keys) | default_skip
    if isinstance(data, dict):
        return {k: translate_json_values(v, target_lang, skip_keys) if k not in skip_keys else v for k, v in data.items()}
    elif isinstance(data, list):
        return [translate_json_values(item, target_lang, skip_keys) for item in data]
    elif isinstance(data, str):
        return translate_text(data, target_lang)
    else:
        return data

def run_streamlit():
    import streamlit as st
    st.set_page_config(page_title="Gerador de Relatórios", layout="centered")
    st.title("📄 Gerador de Relatórios de Candidatos")

    uploaded_file = st.file_uploader("📎 Faça upload do currículo (PDF)", type=["pdf"])
    language = st.selectbox("🌐 Idioma do relatório", options=["PT", "EN"])
    company = st.text_input("🏢 Nome da empresa")
    company_title = st.text_input("💼 Título da vaga")

    # --- Language skill fields (form) ---
    st.markdown("#### Idiomas e Nível do Candidato")
    dropdown_levels = list(df_levels["language_level"])
    LANGUAGE_DISPLAY = [
        {"label_pt": "Inglês", "label_en": "English", "key": "english"},
        {"label_pt": "Espanhol", "label_en": "Spanish", "key": "spanish"},
        {"label_pt": "Japonês", "label_en": "Japanese", "key": "japanese"},
    ]
    language_skills = {}
    for lang in LANGUAGE_DISPLAY:
        col1, col2 = st.columns([1,2])
        with col1:
            label = lang["label_pt"] if language == "PT" else lang["label_en"]
            st.write(f"{label}:")
        with col2:
            dropdown_label = f"Selecione o nível para {label}" if language == "PT" else f"Select level for {label}"
            level = st.selectbox(
                dropdown_label,
                options=[""] + dropdown_levels,
                key=f"{lang['key']}_level"
            )
            language_skills[lang["key"]] = level

    if st.button("▶️ Gerar Relatório") and uploaded_file and company and company_title:
        with st.spinner("Processando o currículo e gerando relatório..."):
            file_bytes = uploaded_file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(file_bytes)
                tmp_pdf.flush()
                tmp_pdf_path = tmp_pdf.name

            json_data = parse_cv_to_json(tmp_pdf_path, language, company_title=company_title, language_skills=language_skills)
            try:
                os.remove(tmp_pdf_path)
            except Exception:
                pass

            st.subheader("🔎 Dados extraídos do currículo:")
            st.json(json_data)
            if "error" in json_data:
                st.error("❌ Erro retornado pelo parser:")
                st.stop()

            json_data["company"] = company

            template_path = os.path.join(TEMPLATE_FOLDER, f"Template_Placeholders_{language}.docx")
            safe_name = json_data.get('cdd_name', 'candidato').lower().replace(" ", "_")
            output_filename = f"Relatorio_{safe_name}_{datetime.today().strftime('%Y%m%d')}.docx"
            output_path = os.path.join(tempfile.gettempdir(), output_filename)

            st.info(f"📄 Caminho do template utilizado: `{template_path}`")
            if not os.path.isfile(template_path):
                st.error(f"❌ Template file does not exist: {template_path}")
                st.stop()
            try:
                with open(template_path, "rb") as f:
                    header = f.read(4)
                st.info(f"📄 Primeiros bytes do template: {header}")
                if header != b'PK\x03\x04':
                    st.error("❌ Template file is not a valid DOCX (ZIP format).")
                    st.stop()
                st.info(f"📄 Tamanho do arquivo template: {os.path.getsize(template_path)} bytes")
                try:
                    doc = DocxTemplate(template_path)
                    undeclared = doc.get_undeclared_template_variables()
                    if undeclared:
                        st.warning(f"⚠️ Template placeholders not provided in context: {undeclared}")
                except Exception as e:
                    st.warning(f"⚠️ Não foi possível checar placeholders do template: {e}")
            except Exception as e:
                st.error(f"❌ Could not read template file: {e}")
                st.stop()

            try:
                generate_report_from_data(json_data, template_path, output_path)
                if not os.path.exists(output_path):
                    st.error("❌ O arquivo DOCX gerado não foi encontrado.")
                    st.stop()
                file_size = os.path.getsize(output_path)
                st.info(f"📄 Tamanho do arquivo DOCX gerado: {file_size} bytes")
                st.info(f"📄 Caminho do arquivo gerado: `{output_path}`")
            except Exception as e:
                st.error("❌ Erro ao gerar o relatório:")
                st.code(traceback.format_exc())
                st.stop()

            try:
                with open(output_path, "rb") as f:
                    file_bytes = f.read()
                st.info(f"📄 Primeiros bytes do DOCX gerado: {file_bytes[:4]}")
                if not file_bytes.startswith(b'PK\x03\x04'):
                    st.error("❌ O arquivo gerado não é um DOCX válido (espera-se PK header).")
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

def parse_cv_to_json(file_path, report_lang, company_title=None, language_skills=None):
    client = Client(api_key=os.getenv("OPENAI_API_KEY"))
    if not file_path:
        return {"error": "Missing CV file"}

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp.flush()
            tmp_pdf_path = tmp.name

        extracted_text = ""
        with fitz.open(tmp_pdf_path) as doc:
            for page in doc:
                extracted_text += page.get_text()

        try:
            os.remove(tmp_pdf_path)
        except Exception:
            pass

        extracted_text = extracted_text.replace("{", "{{").replace("}", "}}")
        schema_example = json.dumps(REQUIRED_SCHEMA, ensure_ascii=False, indent=2)
        extraction_prompt = (
            EXTRACTION_PROMPT
            + schema_example
            + "\n\nReport language: " + report_lang
            + "\nCV Content:\n"
            + extracted_text
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

        if company_title is not None:
            validated_data["company_title"] = company_title

        # --- Languages: Only fill from form input (with robust fallback) ---
        validated_data["languages"] = []
        LANGUAGES_FORM = [
            {"pt": "Inglês",   "en": "English",  "key": "english"},
            {"pt": "Espanhol", "en": "Spanish",  "key": "spanish"},
            {"pt": "Japonês",  "en": "Japanese", "key": "japanese"},
        ]
        report_lang_setting = (validated_data.get("report_lang") or report_lang or "PT").upper()
        if language_skills:
            for lang in LANGUAGES_FORM:
                lang_key = lang["key"]
                level = language_skills.get(lang_key, "")
                if level:
                    language_name = lang["pt"] if report_lang_setting == "PT" else lang["en"]
                    row = df_levels[df_levels["language_level"] == level]
                    level_description = (
                        row.iloc[0]["level_description_pt"] if (not row.empty and report_lang_setting == "PT")
                        else row.iloc[0]["level_description_en"] if (not row.empty and report_lang_setting == "EN")
                        else ""
                    )
                    validated_data["languages"].append({
                        "language": language_name,
                        "language_level": level,
                        "level_description": level_description
                    })

        # ENFORCE translation ONLY to PT or EN, never Spanish or other
        if validated_data.get("report_lang", "PT") == "EN":
            validated_data = translate_json_values(validated_data, target_lang="EN")
        elif validated_data.get("report_lang", "PT") == "PT":
            validated_data = translate_json_values(validated_data, target_lang="PT")

        return validated_data

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

def build_context(data):
    line_items = []
    latest_date = None
    last_company = ""
    report_lang = data.get("report_lang", "PT")

    for item in data.get("line_items", []):
        item["cdd_company"] = format_caps(item.get("cdd_company", ""))
        raw_desc = item.get("company_desc", "")
        item["company_desc"] = trim_text(format_first(raw_desc), 89)
        job_posts = []
        start_dates = []
        end_dates = []
        any_present = False

        for job in item.get("job_posts", []):
            job["job_title"] = smart_title(job.get("job_title", ""))

            raw_start = job.get("start_date", "")
            norm_start = normalize_to_mm_yyyy
