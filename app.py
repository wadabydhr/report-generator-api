
from flask import Flask, request, send_file
from parse_cv_to_json import parse_cv_to_json
from docxtpl import DocxTemplate
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)

# Register your external route
app.add_url_rule('/parse-cv-to-json', view_func=parse_cv_to_json, methods=["POST"])

# Utility functions
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


import json

@app.route("/generate-report", methods=["POST"])
def generate_report():
    raw = request.get_data(as_text=True)

    print("⚠️ RAW BODY RECEIVED:")
    print(raw)

    try:
        json_data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "error": "❌ Failed to decode top-level string JSON."
        }, 400

    # Caso venha como {"data": "{...json...}"}
    if isinstance(json_data, dict) and "data" in json_data and isinstance(json_data["data"], str):
        try:
            data = json.loads(json_data["data"])
            print("✅ Decoded nested JSON inside 'data'")
        except json.JSONDecodeError:
            return {
                "error": "❌ Failed to decode nested JSON inside 'data'"
            }, 400
    else:
        data = json_data[0] if isinstance(json_data, list) else json_data

    print("✅ Final parsed 'data' type:", type(data))


    # Load language levels from Google Sheet
    sheet_url = "https://docs.google.com/spreadsheets/d/1q8hKLWcizUK2moUxQpiLHCyB5FHYVpPPNiyvq0NB_mM/export?format=csv"
    df_levels = pd.read_csv(sheet_url)
    level_map = df_levels.set_index("language_level").to_dict(orient="index")

    # Process line_items
    for item in data.get("line_items", []):
        start_dates = []
        end_dates = []

        item["cdd_company"] = format_caps(item.get("cdd_company", ""))
        raw_desc = item.get("company_desc", "")
        item["company_desc"] = trim_text(format_first(raw_desc), 89)

        for job in item.get("job_posts", []):
            job["job_title"] = smart_title(job.get("job_title", ""))
            start = safe_date(job.get("start_date", ""))
            end_str = job.get("end_date", "")
            end = safe_date(end_str) if end_str.lower() != "presente" else None

            if start:
                start_dates.append(start)
            if end:
                end_dates.append(end)

            for task in job.get("job_tasks", []):
                task["task"] = format_first(task.get("task", ""))

        item["company_start_date"] = min(start_dates).strftime("%m/%Y") if start_dates else "N/A"
        item["company_end_date"] = max(end_dates).strftime("%m/%Y") if end_dates else "presente"
        item["job_count"] = len(item.get("job_posts", []))

    # Process academics
    for acad in data.get("academics", []):
        acad["academic_course"] = smart_title(acad.get("academic_course", ""))
        acad["academic_institution"] = smart_title(acad.get("academic_institution", ""))

    # Process languages
    for lang in data.get("languages", []):
        lang["language"] = smart_title(lang.get("language", ""))
        level = lang.get("language_level")
        if level in level_map:
            lang["language_description"] = level_map[level]["language_description"]
            lang["level_description"] = level_map[level]["level_description"]
        else:
            lang["language_description"] = "Desconhecido"
            lang["level_description"] = ""

    # Determine last_company
    latest_date = None
    last_company = ""
    for item in data.get("line_items", []):
        end_date_str = item.get("company_end_date", "")
        end_date = parse_date_safe(end_date_str)
        if end_date and (latest_date is None or end_date > latest_date):
            latest_date = end_date
            last_company = item.get("cdd_company", "")

    # Prepare context
    context = {
        "company": format_caps(data.get("company", "")),
        "job_title": format_caps(data.get("job_title", "")),
        "cdd_name": format_caps(data.get("cdd_name", "")),
        "cdd_city": smart_title(data.get("cdd_city", "")),
        "cdd_state": format_caps(data.get("cdd_state", "")),
        "cdd_ddi": data.get("cdd_ddi", ""),
        "cdd_ddd": data.get("cdd_ddd", ""),
        "cdd_cel": data.get("cdd_cel", ""),
        "cdd_email": data.get("cdd_email", ""),
        "cdd_nationality": smart_title(data.get("cdd_nationality", "")),
        "cdd_age": data.get("cdd_age", ""),
        "cdd_personal": format_first(data.get("cdd_personal", "")),
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
        "line_items": data.get("line_items", []),
        "academics": data.get("academics", []),
        "languages": data.get("languages", []),
        "last_company": last_company,
        "report_date": format_report_date(data.get("report_lang", "PT"))
    }

    # Load the template and generate the report
    # Escolhe o template com base no idioma
    lang = data.get("report_lang", "PT").upper()
    template_file = f"Template_Placeholders_{lang}.docx"

    import os
    if not os.path.exists(template_file):
        return {
            "error": f"Template file '{template_file}' not found on server."
        }, 500

    doc = DocxTemplate(template_file)
    doc.render(context)

    output_stream = io.BytesIO()
    doc.save(output_stream)
    output_stream.seek(0)

    return send_file(
        output_stream,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name="output_report.docx"
    )


if __name__ == "__main__":
    app.run()
