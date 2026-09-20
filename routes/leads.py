import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    Lead, User, CallLog, FollowUp, AssignmentHistory, Enrollment,
    ALL_STATUSES, ALL_SOURCES, INDIAN_STATES, SOURCE_MANUAL, SOURCE_TELECALLER, SOURCE_BDE,
    STATUS_NEW, STATUS_ENROLLED, CALLING_ROLES, TELECALLER, BDE, normalize_phone, is_valid_phone,
)
from permissions import (
    leads_query_for_user, can_view_lead, can_work_lead, can_manage_employee,
    visible_employees_query_for,
)

leads_bp = Blueprint("leads", __name__, url_prefix="/leads")


@leads_bp.route("/")
@login_required
def list_leads():
    query = _apply_lead_filters(leads_query_for_user(current_user), request.args)

    status = request.args.get("status", "").strip()
    source = request.args.get("source", "").strip()
    state = request.args.get("state", "").strip()
    assigned = request.args.get("assigned", "").strip()
    search = request.args.get("q", "").strip()

    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Lead.updated_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    assignable_employees = visible_employees_query_for(current_user).filter(
        User.role.in_(CALLING_ROLES), User.is_active_employee.is_(True)
    ).all()

    return render_template(
        "leads_list.html",
        pagination=pagination,
        leads=pagination.items,
        statuses=ALL_STATUSES,
        sources=ALL_SOURCES,
        states=INDIAN_STATES,
        employees=assignable_employees,
        filters=dict(status=status, source=source, state=state, assigned=assigned, q=search),
    )


def _apply_lead_filters(query, args):
    status = args.get("status", "").strip()
    source = args.get("source", "").strip()
    state = args.get("state", "").strip()
    assigned = args.get("assigned", "").strip()
    search = args.get("q", "").strip()

    if status:
        query = query.filter(Lead.status == status)
    if source:
        query = query.filter(Lead.source == source)
    if state:
        query = query.filter(Lead.state == state)
    if assigned == "unassigned":
        query = query.filter(Lead.assigned_to_id.is_(None))
    elif assigned:
        query = query.filter(Lead.assigned_to_id == int(assigned))
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Lead.business_name.ilike(like), Lead.phone.ilike(like),
                   Lead.contact_person.ilike(like))
        )
    return query


@leads_bp.route("/export.csv")
@login_required
def export_leads_csv():
    """Exports the current filtered view of leads (scoped to what this user can see)."""
    query = _apply_lead_filters(leads_query_for_user(current_user), request.args)
    leads = query.order_by(Lead.updated_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Business Name", "Contact Person", "Phone", "Alt Phone", "Email", "City", "State",
        "Source", "Status", "Assigned To", "Next Follow-up", "Created At", "Updated At",
    ])
    for lead in leads:
        nf = lead.next_follow_up
        writer.writerow([
            lead.business_name, lead.contact_person or "", lead.phone, lead.alt_phone or "",
            lead.email or "", lead.city or "", lead.state or "", lead.source, lead.status,
            lead.assigned_to.name if lead.assigned_to else "Unassigned",
            nf.follow_up_date.strftime("%Y-%m-%d %H:%M") if nf else "",
            lead.created_at.strftime("%Y-%m-%d %H:%M"),
            lead.updated_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@leads_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_lead():
    if request.method == "POST":
        form = request.form
        business_name = form.get("business_name", "").strip()
        phone = normalize_phone(form.get("phone", ""))
        alt_phone = normalize_phone(form.get("alt_phone", ""))

        errors = []
        if not business_name:
            errors.append("Business name is required.")
        if not phone or not is_valid_phone(phone):
            errors.append("Please enter a valid phone number (7-15 digits).")
        elif Lead.query.filter_by(phone=phone).first():
            errors.append(f"A lead with phone number {phone} already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            # Re-render with whatever the user already typed so nothing is lost.
            return render_template("lead_form.html", states=INDIAN_STATES, form_data=form)

        lead = Lead(
            business_name=business_name,
            contact_person=form.get("contact_person", "").strip(),
            phone=phone,
            alt_phone=alt_phone,
            email=form.get("email", "").strip(),
            address=form.get("address", "").strip(),
            city=form.get("city", "").strip(),
            state=form.get("state", "").strip(),
            # A telecaller/BDE entering a business they sourced themselves is a
            # genuine "Telecaller"/"BDE" lead source per the requirement doc —
            # not generic manual entry.
            source={TELECALLER: SOURCE_TELECALLER, BDE: SOURCE_BDE}.get(current_user.role, SOURCE_MANUAL),
            status=STATUS_NEW,
            created_by_id=current_user.id,
        )
        db.session.add(lead)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That phone number was just added by someone else — please check the leads list.", "danger")
            return render_template("lead_form.html", states=INDIAN_STATES, form_data=form)

        flash(f"Lead '{lead.business_name}' created.", "success")
        return redirect(url_for("leads.view_lead", lead_id=lead.id))

    return render_template("lead_form.html", states=INDIAN_STATES, form_data={})


@leads_bp.route("/<int:lead_id>")
@login_required
def view_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_view_lead(current_user, lead):
        abort(403)

    can_work = can_work_lead(current_user, lead)
    assignable_employees = visible_employees_query_for(current_user).filter(
        User.role.in_(CALLING_ROLES), User.is_active_employee.is_(True)
    ).all()

    return render_template(
        "lead_detail.html",
        lead=lead,
        can_work=can_work,
        statuses=ALL_STATUSES,
        employees=assignable_employees,
        is_management=current_user.is_management(),
    )


@leads_bp.route("/<int:lead_id>/claim", methods=["POST"])
@login_required
def claim_lead(lead_id):
    """Atomically claim an unassigned lead — prevents two employees claiming the same one."""
    if not current_user.can_call() and not current_user.is_management():
        abort(403)

    # Conditional UPDATE: only succeeds if the lead is still unassigned at the moment
    # of the write. This is the concurrency guard against duplicate-calling.
    result = db.session.execute(
        db.update(Lead)
        .where(Lead.id == lead_id, Lead.assigned_to_id.is_(None))
        .values(assigned_to_id=current_user.id, updated_at=datetime.utcnow())
    )
    db.session.commit()

    if result.rowcount == 0:
        flash("That lead has already been picked up by someone else.", "warning")
        return redirect(url_for("leads.list_leads"))

    history = AssignmentHistory(
        lead_id=lead_id, from_employee_id=None, to_employee_id=current_user.id,
        changed_by_id=current_user.id, reason="Claimed from unassigned pool",
    )
    db.session.add(history)
    db.session.commit()
    flash("Lead claimed. It's now locked to you.", "success")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/assign", methods=["POST"])
@login_required
def assign_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not (current_user.is_management()):
        abort(403)

    new_employee_id = request.form.get("employee_id", type=int)
    reason = request.form.get("reason", "").strip() or "Reassigned by manager"

    new_employee = User.query.get(new_employee_id) if new_employee_id else None
    if new_employee_id and new_employee is None:
        flash("Selected employee not found.", "danger")
        return redirect(url_for("leads.view_lead", lead_id=lead_id))

    old_employee_id = lead.assigned_to_id

    if old_employee_id == new_employee_id:
        flash("Lead is already assigned to that employee.", "info")
        return redirect(url_for("leads.view_lead", lead_id=lead_id))

    lead.assigned_to_id = new_employee_id
    lead.updated_at = datetime.utcnow()

    history = AssignmentHistory(
        lead_id=lead.id, from_employee_id=old_employee_id, to_employee_id=new_employee_id,
        changed_by_id=current_user.id, reason=reason,
    )
    db.session.add(history)
    db.session.commit()

    if new_employee_id:
        flash(f"Lead assigned to {new_employee.name}.", "success")
    else:
        flash("Lead released back to the unassigned pool.", "info")

    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/release", methods=["POST"])
@login_required
def release_lead(lead_id):
    """Employee voluntarily releases a lead they can't/won't continue working."""
    lead = Lead.query.get_or_404(lead_id)
    if not can_work_lead(current_user, lead):
        abort(403)

    old_employee_id = lead.assigned_to_id
    lead.assigned_to_id = None
    lead.updated_at = datetime.utcnow()

    history = AssignmentHistory(
        lead_id=lead.id, from_employee_id=old_employee_id, to_employee_id=None,
        changed_by_id=current_user.id, reason="Released back to unassigned pool",
    )
    db.session.add(history)
    db.session.commit()
    flash("Lead released.", "info")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/call", methods=["POST"])
@login_required
def log_call(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_work_lead(current_user, lead):
        abort(403)

    new_status = request.form.get("status", "").strip()
    notes = request.form.get("notes", "").strip()
    duration = request.form.get("duration_minutes", type=int)

    if new_status not in ALL_STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("leads.view_lead", lead_id=lead_id))

    call = CallLog(
        lead_id=lead.id,
        employee_id=current_user.id,
        status_set=new_status,
        notes=notes,
        duration_minutes=duration,
    )
    db.session.add(call)

    lead.status = new_status
    lead.updated_at = datetime.utcnow()
    db.session.commit()

    flash("Call logged and status updated.", "success")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/followup", methods=["POST"])
@login_required
def add_followup(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_work_lead(current_user, lead):
        abort(403)

    date_str = request.form.get("follow_up_date", "")
    notes = request.form.get("notes", "").strip()
    try:
        follow_up_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Please provide a valid follow-up date/time.", "danger")
        return redirect(url_for("leads.view_lead", lead_id=lead_id))

    fu = FollowUp(
        lead_id=lead.id, employee_id=current_user.id,
        follow_up_date=follow_up_date, notes=notes,
    )
    db.session.add(fu)
    db.session.commit()
    flash("Follow-up scheduled.", "success")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/followup/<int:fu_id>/complete", methods=["POST"])
@login_required
def complete_followup(lead_id, fu_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_work_lead(current_user, lead):
        abort(403)
    fu = FollowUp.query.get_or_404(fu_id)
    fu.is_completed = True
    db.session.commit()
    flash("Follow-up marked as done.", "success")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/enroll", methods=["POST"])
@login_required
def enroll_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_work_lead(current_user, lead):
        abort(403)

    plan = request.form.get("plan", "").strip()
    amount = request.form.get("amount", type=float)

    if lead.enrollment:
        flash("This lead is already enrolled.", "info")
        return redirect(url_for("leads.view_lead", lead_id=lead_id))

    enrollment = Enrollment(
        lead_id=lead.id, plan=plan, amount=amount, created_by_id=current_user.id,
    )
    db.session.add(enrollment)
    lead.status = STATUS_ENROLLED
    lead.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Lead marked as enrolled and payment recorded.", "success")
    return redirect(url_for("leads.view_lead", lead_id=lead_id))
