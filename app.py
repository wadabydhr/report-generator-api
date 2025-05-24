print("VERSÃO CORRETA DO APP.PY CARREGADA")
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from docxtpl import DocxTemplate

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
TEMPLATE_FOLDER = 'template'
STATIC_FOLDER = 'static'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMPLATE_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

@app.route("/generate-report", methods=["POST"])

def generate_report_from_data(data, template_path, output_path):
    from docxtpl import DocxTemplate
    import os

    context = {
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

    doc = DocxTemplate(template_path)
    doc.render(context)
    doc.save(output_path)



def generate_report():
    try:
        data = request.get_json()

        # Constrói o contexto com formatação
        context = {
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
            "languages": data.get("languages", []),
        }

        # Formata datas dos empregos
        line_items = []
        for item in data.get("line_items", []):
            job_posts = []
            for job in item.get("job_posts", []):
                start_date = job.get("start_date", "")
                end_date = job.get("end_date", "")
                job_posts.append({
                    "job_title": job.get("job_title", ""),
                    "start_date": start_date,
                    "end_date": end_date,
                    "job_tasks": job.get("job_tasks", [])
                })
            line_items.append({
                "cdd_company": item.get("cdd_company", ""),
                "company_desc": item.get("company_desc", ""),
                "job_posts": job_posts
            })
        context["line_items"] = line_items

        # Seleciona template com base no idioma
        lang = context["report_lang"].upper()
        template_filename = (
            "Template_Placeholders_EN.docx" if lang == "EN" else "Template_Placeholders_PT.docx"
        )
        template_path = os.path.join(TEMPLATE_FOLDER, template_filename)
        doc = DocxTemplate(template_path)
        doc.render(context)

        # Geração de nome e salvamento do arquivo
        safe_name = context["cdd_name"].lower().replace(" ", "_")
        file_name = f"{safe_name}_report.docx"
        file_path = os.path.join(STATIC_FOLDER, file_name)
        doc.save(file_path)

        # Retorno da URL do relatório
        download_url = f"https://report-generator-7qud.onrender.com/static/{file_name}"
        return jsonify({"download_url": download_url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/static/<path:filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(STATIC_FOLDER, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=10000)
