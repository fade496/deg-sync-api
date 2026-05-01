import csv
import os
import re
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


TABLES = {
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
    "contracts": "tblSOm11yRrU6gckp",
    "contacts": "tblk1KQFBKDA1WPna",
}


CSV_HEADERS = [
    "LINETYPE",
    "WORKDATE",
    "REFWO",
    "LABORCODE",
    "LABORDESC",
    "LABORISNIGHTSHIFT",
    "LABORPAYCODE",
    "LABORHRS",
    "CRAFT+SKILL/PREM",
]


DETAIL_HEADERS = [
    "Index",
    "Date",
    "LEM Name",
    "Employee",
    "Project",
    "Description",
    "Hours",
    "WO",
]


# =============================================================================
# Airtable helpers
# =============================================================================

def airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing AIRTABLE_API_KEY")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def airtable_list_records(
    table_id: str,
    formula: Optional[str] = None,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"pageSize": 100}

        if formula:
            params["filterByFormula"] = formula

        if offset:
            params["offset"] = offset

        response = requests.get(
            f"{AIRTABLE_API_ROOT}/{table_id}",
            headers=airtable_headers(),
            params=params,
            timeout=60,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Airtable read failed",
                    "table_id": table_id,
                    "status_code": response.status_code,
                    "response": response.text,
                },
            )

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")

        if not offset:
            break

    return records


def airtable_get_by_ids(
    table_id: str,
    ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    ids = [record_id for record_id in ids if record_id]

    if not ids:
        return {}

    output: Dict[str, Dict[str, Any]] = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]

        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{record_id}'" for record_id in chunk]
        ) + ")"

        records = airtable_list_records(table_id, formula=formula)

        for record in records:
            output[record["id"]] = record.get("fields", {})

    return output


# =============================================================================
# General helpers
# =============================================================================

def first_link(value: Any) -> Optional[str]:
    if isinstance(value, list) and value:
        return value[0]

    return None


def clean_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return ""

        if len(value) == 1:
            return clean_value(value[0])

        return ", ".join(clean_value(item) for item in value)

    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "")

    if value is None:
        return ""

    return str(value).strip()


def safe_filename(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^\w.\- ]+", "", text)
    text = text.replace(" ", "")
    return text or "LEM"


def split_first_last(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], ""

    return parts[0], " ".join(parts[1:])


def parse_date(value: Any) -> Optional[datetime]:
    text = clean_value(value)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def parse_hours(value: Any) -> Optional[float]:
    try:
        return float(clean_value(value).replace(",", ""))
    except ValueError:
        return None


def format_hours(value: float) -> str:
    return (
        f"{int(value)}"
        if float(value).is_integer()
        else f"{value:.2f}".rstrip("0").rstrip(".")
    )


def extract_wo(*values: Any) -> str:
    joined = " ".join(clean_value(value) for value in values)

    match = re.search(r"WO[-\s:]?(\d+)", joined, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    digits = re.search(r"(\d{6,})", joined)
    return digits.group(1) if digits else ""


def extract_id_digits(value: Any) -> str:
    digits = re.findall(r"\d+", clean_value(value))
    return digits[0] if digits else clean_value(value)


def extract_employee_id_from_roles(value: Any) -> str:
    text = clean_value(value)

    match = re.search(r"\bID-(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    return ""


def get_employee_id(person: Dict[str, Any]) -> str:
    return (
        clean_value(person.get("Employee ID"))
        or extract_employee_id_from_roles(person.get("Harvest Roles"))
        or clean_value(person.get("Harvest User ID"))
    )


def format_lem_date_name(rows: List[Dict[str, Any]]) -> str:
    dates = sorted(row["work_date"] for row in rows)
    start = dates[0]
    end = dates[-1]
    short_code = rows[0].get("short_code") or "LEM"

    if start.month == end.month:
        date_part = f"{start:%m.%d}-{end:%d.%Y}"
    else:
        date_part = f"{start:%m.%d}-{end:%m.%d.%Y}"

    return f"{date_part}.{short_code}"


# =============================================================================
# Data loading
# =============================================================================

def load_time_entries(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    formula = (
        "AND("
        f"IS_AFTER({{Spent Date}}, DATEADD('{from_date}', -1, 'days')), "
        f"IS_BEFORE({{Spent Date}}, DATEADD('{to_date}', 1, 'days'))"
        ")"
    )

    return airtable_list_records(TABLES["time_entries"], formula=formula)


def hydrate(
    time_entries: List[Dict[str, Any]],
) -> tuple[
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
]:
    project_ids = set()
    person_ids = set()
    task_ids = set()
    approver_ids = set()
    contract_ids = set()

    for record in time_entries:
        fields = record.get("fields", {})

        project_ids.add(first_link(fields.get("Project")))
        person_ids.add(first_link(fields.get("Person")))
        task_ids.add(first_link(fields.get("Task")))

    projects = airtable_get_by_ids(TABLES["projects"], list(project_ids))

    for project in projects.values():
        approver_ids.add(first_link(project.get("Approver")))
        contract_ids.add(first_link(project.get("Contracts")))

    people = airtable_get_by_ids(TABLES["people"], list(person_ids))
    tasks = airtable_get_by_ids(TABLES["tasks"], list(task_ids))
    approvers = airtable_get_by_ids(TABLES["contacts"], list(approver_ids))
    contracts = airtable_get_by_ids(TABLES["contracts"], list(contract_ids))

    return projects, people, tasks, approvers, contracts


# =============================================================================
# Contract / craft / approver logic
# =============================================================================

def get_contract_for_project(
    project: Dict[str, Any],
    contracts_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    contract_id = first_link(project.get("Contracts"))
    if not contract_id:
        return {}

    return contracts_by_id.get(contract_id, {})


def normalize_billing_method(value: Any) -> str:
    text = clean_value(value).lower()

    if "craft code 2" in text or text == "craft 2":
        return "Craft 2"

    if "craft code 3" in text or text == "craft 3":
        return "Craft 3"

    return "Craft 1"


def choose_craft_code(
    billing_method: Any,
    person: Dict[str, Any],
) -> str:
    method = normalize_billing_method(billing_method)

    craft1 = clean_value(
        person.get("Description (from Craft1)")
        or person.get("Craft1")
    )
    craft2 = clean_value(
        person.get("Description (from Craft2)")
        or person.get("Craft2")
    )
    craft3 = clean_value(
        person.get("Description (from Craft3)")
        or person.get("Craft3")
    )

    if method == "Craft 2":
        return craft2 or craft1

    if method == "Craft 3":
        return craft3 or craft1

    return craft1


def get_approver(
    project: Dict[str, Any],
    approvers: Dict[str, Dict[str, Any]],
) -> Dict[str, str]:
    approver_id = first_link(project.get("Approver"))
    approver = approvers.get(approver_id, {})

    full_name = clean_value(approver.get("Full Name"))
    first_name = clean_value(approver.get("First Name"))
    last_name = clean_value(approver.get("Last Name"))

    if not first_name and not last_name:
        first_name, last_name = split_first_last(full_name)

    email = clean_value(
        approver.get("Email")
        or project.get("Email (from Approver)")
    )

    approver_name = (
        f"{first_name} {last_name}".strip()
        or full_name
        or "Unassigned Approver"
    )

    return {
        "first": first_name,
        "last": last_name,
        "name": approver_name,
        "email": email,
    }


# =============================================================================
# Row normalization
# =============================================================================

def build_normalized_rows(
    time_entries: List[Dict[str, Any]],
    projects: Dict[str, Dict[str, Any]],
    people: Dict[str, Dict[str, Any]],
    tasks: Dict[str, Dict[str, Any]],
    approvers: Dict[str, Dict[str, Any]],
    contracts: Dict[str, Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []

    for record in time_entries:
        record_id = record.get("id", "")
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))
        task_id = first_link(fields.get("Task"))

        project = projects.get(project_id, {})
        person = people.get(person_id, {})
        task = tasks.get(task_id, {})
        contract = get_contract_for_project(project, contracts)
        approver = get_approver(project, approvers)

        project_code = clean_value(project.get("Code"))
        project_name = clean_value(project.get("Name"))

        is_active = bool(project.get("Is Active"))
        invoice_type = clean_value(project.get("Invoice Type"))

        if not is_active:
            errors.append(
                f"{record_id}: skipped inactive project "
                f"{project_code or project_name}"
            )
            continue

        if invoice_type.upper() != "LEM":
            errors.append(
                f"{record_id}: skipped non-LEM invoice type for project "
                f"{project_code or project_name}: {invoice_type or 'blank'}"
            )
            continue

        first_name = clean_value(person.get("First Name"))
        last_name = clean_value(person.get("Last Name"))

        if not first_name and not last_name:
            first_name, last_name = split_first_last(
                clean_value(person.get("Full Name"))
            )

        employee_name = (
            f"{first_name} {last_name}".strip()
            or clean_value(person.get("Full Name"))
        )

        employee_id = get_employee_id(person)

        work_date = parse_date(fields.get("Spent Date"))
        hours = parse_hours(fields.get("Hours"))

        if not project_code:
            errors.append(f"{record_id}: missing project code")
            continue

        if not contract:
            errors.append(
                f"{record_id}: missing linked contract for project {project_code}"
            )
            continue

        if not employee_name:
            errors.append(f"{record_id}: missing employee name")
            continue

        if not employee_id:
            errors.append(f"{record_id}: missing employee ID for {employee_name}")
            continue

        if work_date is None:
            errors.append(f"{record_id}: invalid or missing spent date")
            continue

        if hours is None:
            errors.append(f"{record_id}: invalid or missing hours")
            continue

        notes = clean_value(fields.get("Notes"))
        task_name = clean_value(task.get("Name"))

        description = notes or task_name or project_name
        wo = extract_wo(task_name, notes)

        rows.append({
            "contract": clean_value(contract.get("Contract")),
            "short_code": clean_value(contract.get("Short Code")),
            "project_code": project_code,
            "project_name": project_name,
            "billing_method": clean_value(project.get("Billing Method")),
            "approver_first": approver["first"],
            "approver_last": approver["last"],
            "approver_name": approver["name"],
            "approver_email": approver["email"],
            "employee_name": employee_name,
            "employee_id": employee_id,
            "work_date": work_date,
            "work_date_str": work_date.strftime("%m/%d/%y"),
            "hours": hours,
            "hours_str": format_hours(hours),
            "wo": wo,
            "labor_code": extract_id_digits(employee_id),
            "craft_code": choose_craft_code(project.get("Billing Method"), person),
            "description": description,
            "report_name": "",
        })

    rows.sort(
        key=lambda row: (
            row["contract"],
            row["approver_name"],
            row["work_date"],
            row["employee_name"],
        )
    )

    return rows, errors


# =============================================================================
# CSV generation
# =============================================================================

def write_contract_csv(
    contract_rows: List[Dict[str, Any]],
    output_dir: Path,
) -> Path:
    base_name = format_lem_date_name(contract_rows)
    contract = contract_rows[0]["contract"]
    csv_path = output_dir / f"{safe_filename(base_name)}.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow(["CNRLEMLINE", base_name, contract, "O"])
        writer.writerow(CSV_HEADERS)

        for row in contract_rows:
            writer.writerow([
                "L",
                row["work_date_str"],
                row["wo"],
                row["labor_code"],
                row["employee_name"],
                "0",
                "801",
                row["hours_str"],
                row["craft_code"],
            ])

    return csv_path


# =============================================================================
# PDF generation
# =============================================================================

def create_pdf_reports(
    rows: List[Dict[str, Any]],
    output_dir: Path,
) -> List[Path]:
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for row in rows:
        grouped[(row["contract"], row["approver_name"])].append(row)

    pdf_paths: List[Path] = []

    for (_, approver_name), group in grouped.items():
        base_name = format_lem_date_name(group)
        safe_approver = safe_filename(approver_name)
        report_name = f"{base_name}.{safe_approver}"

        for row in group:
            row["report_name"] = report_name

        pdf_path = output_dir / f"{safe_filename(report_name)}.pdf"
        build_report_pdf(group, pdf_path)
        pdf_paths.append(pdf_path)

    return pdf_paths


def build_report_pdf(rows: List[Dict[str, Any]], output_path: Path) -> None:
    page_width, page_height = landscape(letter)

    left = 0.35 * inch
    right = 0.35 * inch
    top = 0.35 * inch
    bottom = 0.35 * inch

    usable_width = page_width - left - right
    usable_height = page_height - top - bottom

    header_h = 1.10 * inch
    signature_h = 0.65 * inch
    table_h = usable_height - header_h - signature_h - 0.08 * inch

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=landscape(letter),
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
    )

    frame = Frame(
        left,
        bottom + signature_h,
        usable_width,
        table_h,
        id="detail",
    )

    def on_page(canvas, _doc):
        draw_pdf_page_decor(
            canvas,
            rows,
            left,
            bottom,
            usable_width,
            page_height - top,
        )

    doc.addPageTemplates([
        PageTemplate(id="lem", frames=[frame], onPage=on_page)
    ])

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )

    data: List[List[Any]] = [DETAIL_HEADERS]

    for idx, row in enumerate(rows, start=1):
        data.append([
            str(idx),
            row["work_date"].strftime("%m/%d/%Y"),
            row["report_name"],
            row["employee_name"],
            row["project_name"],
            Paragraph(escape_pdf(row["description"]), body),
            row["hours_str"],
            row["wo"],
        ])

    col_widths = fit_column_widths(data, usable_width, styles)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 1), (2, -1), "LEFT"),
        ("ALIGN", (6, 1), (7, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    doc.build([table])


def draw_pdf_page_decor(
    canvas,
    rows: List[Dict[str, Any]],
    left: float,
    bottom: float,
    usable_width: float,
    top_y: float,
) -> None:
    total_hours = sum(row["hours"] for row in rows)
    project_names = sorted({row["project_name"] for row in rows})
    project_label = (
        project_names[0]
        if len(project_names) == 1
        else "Multiple Projects"
    )

    report_name = rows[0]["report_name"]
    client = rows[0]["contract"]
    approver = rows[0]["approver_name"]

    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(left, top_y + 2, "DEG engineering")

    box_top = top_y - 14
    row_h = 18
    label_w = 86
    value_w = usable_width / 2 - label_w - 6

    x1 = left
    x2 = left + usable_width / 2

    labels1 = [
        ("Client:", client),
        ("Project:", project_label),
        ("Date Generated:", datetime.now().strftime("%m/%d/%Y")),
    ]

    labels2 = [
        ("Report Name:", report_name),
        ("Report Approver:", approver),
        ("Total Hours:", format_hours(total_hours)),
    ]

    for i, (label, value) in enumerate(labels1):
        y = box_top - i * row_h
        draw_header_cell(canvas, x1, y, label_w, row_h, label, bold=True)
        draw_header_cell(canvas, x1 + label_w, y, value_w, row_h, value)

    for i, (label, value) in enumerate(labels2):
        y = box_top - i * row_h
        draw_header_cell(canvas, x2, y, label_w, row_h, label, bold=True)
        draw_header_cell(canvas, x2 + label_w, y, value_w, row_h, value)

    footer_y = bottom + 16

    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(left + 18, footer_y + 18, "Signature:")
    canvas.drawString(left + usable_width * 0.72, footer_y + 18, "Date:")


def draw_header_cell(
    canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    bold: bool = False,
) -> None:
    canvas.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
    canvas.drawString(x + 4, y - 12, str(text))


def fit_column_widths(
    data: List[List[Any]],
    total_width: float,
    styles,
) -> List[float]:
    raw_widths = []

    for col_idx in range(len(DETAIL_HEADERS)):
        max_width = (
            stringWidth(str(DETAIL_HEADERS[col_idx]), "Helvetica-Bold", 8)
            + 12
        )

        for row in data[1:]:
            value = row[col_idx]

            if isinstance(value, Paragraph):
                width = 180
            else:
                width = stringWidth(str(value), "Helvetica", 8) + 10

            max_width = max(max_width, width)

        raw_widths.append(max_width)

    scale = total_width / sum(raw_widths)
    widths = [width * scale for width in raw_widths]

    min_widths = [28, 54, 75, 90, 110, 170, 42, 52]
    widths = [
        max(widths[index], min_widths[index])
        for index in range(len(widths))
    ]

    total = sum(widths)

    if total > total_width:
        overflow = total - total_width
        widths[5] = max(min_widths[5], widths[5] - overflow)

    return widths


def escape_pdf(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# =============================================================================
# ZIP output
# =============================================================================

def write_errors(errors: List[str], output_dir: Path) -> Optional[Path]:
    if not errors:
        return None

    errors_path = output_dir / "errors.txt"
    errors_path.write_text("\n".join(errors), encoding="utf-8")

    return errors_path


def zip_output_dir(output_dir: Path) -> Path:
    zip_path = output_dir.parent / "lem_outputs.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in output_dir.rglob("*"):
            if path.is_file():
                zip_file.write(path, arcname=path.relative_to(output_dir))

    return zip_path


# =============================================================================
# Main service entry point
# =============================================================================

def generate_lem(payload) -> str:
    work_dir = Path(tempfile.mkdtemp(prefix="lem_"))
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    time_entries = load_time_entries(payload.from_date, payload.to_date)

    if not time_entries:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No time entries found from "
                f"{payload.from_date} to {payload.to_date}"
            ),
        )

    projects, people, tasks, approvers, contracts = hydrate(time_entries)

    rows, errors = build_normalized_rows(
        time_entries=time_entries,
        projects=projects,
        people=people,
        tasks=tasks,
        approvers=approvers,
        contracts=contracts,
    )

    if not rows:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid LEM rows were generated",
                "errors": errors,
            },
        )

    grouped_by_contract: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in rows:
        grouped_by_contract[row["contract"]].append(row)

    for contract_rows in grouped_by_contract.values():
        write_contract_csv(contract_rows, output_dir)

    create_pdf_reports(rows, output_dir)
    write_errors(errors, output_dir)

    return str(zip_output_dir(output_dir))
