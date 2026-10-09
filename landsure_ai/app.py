from flask import Flask, render_template, request, redirect, session, send_file
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import sqlite3
import os
import re
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "landsure-ai-demo-secret-key"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

UPLOAD_FOLDER = "uploads"
DB_NAME = "landsure.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS property_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_name TEXT,
            khasra_number TEXT,
            survey_number TEXT,
            village TEXT,
            district TEXT,
            state TEXT,
            land_area TEXT,
            property_type TEXT,
            registration_status TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_pdf_text(file_path):

    text = ""

    try:

        reader = PdfReader(file_path)

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:
                text += "\n" + page_text

    except Exception as e:

        print("PDF extraction error:", e)
        return ""

    return text.strip()


# =========================================================
# CLEAN VALUE
# =========================================================

def clean_value(value):

    if not value:
        return ""

    value = value.strip()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value


# =========================================================
# FIELD EXTRACTION
# =========================================================

def extract_field(text, labels):

    if not text:
        return ""

    lines = [
        clean_value(line)
        for line in text.splitlines()
        if clean_value(line)
    ]

    # -----------------------------------------------------
    # METHOD 1:
    # "Owner Name: Aarav Sharma"
    # -----------------------------------------------------

    for label in labels:

        pattern = (
            rf"^\s*{re.escape(label)}"
            rf"\s*(?:\:|\-|\–|\—)\s*(.+?)\s*$"
        )

        match = re.search(
            pattern,
            text,
            re.IGNORECASE |
            re.MULTILINE
        )

        if match:

            return clean_value(
                match.group(1)
            )


    # -----------------------------------------------------
    # METHOD 2:
    # "Owner Name"
    # next line = "Aarav Sharma"
    # -----------------------------------------------------

    lower_lines = [
        line.lower()
        for line in lines
    ]

    for label in labels:

        label_lower = label.lower()

        for index, line in enumerate(lower_lines):

            if line == label_lower:

                if index + 1 < len(lines):

                    next_value = lines[index + 1]

                    # Avoid taking another field name
                    field_names = [
                        x.lower()
                        for x in [
                            "Owner Name",
                            "Khasra Number",
                            "Survey Number",
                            "Village",
                            "District",
                            "State",
                            "Land Area",
                            "Property Type",
                            "Registration Status"
                        ]
                    ]

                    if next_value.lower() not in field_names:

                        return clean_value(
                            next_value
                        )


    # -----------------------------------------------------
    # METHOD 3:
    # Label followed by value on same line without colon
    # Example: Owner Name Aarav Sharma
    # -----------------------------------------------------

    for label in labels:

        pattern = (
            rf"^\s*{re.escape(label)}"
            rf"\s+(.+?)\s*$"
        )

        match = re.search(
            pattern,
            text,
            re.IGNORECASE |
            re.MULTILINE
        )

        if match:

            value = clean_value(
                match.group(1)
            )

            if value and value.lower() != label.lower():

                return value


    return ""


# =========================================================
# EXTRACT LAND DETAILS
# =========================================================

def extract_land_details(text):

    details = {}

    details["Owner Name"] = extract_field(
        text,
        [
            "Owner Name",
            "Owner",
            "Name of Owner",
            "Property Owner"
        ]
    )

    details["Khasra Number"] = extract_field(
        text,
        [
            "Khasra Number",
            "Khasra No",
            "Khasra"
        ]
    )

    details["Survey Number"] = extract_field(
        text,
        [
            "Survey Number",
            "Survey No",
            "Survey"
        ]
    )

    details["Village"] = extract_field(
        text,
        [
            "Village Name",
            "Village"
        ]
    )

    details["District"] = extract_field(
        text,
        [
            "District Name",
            "District"
        ]
    )

    details["State"] = extract_field(
        text,
        [
            "State Name",
            "State"
        ]
    )

    details["Land Area"] = extract_field(
        text,
        [
            "Land Area",
            "Plot Area",
            "Area of Land",
            "Area"
        ]
    )

    details["Property Type"] = extract_field(
        text,
        [
            "Property Type",
            "Land Type",
            "Type of Property"
        ]
    )

    details["Registration Status"] = extract_field(
        text,
        [
            "Registration Status",
            "Registration",
            "Registered Status"
        ]
    )

    return details


# =========================================================
# LAND DOCUMENT CHECK
# =========================================================

def is_land_document(text):

    text_lower = text.lower()

    keywords = [
        "land",
        "khasra",
        "khatauni",
        "survey number",
        "survey no",
        "owner name",
        "property type",
        "property",
        "village",
        "district",
        "registration",
        "agricultural land",
        "acre",
        "hectare"
    ]

    found = 0

    for keyword in keywords:

        if keyword in text_lower:
            found += 1

    # Need at least 2 meaningful land terms
    return found >= 2


# =========================================================
# DUPLICATE CHECK
# =========================================================

def check_duplicate(details):

    khasra = details.get(
        "Khasra Number",
        ""
    ).strip().lower()

    survey = details.get(
        "Survey Number",
        ""
    ).strip().lower()

    owner = details.get(
        "Owner Name",
        ""
    ).strip().lower()

    village = details.get(
        "Village",
        ""
    ).strip().lower()

    district = details.get(
        "District",
        ""
    ).strip().lower()


    if not khasra and not survey:

        return "Not Checked", 0


    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM property_records"
    ).fetchall()

    conn.close()


    highest_score = 0


    for row in rows:

        score = 0

        if khasra and row["khasra_number"]:

            if khasra == row["khasra_number"].strip().lower():
                score += 3


        if survey and row["survey_number"]:

            if survey == row["survey_number"].strip().lower():
                score += 3


        if owner and row["owner_name"]:

            if owner == row["owner_name"].strip().lower():
                score += 2


        if village and row["village"]:

            if village == row["village"].strip().lower():
                score += 2


        if district and row["district"]:

            if district == row["district"].strip().lower():
                score += 1


        highest_score = max(
            highest_score,
            score
        )


    if highest_score >= 5:

        return "Possible Duplicate", highest_score


    return "No Matching Record", highest_score


# =========================================================
# SAVE RECORD
# =========================================================

def save_property_record(details):

    conn = get_db()

    conn.execute("""
        INSERT INTO property_records
        (
            owner_name,
            khasra_number,
            survey_number,
            village,
            district,
            state,
            land_area,
            property_type,
            registration_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        details.get("Owner Name", ""),
        details.get("Khasra Number", ""),
        details.get("Survey Number", ""),
        details.get("Village", ""),
        details.get("District", ""),
        details.get("State", ""),
        details.get("Land Area", ""),
        details.get("Property Type", ""),
        details.get("Registration Status", "")

    ))

    conn.commit()
    conn.close()


# =========================================================
# DOCUMENT UPLOAD
# =========================================================

@app.route(
    "/documents",
    methods=["GET", "POST"]
)
def documents():

    if request.method == "GET":

        return render_template(
            "documents.html"
        )


    document = request.files.get(
        "document"
    )

    land_map = request.files.get(
        "land_map"
    )

    land_photo = request.files.get(
        "land_photo"
    )

    document_type = request.form.get(
        "document_type",
        "Other"
    )


    # -----------------------------------------------------
    # DOCUMENT REQUIRED
    # -----------------------------------------------------

    if not document or not document.filename:

        return render_template(
            "documents.html",
            error="Please select a land document PDF."
        )


    # -----------------------------------------------------
    # PDF CHECK
    # -----------------------------------------------------

    if not document.filename.lower().endswith(
        ".pdf"
    ):

        return render_template(
            "documents.html",
            error="Land document must be a PDF file."
        )


    # -----------------------------------------------------
    # SAVE DOCUMENT
    # -----------------------------------------------------

    filename = secure_filename(
        document.filename
    )

    document_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    document.save(
        document_path
    )


    # -----------------------------------------------------
    # SAVE MAP
    # -----------------------------------------------------

    map_path = ""

    if land_map and land_map.filename:

        map_filename = secure_filename(
            land_map.filename
        )

        map_path = os.path.join(
            UPLOAD_FOLDER,
            map_filename
        )

        land_map.save(
            map_path
        )


    # -----------------------------------------------------
    # SAVE PHOTO
    # -----------------------------------------------------

    photo_path = ""

    if land_photo and land_photo.filename:

        photo_filename = secure_filename(
            land_photo.filename
        )

        photo_path = os.path.join(
            UPLOAD_FOLDER,
            photo_filename
        )

        land_photo.save(
            photo_path
        )


    # -----------------------------------------------------
    # SESSION
    # -----------------------------------------------------

    session["document_path"] = document_path

    session["land_map_path"] = map_path

    session["land_photo_path"] = photo_path

    session["document_type"] = document_type

    session.pop(
        "report_data",
        None
    )

    session.pop(
        "verification_done",
        None
    )


    # -----------------------------------------------------
    # AUTOMATIC VERIFICATION
    # -----------------------------------------------------

    return redirect(
        "/verification"
    )


# =========================================================
# VERIFICATION
# =========================================================

@app.route("/verification")
def verification():

    document_path = session.get(
        "document_path"
    )


    if not document_path:

        return redirect(
            "/documents"
        )


    # -----------------------------------------------------
    # IF ALREADY VERIFIED
    # -----------------------------------------------------

    if session.get(
        "verification_done"
    ):

        details = session.get(
            "report_data",
            {}
        )

        return render_template(
            "verification.html",
            result="Basic verification passed. Land-related details found.",
            details=details,
            auto_report=False
        )


    # -----------------------------------------------------
    # EXTRACT PDF
    # -----------------------------------------------------

    text = extract_pdf_text(
        document_path
    )


    # -----------------------------------------------------
    # PDF READ FAILURE
    # -----------------------------------------------------

    if not text:

        details = {
            "Duplicate Status": "Not Checked",
            "Duplicate Score": 0
        }

        return render_template(
            "verification.html",
            result="❌ Verification failed. The PDF could not be read.",
            details=details,
            auto_report=False
        )


    # -----------------------------------------------------
    # LAND DOCUMENT CHECK
    # -----------------------------------------------------

    if not is_land_document(text):

        details = {
            "Duplicate Status": "Not Checked",
            "Duplicate Score": 0
        }

        return render_template(
            "verification.html",
            result=(
                "❌ Verification failed. "
                "No sufficient land-related information "
                "was found in this document."
            ),
            details=details,
            auto_report=False
        )


    # -----------------------------------------------------
    # EXTRACT DETAILS
    # -----------------------------------------------------

    details = extract_land_details(
        text
    )


    # -----------------------------------------------------
    # MAP
    # -----------------------------------------------------

    map_path = session.get(
        "land_map_path",
        ""
    )

    if (
        map_path
        and os.path.exists(map_path)
    ):

        details["Land Map"] = (
            "Uploaded and Validated"
        )

    else:

        details["Land Map"] = (
            "Not Uploaded"
        )


    # -----------------------------------------------------
    # PHOTO
    # -----------------------------------------------------

    photo_path = session.get(
        "land_photo_path",
        ""
    )

    if (
        photo_path
        and os.path.exists(photo_path)
    ):

        details["Land Photo"] = (
            "Uploaded and Validated"
        )

    else:

        details["Land Photo"] = (
            "Not Uploaded"
        )


    # -----------------------------------------------------
    # DUPLICATE
    # -----------------------------------------------------

    duplicate_status, duplicate_score = check_duplicate(
        details
    )

    details["Duplicate Status"] = duplicate_status

    details["Duplicate Score"] = duplicate_score


    # -----------------------------------------------------
    # SAVE DATABASE
    # -----------------------------------------------------

    save_property_record(
        details
    )


    # -----------------------------------------------------
    # SAVE SESSION
    # -----------------------------------------------------

    session["report_data"] = details

    session["verification_done"] = True


    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    return render_template(
        "verification.html",
        result=(
            "✅ Basic verification passed. "
            "Land-related details found."
        ),
        details=details,
        auto_report=True
    )


# =========================================================
# REPORT
# =========================================================

@app.route("/reports")
def reports():

    report_data = session.get(
        "report_data"
    )


    if not report_data:

        return render_template(
            "reports.html",
            report_data=None
        )


    return render_template(
        "reports.html",
        report_data=report_data
    )


# =========================================================
# DOWNLOAD REPORT
# =========================================================

@app.route("/download_report")
def download_report():

    report_data = session.get(
        "report_data"
    )


    if not report_data:

        return (
            "No verification report available.",
            404
        )


    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    y = height - 50


    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        20
    )

    pdf.drawString(
        50,
        y,
        "LandSure AI"
    )

    y -= 30

    pdf.setFont(
        "Helvetica-Bold",
        15
    )

    pdf.drawString(
        50,
        y,
        "Land Verification Report"
    )

    y -= 35


    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        50,
        y,
        "Automated prototype verification report"
    )

    y -= 35


    # -----------------------------------------------------
    # PROPERTY INFORMATION
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        12
    )

    pdf.drawString(
        50,
        y,
        "Property Information"
    )

    y -= 22


    pdf.setFont(
        "Helvetica",
        10
    )


    fields = [
        "Owner Name",
        "Khasra Number",
        "Survey Number",
        "Village",
        "District",
        "State",
        "Land Area",
        "Property Type",
        "Registration Status",
        "Land Map",
        "Land Photo",
        "Duplicate Status",
        "Duplicate Score"
    ]


    for field in fields:

        value = report_data.get(
            field,
            "Not Available"
        )

        line = f"{field}: {value}"


        if y < 60:

            pdf.showPage()

            y = height - 50

            pdf.setFont(
                "Helvetica",
                10
            )


        pdf.drawString(
            60,
            y,
            line[:115]
        )

        y -= 18


    # -----------------------------------------------------
    # NOTICE
    # -----------------------------------------------------

    y -= 15


    if y < 90:

        pdf.showPage()

        y = height - 50


    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        50,
        y,
        "Prototype Notice"
    )

    y -= 18


    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        50,
        y,
        "This report is generated by a prototype and does not"
    )

    y -= 14

    pdf.drawString(
        50,
        y,
        "replace official government land-record verification."
    )


    pdf.save()

    buffer.seek(0)


    return send_file(
        buffer,
        as_attachment=True,
        download_name="LandSure_Verification_Report.pdf",
        mimetype="application/pdf"
    )


# =========================================================
# AI ASSISTANT
# =========================================================

@app.route(
    "/assistant",
    methods=["GET", "POST"]
)
def assistant():

    answer = None

    if request.method == "POST":

        question = request.form.get(
            "question",
            ""
        ).lower().strip()


        if "duplicate" in question:

            answer = (
                "LandSure AI compares Khasra Number, "
                "Survey Number, Owner, Village and District "
                "with stored prototype records."
            )

        elif "verify" in question:

            answer = (
                "LandSure AI reads the uploaded PDF, "
                "checks land-related information and "
                "extracts important property details."
            )

        elif "map" in question:

            answer = (
                "The Land Map module checks whether a "
                "supported map file has been uploaded."
            )

        elif "report" in question:

            answer = (
                "After successful verification, LandSure AI "
                "automatically generates a verification report."
            )

        else:

            answer = (
                "LandSure AI can help with land-document "
                "analysis, verification, duplicate screening "
                "and report generation."
            )


    return render_template(
        "assistant.html",
        answer=answer
    )


# =========================================================
# FILE SIZE ERROR
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return render_template(
        "documents.html",
        error="File is too large. Maximum allowed size is 10 MB."
    ), 413


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )