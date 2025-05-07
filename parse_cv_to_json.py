from flask import request, jsonify
import os
import tempfile
import fitz  # PyMuPDF
import openai

def parse_cv_to_json():
    cv_file = request.files.get("cv_file")
    report_lang = request.form.get("report_lang", "PT").upper()
    benefits_block = request.form.get("benefits_block", "")

    if not cv_file:
        return jsonify({"error": "Missing CV file"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(cv_file.read())
        pdf_path = tmp.name

    extracted_text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            extracted_text += page.get_text()

    openai.api_key = os.getenv("OPENAI_API_KEY")

    system_prompt = (
        "You are a system that converts resumes into structured JSON. "
        "You must follow exactly the structure of a reference JSON used for report automation. "
        "All keys must be present and correctly named. Translate and adapt content to match the report language (PT or EN)."
    )

    user_prompt_template = """You will receive:
1. The full text extracted from a CV in PDF format
2. A report language code ("PT" for Portuguese, "EN" for English)
3. A block of compensation/benefits information to extract into specific keys

Return only a single valid JSON object following the schema used in the file '@SAMPLE_REPORT_APRIL_25.json'. Your response must exactly match this structure and naming, including:

Top-level:
- cdd_name, cdd_email, cdd_city, cdd_state, cdd_cel, cdd_age, cdd_nationality
- abt_background, bhv_profile
- job_bond, job_wage, job_variable, job_meal, job_food, job_health, job_dental, job_life, job_pension, job_others, job_expectation
- last_company, report_lang, report_date

And nested arrays:
- line_items: [{{ cdd_company, company_desc, job_posts: [{{ job_title, start_date, end_date, job_tasks: [{{task}}] }}] }}]
- academics: [{{ academic_course, academic_institution, academic_conclusion }}]
- languages: [{{ language, language_level }}]

Instructions:
- Translate all content to match the report_lang: "{report_lang}".
- Use formal business writing and correct formatting.
- Extract compensation values from the following block and assign to correct job_* keys:

"""{benefits_block}"""

Parse the CV content below to extract work experiences, education, language fluency, and narrative sections:

"""{extracted_text}"""

Return a single, well-formatted JSON object only. Do not include explanations.
"""

    user_prompt = user_prompt_template.format(
        report_lang=report_lang,
        benefits_block=benefits_block,
        extracted_text=extracted_text
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        json_output = response["choices"][0]["message"]["content"]
        return json_output, 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500
