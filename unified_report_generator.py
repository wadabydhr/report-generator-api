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
Never invent, summarize, or infer data not present.
Output only valid JSON matching the provided schema.

# GLOBAL RULES
- Every key in the schema must appear in the output, even if its value is empty.
- If a value is missing or unparseable, fill with an empty string (""), empty list ([]), or the correct empty type.
- Never invent, summarize, or infer data not found in the input.
- Never translate key names, only values.
- All string values must be stripped of leading/trailing whitespace.
- All string values must be normalized per field rules below.
- Dates must be normalized as per date rules below.
- Output must be valid, parseable JSON matching the schema.

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
- Format as "DD de <month> de YYYY" if PT, or "<DayOrdinal> <Month>, YYYY" if EN (e.g., "29 de maio de 2025" or "29th May, 2025").

## line_items (array)
- Each item is a unique company the candidate worked for.
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
- "MM/YYYY" or "00/0000".

## languages (array)
- All languages the candidate lists.

### languages[].language
- Title Case. Must be a valid language.

### languages[].language_level
- Must match exactly one of:
  - If basic knowledge must be either "Elementary" for report_lang=EN or "Elementar" for report_lang=PT.
  - If basic with intermediary skill in conversation or writing must be either "Pre-operational" for report_lang=EN or "Pre-operacional" for report_lang=PT.
  - If intermediary knowledge must be either "Operational" for report_lang=EN or "Operacional" for report_lang=PT.
  - If intermediary with advanced skill only in conversation or writing must be either "Extended" for report_lang=EN or "Intermediário" for report_lang=PT.
  - If advanced knowledge or native or fluent must be either "Expert" for report_lang=EN or "Avançado / Fluente" for report_lang=PT.

### languages[].level_description
- Use the standard description for the language level and report language.
- If not found, output "".

# OUTPUT FORMAT
Output only valid JSON matching this schema:
"""

# ... [unchanged code above] ...

# --- Translation Utilities ---
def translate_text(text, target_lang="EN"):
    if not isinstance(text, str) or not text.strip():
        return text
    try:
        client = Client(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"Translate the following text to English:\n\n{text.strip()}"
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a translation assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        result = response.choices[0].message.content.strip()
        # If OpenAI returns empty, a warning, a clarification, or repeats input, fallback to original
        if not result or result.lower().startswith("i'm sorry") or result.lower().startswith("sorry") or result.lower().startswith("as an") or result.lower().startswith("as a") or "could stand for many things" in result.lower() or "provide more context" in result.lower():
            return text
        if result.strip() == text.strip():
            return text
        return result
    except Exception:
        return text

def translate_json_values(data, target_lang="EN", skip_keys=None):
    # Add all keys you want to skip translation for, including the requested ones
    default_skip = {
        "language_level", "level_description", "report_lang", "report_date",
        "cdd_email", "cdd_cel", "cdd_ddd", "cdd_ddi", "cdd_age", "cdd_state", "cdd_city",
        "company_start_date", "company_end_date", "start_date", "end_date", "academic_conclusion"
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

# ... [rest of original code, unchanged] ...