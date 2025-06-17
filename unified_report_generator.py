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
- Every key in the schema must appear in the output, even if its value is empty.
- If a value is missing or unparseable, fill with an empty string (""), empty list ([]), or the correct empty type.
- Never invent, summarize, or infer data not found in the input.
- Never translate key names, only values.
- All string values must be stripped of leading/trailing whitespace.
- All string values must be normalized per field rules below.
- Dates must be normalized as per date rules below.
- Output must be valid, parseable JSON matching the schema.

# CRUCIAL EXTRACTION RULES FOR COMPANIES AND JOBS
- Do not skip, merge, or omit any company or employer from the CV.
- For each distinct company, create one line_items[] entry, grouping all jobs at that company.
- If the candidate worked at N companies, your output must have N line_items[] entries.
- If you miss any, your output is invalid.
- Never summarize, merge, or omit any company, employer, or position. If the CV lists 5 companies, your output MUST contain 5 items in line_items.
- Do not omit, merge, or skip any company.

# LANGUAGE RULES
- The output content MUST be ONLY in the language specified by the field "report_lang": use "PT" for Portuguese or "EN" for English.
- Do NOT use Spanish or any other language under any circumstances.
- If translating, always translate to the language specified by "report_lang" and never to any other language.
- If the content is already in the correct language, only perform spelling and grammar correction as needed according to "report_lang".

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

## languages (array)
- All languages the candidate lists except Portuguese language.

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

# [rest of the file remains unchanged, as previously provided]
# (Copy/paste your current code here, starting from UPLOAD_FOLDER = ...)

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

# [Continue with your unchanged logic, as in your current file...]

# (Paste the rest of your current file here, unmodified.)

# The rest of the file is unchanged and should include all your current report generation and processing logic.