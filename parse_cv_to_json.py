import json
import os
import tempfile
import fitz  # PyMuPDF
from openai import Client
import traceback

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
            #f"Compensation/benefits block:\n{benefits_block}\n\n"
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
        print(response)
        # Verificação explícita
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

            import requests
            from flask import send_file
            import io

            # Envia o JSON diretamente para o gerador de relatório
            report_response = requests.post(
                #"http://localhost:5000/generate-report",  # ajuste para o host real, se necessário
                "https://report-generator-7qud.onrender.com/generate-report",
                json=validated_data,
                headers=headers
            )

            if report_response.status_code != 200:
                print("❌ Erro ao chamar o endpoint /generate-report")
                print("🔢 Status HTTP:", report_response.status_code)
                print("📩 Resposta do servidor:", report_response.text)
                print("📦 JSON enviado para o app.py:")
                print(json.dumps(validated_data, indent=2, ensure_ascii=False))

                import traceback
                traceback.print_exc()
                return {"error": f"Erro ao gerar relatório: HTTP {report_response.status_code}"}

            # Retorna o arquivo .docx diretamente ao Bubble
            return send_file(
                io.BytesIO(report_response.content),
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name="relatorio.docx"
            )


            #return validated_data
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
            return json_output

    except Exception as e:
        #print("❌ Internal server error:", e)
        #print(traceback.format_exc())
        #return {"error": "Internal error occurred during parsing"}
        import traceback
        print("Erro durante o parsing do currículo:")
        traceback.print_exc()
        return {"error": str(e)}
