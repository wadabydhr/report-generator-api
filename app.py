from flask import Flask, request, send_file, jsonify
from docxtpl import DocxTemplate
import io
import os

app = Flask(__name__)

@app.route("/generate-report", methods=["POST"])
def generate_report():
    try:
        data = request.get_json(force=True)
        template_path = os.path.join("template", "Template_Placeholders.docx")
        doc = DocxTemplate(template_path)
        doc.render(data)

        with io.BytesIO() as output_stream:
            doc.save(output_stream)
            output_stream.seek(0)
            return send_file(
                output_stream,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name="relatorio.docx"
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/", methods=["GET"])
def healthcheck():
    return "Service is running", 200
