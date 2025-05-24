from flask import request, jsonify
import os
import tempfile
import fitz  # PyMuPDF
from openai import Client
import traceback
import json

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

def parse_cv_to_json():
    client = Client(api_key=os.getenv("OPENAI_API_KEY"))

    cv_file = request.files.get("cv_file")
    report_lang = request.form.get("report_lang", "PT").upper()
    benefits_block = request.form.get("benefits_block", "")

    if not cv_file:
        return jsonify({"error": "Missing CV file"}), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(cv_file.read())
            pdf_path = tmp.name

        extracted_text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                extracted_text += page.get_text()

        benefits_block = benefits_block.replace("{", "{{").replace("}", "}}")
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
            f"Compensation/benefits block:\n{benefits_block}\n\n"
            "CV Content:\n"
            f"{extracted_text}"
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )

        if not response.choices or not hasattr(response.choices[0], "message"):
            return jsonify({"error": "Unexpected response structure from OpenAI"}), 500

        json_output = response.choices[0].message.content

        try:
            parsed_data = json.loads(json_output)
            validated_data = enforce_schema(parsed_data, REQUIRED_SCHEMA)

            import requests
            from flask import send_file
            import io

            # Envia o JSON diretamente para o gerador de relatório
            report_response = requests.post(
                #"http://localhost:5000/generate-report",  # ajuste para o host real, se necessário
                "https://report-generator-7qud.onrender.com/generate-report",
                json=validated_data
            )

            if report_response.status_code != 200:
                return jsonify({"error": "Erro ao gerar relatório"}), 500

            # Retorna o arquivo .docx diretamente ao Bubble
            return send_file(
                io.BytesIO(report_response.content),
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name="relatorio.docx"
            )


            #return jsonify(validated_data)
            #return jsonify({
                #**validated_data,
                #"json_result": json.dumps(validated_data, ensure_ascii=False, separators=(',', ':'))
                #"json_result": validated_data
            #})
        except json.JSONDecodeError:
            print("⚠️ Falha ao converter resposta do OpenAI para JSON. Conteúdo bruto será retornado.")
            #return jsonify({
            #    "json_result": json_output,
            #    "error": "Could not parse response as JSON. Original content returned in 'json_result'."
            #}), 200
            return jsonify(json_output)

    except Exception as e:
        print("❌ Internal server error:", e)
        print(traceback.format_exc())
        return jsonify({"error": "Internal error occurred during parsing"}), 500
