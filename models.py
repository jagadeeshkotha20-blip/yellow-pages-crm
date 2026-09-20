from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
SUPER_ADMIN = "super_admin"
ADMIN = "admin"
HR_ADMIN = "hr_admin"
TEAM_LEAD = "team_lead"
EMPLOYEE = "employee"
TELECALLER = "telecaller"
BDE = "bde"

ALL_ROLES = [SUPER_ADMIN, ADMIN, HR_ADMIN, TEAM_LEAD, EMPLOYEE, TELECALLER, BDE]

# Roles that are allowed to be assigned leads and make calls
CALLING_ROLES = [TELECALLER, BDE, EMPLOYEE, TEAM_LEAD]

# Roles that count as "management" for visibility purposes
MANAGEMENT_ROLES = [SUPER_ADMIN, ADMIN, HR_ADMIN, TEAM_LEAD]

ROLE_LABELS = {
    SUPER_ADMIN: "Super Admin",
    ADMIN: "Admin",
    HR_ADMIN: "HR Admin",
    TEAM_LEAD: "Team Lead",
    EMPLOYEE: "Employee",
    TELECALLER: "Telecaller",
    BDE: "BDE",
}

# Rank used to decide "is X a manager of Y" style checks (lower = higher authority)
ROLE_RANK = {
    SUPER_ADMIN: 0,
    ADMIN: 1,
    HR_ADMIN: 1,
    TEAM_LEAD: 2,
    EMPLOYEE: 3,
    TELECALLER: 3,
    BDE: 3,
}

# ---------------------------------------------------------------------------
# Lead statuses
# ---------------------------------------------------------------------------
STATUS_NEW = "New"
STATUS_NOT_LIFTED = "Phone Not Lifted"
STATUS_CALL_LATER = "Call Me Later"
STATUS_INTERESTED = "Interested"
STATUS_NOT_INTERESTED = "Not Interested"
STATUS_READY_PAYMENT = "Ready to Make Payment"
STATUS_ALREADY_ENROLLED = "Already Enrolled"
STATUS_FOLLOW_UP = "Follow-up Required"
STATUS_ENROLLED = "Enrolled"
STATUS_OTHER = "Other"

ALL_STATUSES = [
    STATUS_NEW,
    STATUS_NOT_LIFTED,
    STATUS_CALL_LATER,
    STATUS_INTERESTED,
    STATUS_NOT_INTERESTED,
    STATUS_READY_PAYMENT,
    STATUS_ALREADY_ENROLLED,
    STATUS_FOLLOW_UP,
    STATUS_ENROLLED,
    STATUS_OTHER,
]

# Lead sources
SOURCE_WEBSITE = "Website"
SOURCE_SOCIAL_MEDIA = "Social Media"
SOURCE_TELECALLER = "Telecaller"
SOURCE_BDE = "BDE"
SOURCE_BULK_EXCEL = "Bulk/Excel"
SOURCE_MANUAL = "Manual Entry"

ALL_SOURCES = [
    SOURCE_WEBSITE,
    SOURCE_SOCIAL_MEDIA,
    SOURCE_TELECALLER,
    SOURCE_BDE,
    SOURCE_BULK_EXCEL,
    SOURCE_MANUAL,
]

INDIAN_STATES = [
    "All India", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Puducherry", "Chandigarh",
]


def normalize_phone(raw):
    """Strip everything except digits and a leading '+' so the same number
    typed differently (spaces, dashes, brackets) is always stored the same way."""
    if not raw:
        return ""
    raw = str(raw).strip()
    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    return cleaned


def is_valid_phone(cleaned):
    digits = cleaned.lstrip("+")
    return digits.isdigit() and 7 <= len(digits) <= 15


class Team(db.Model):
    """A named team, e.g. 'Telangana Telecalling Team'. Grouping on top of the
    manager_id hierarchy so admins can see/organize by team, not just by chain."""

    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    team_lead_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    team_lead = db.relationship("User", foreign_keys=[team_lead_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship("User", back_populates="team", foreign_keys="User.team_id")


class User(UserMixin, db.Model):
    """An employee/admin account. Hierarchy is modeled via manager_id (self-referential)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=EMPLOYEE)

    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    manager = db.relationship("User", remote_side=[id], backref="direct_reports")

    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    team = db.relationship("Team", back_populates="members", foreign_keys=[team_id])

    # Optional state scoping for admins/team leads that only handle certain states.
    # Comma-separated list of states, or empty/NULL = all states.
    state_scope = db.Column(db.String(500), nullable=True)

    is_active_employee = db.Column(db.Boolean, default=True, nullable=False)
    resigned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- brute-force login protection ---
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def is_locked_out(self):
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    # Flask-Login expects `is_active` — map it to our employment status so a
    # deactivated/resigned employee can no longer log in.
    @property
    def is_active(self):
        return self.is_active_employee

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    def is_super_admin(self):
        return self.role == SUPER_ADMIN

    def is_management(self):
        return self.role in MANAGEMENT_ROLES

    def can_call(self):
        return self.role in CALLING_ROLES

    def scoped_states(self):
        """Returns list of states this user is restricted to, or None for all."""
        if not self.state_scope:
            return None
        return [s.strip() for s in self.state_scope.split(",") if s.strip()]

    def all_subordinate_ids(self, include_self=True):
        """Recursively walk the manager hierarchy to find everyone under this user."""
        ids = set()
        if include_self:
            ids.add(self.id)
        frontier = [self.id]
        while frontier:
            children = User.query.filter(User.manager_id.in_(frontier)).all()
            frontier = []
            for c in children:
                if c.id not in ids:
                    ids.add(c.id)
                    frontier.append(c.id)
        return ids

    def is_manager_of(self, other_user):
        if self.is_super_admin():
            return True
        return other_user.id in self.all_subordinate_ids(include_self=False)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Lead(db.Model):
    """A business/customer record that needs to be contacted about a Yellow Pages listing."""

    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(120))
    # Unique at the DB level — this is the actual guarantee against duplicate
    # lead records for the same phone number, enforced even under concurrent
    # writes (app-level dedupe checks alone can't fully prevent race conditions).
    phone = db.Column(db.String(20), nullable=False, unique=True, index=True)
    alt_phone = db.Column(db.String(20))
    email = db.Column(db.String(160))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100), index=True)

    source = db.Column(db.String(50), default=SOURCE_MANUAL)
    status = db.Column(db.String(50), default=STATUS_NEW, index=True)

    # Which bulk import brought this lead in, if any — lets admins actually
    # "access the uploaded data" per batch (Requirement #9), not just totals.
    bulk_batch_id = db.Column(db.Integer, db.ForeignKey("bulk_upload_batches.id"), nullable=True)

    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    call_logs = db.relationship("CallLog", backref="lead", lazy="dynamic",
                                 order_by="CallLog.call_time.desc()",
                                 cascade="all, delete-orphan")
    follow_ups = db.relationship("FollowUp", backref="lead", lazy="dynamic",
                                  order_by="FollowUp.follow_up_date.asc()",
                                  cascade="all, delete-orphan")
    assignment_history = db.relationship("AssignmentHistory", backref="lead", lazy="dynamic",
                                          order_by="AssignmentHistory.changed_at.desc()",
                                          cascade="all, delete-orphan")
    enrollment = db.relationship("Enrollment", backref="lead", uselist=False,
                                  cascade="all, delete-orphan")

    @property
    def is_locked(self):
        """A lead is 'locked' to whoever it's currently assigned to."""
        return self.assigned_to_id is not None

    @property
    def next_follow_up(self):
        return (
            self.follow_ups.filter_by(is_completed=False)
            .order_by(FollowUp.follow_up_date.asc())
            .first()
        )

    def __repr__(self):
        return f"<Lead {self.business_name} ({self.phone})>"


class CallLog(db.Model):
    """Immutable historical record of a call. Never edited/deleted when a lead is reassigned."""

    __tablename__ = "call_logs"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)

    # The employee who actually made this call — kept forever, even after reassignment.
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    employee = db.relationship("User")

    call_time = db.Column(db.DateTime, default=datetime.utcnow)
    status_set = db.Column(db.String(50))
    notes = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, nullable=True)


class FollowUp(db.Model):
    __tablename__ = "follow_ups"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)

    # Who scheduled/owns this follow-up at the time it was created — historical.
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    employee = db.relationship("User")

    follow_up_date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssignmentHistory(db.Model):
    """Every assignment / reassignment / release / transfer event for a lead."""

    __tablename__ = "assignment_history"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)

    from_employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    to_employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    from_employee = db.relationship("User", foreign_keys=[from_employee_id])
    to_employee = db.relationship("User", foreign_keys=[to_employee_id])
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])

    reason = db.Column(db.String(200))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)


class Enrollment(db.Model):
    """Payment/enrollment record once a lead converts."""

    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, unique=True)
    plan = db.Column(db.String(100))
    amount = db.Column(db.Numeric(10, 2))
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_by = db.relationship("User")


class BulkUploadBatch(db.Model):
    """Tracks each Excel/bulk import so admins can audit what was imported and when."""

    __tablename__ = "bulk_upload_batches"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    uploaded_by = db.relationship("User")
    total_rows = db.Column(db.Integer, default=0)
    imported_count = db.Column(db.Integer, default=0)
    duplicate_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    leads = db.relationship("Lead", backref="bulk_batch", lazy="dynamic",
                             foreign_keys="Lead.bulk_batch_id")
