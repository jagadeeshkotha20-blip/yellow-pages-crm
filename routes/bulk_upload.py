import os
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                    flash, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
import pandas as pd

from extensions import db
from models import (
    Lead, User, BulkUploadBatch, AssignmentHistory, SOURCE_BULK_EXCEL, STATUS_NEW,
    CALLING_ROLES, normalize_phone, is_valid_phone,
)
from permissions import management_required, visible_employees_query_for

bulk_bp = Blueprint("bulk", __name__, url_prefix="/bulk-upload")

# Flexible column-name matching so real-world sheets (varying capitalisation/
# spacing) still import cleanly.
COLUMN_ALIASES = {
    "business_name": ["business name", "business", "company", "company name", "name"],
    "contact_person": ["contact person", "contact", "person name"],
    "phone": ["phone", "phone number", "mobile", "mobile number", "contact number"],
    "alt_phone": ["alt phone", "alternate phone", "alternate number", "phone 2"],
    "email": ["email", "email id", "e-mail"],
    "address": ["address", "full address"],
    "city": ["city", "town"],
    "state": ["state"],
}


def _normalize_columns(df):
    lower_map = {c: str(c).strip().lower() for c in df.columns}
    resolved = {}
    for field, aliases in COLUMN_ALIASES.items():
        for col, low in lower_map.items():
            if low in aliases:
                resolved[field] = col
                break
    return resolved


def _allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXCEL_EXTENSIONS"]


@bulk_bp.route("/", methods=["GET", "POST"])
@management_required
def upload():
    assignable_employees = visible_employees_query_for(current_user).filter(
        User.role.in_(CALLING_ROLES), User.is_active_employee.is_(True)
    ).all()

    if request.method == "POST":
        file = request.files.get("excel_file")
        if not file or file.filename == "":
            flash("Please choose an Excel file to upload.", "danger")
            return redirect(url_for("bulk.upload"))

        if not _allowed_file(file.filename):
            flash("Only .xlsx or .xls files are supported.", "danger")
            return redirect(url_for("bulk.upload"))

        filename = secure_filename(file.filename)
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        try:
            df = pd.read_excel(save_path, dtype=str).fillna("")
        except Exception as exc:
            flash(f"Could not read that file: {exc}", "danger")
            return redirect(url_for("bulk.upload"))

        col_map = _normalize_columns(df)
        if "business_name" not in col_map or "phone" not in col_map:
            flash(
                "The sheet must have at least a business/company name column "
                "and a phone number column.", "danger",
            )
            return redirect(url_for("bulk.upload"))

        default_state = request.form.get("default_state", "").strip()
        bulk_assign_to = request.form.get("bulk_assign_to", type=int) or None

        batch = BulkUploadBatch(filename=filename, uploaded_by_id=current_user.id,
                                 total_rows=len(df))
        db.session.add(batch)
        db.session.flush()

        imported, duplicates, errors = 0, 0, 0

        seen_this_batch = set()  # catches duplicate phone numbers within the same sheet

        for _, row in df.iterrows():
            try:
                business_name = str(row.get(col_map.get("business_name", ""), "")).strip()
                phone = normalize_phone(row.get(col_map.get("phone", ""), ""))

                if not business_name or not phone or not is_valid_phone(phone):
                    errors += 1
                    continue

                if phone in seen_this_batch or Lead.query.filter_by(phone=phone).first():
                    duplicates += 1
                    continue
                seen_this_batch.add(phone)

                # A SAVEPOINT around just this row: if it fails, only this row's
                # insert is undone — the rest of the batch (and the batch record
                # itself) stays intact.
                with db.session.begin_nested():
                    lead = Lead(
                        business_name=business_name,
                        contact_person=str(row.get(col_map.get("contact_person", ""), "")).strip(),
                        phone=phone,
                        alt_phone=normalize_phone(row.get(col_map.get("alt_phone", ""), "")),
                        email=str(row.get(col_map.get("email", ""), "")).strip(),
                        address=str(row.get(col_map.get("address", ""), "")).strip(),
                        city=str(row.get(col_map.get("city", ""), "")).strip(),
                        state=str(row.get(col_map.get("state", ""), "")).strip() or default_state,
                        source=SOURCE_BULK_EXCEL,
                        status=STATUS_NEW,
                        created_by_id=current_user.id,
                        assigned_to_id=bulk_assign_to,
                        bulk_batch_id=batch.id,
                    )
                    db.session.add(lead)
                    db.session.flush()

                    if bulk_assign_to:
                        db.session.add(AssignmentHistory(
                            lead_id=lead.id, from_employee_id=None,
                            to_employee_id=bulk_assign_to, changed_by_id=current_user.id,
                            reason="Bulk import auto-assignment",
                        ))

                imported += 1
            except IntegrityError:
                duplicates += 1
                continue
            except Exception:
                errors += 1
                continue

        batch.imported_count = imported
        batch.duplicate_count = duplicates
        batch.error_count = errors
        db.session.commit()

        flash(
            f"Import complete: {imported} leads imported, {duplicates} duplicates skipped, "
            f"{errors} rows had errors.", "success",
        )
        return redirect(url_for("bulk.history"))

    return render_template("bulk_upload.html", employees=assignable_employees)


@bulk_bp.route("/history")
@management_required
def history():
    batches = BulkUploadBatch.query.order_by(BulkUploadBatch.uploaded_at.desc()).all()
    return render_template("bulk_history.html", batches=batches)


@bulk_bp.route("/<int:batch_id>/leads")
@management_required
def batch_leads(batch_id):
    """Requirement #9: 'Access the uploaded data' — browse exactly which leads
    came in from a given import, not just the aggregate counts."""
    batch = BulkUploadBatch.query.get_or_404(batch_id)
    leads = batch.leads.order_by(Lead.created_at.desc()).all()
    return render_template("bulk_batch_leads.html", batch=batch, leads=leads)
