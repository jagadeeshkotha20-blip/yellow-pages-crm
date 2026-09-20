"""
Run once to set up the database with a Super Admin login and a small sample
hierarchy so you can log in and explore the CRM immediately.

Usage:
    python seed.py
"""
from app import create_app
from extensions import db
from models import (
    User, Lead, Team, SUPER_ADMIN, ADMIN, HR_ADMIN, TEAM_LEAD, EMPLOYEE, TELECALLER, BDE,
    SOURCE_WEBSITE, SOURCE_SOCIAL_MEDIA, STATUS_NEW,
)

app = create_app()

with app.app_context():
    db.create_all()

    if User.query.filter_by(email="superadmin@yellowpages.com").first():
        print("Seed data already exists — skipping. Delete instance/crm.db to reseed.")
    else:
        super_admin = User(name="Super Admin", email="superadmin@yellowpages.com",
                            role=SUPER_ADMIN, phone="9999900000")
        super_admin.set_password("Admin@123")
        db.session.add(super_admin)
        db.session.flush()

        admin = User(name="Priya Admin", email="admin@yellowpages.com", role=ADMIN,
                      phone="9999900001", manager_id=super_admin.id)
        admin.set_password("Admin@123")
        db.session.add(admin)
        db.session.flush()

        hr_admin = User(name="Meera HRAdmin", email="hradmin@yellowpages.com", role=HR_ADMIN,
                         phone="9999900005", manager_id=super_admin.id)
        hr_admin.set_password("Admin@123")
        db.session.add(hr_admin)
        db.session.flush()

        team_lead = User(name="Ravi TeamLead", email="teamlead@yellowpages.com", role=TEAM_LEAD,
                          phone="9999900002", manager_id=admin.id, state_scope="Telangana,Andhra Pradesh")
        team_lead.set_password("Admin@123")
        db.session.add(team_lead)
        db.session.flush()

        team = Team(name="South Zone Telecalling Team", team_lead_id=team_lead.id)
        db.session.add(team)
        db.session.flush()
        team_lead.team_id = team.id

        telecaller = User(name="Anita Telecaller", email="telecaller1@yellowpages.com", role=TELECALLER,
                           phone="9999900003", manager_id=team_lead.id, team_id=team.id)
        telecaller.set_password("Admin@123")
        db.session.add(telecaller)

        bde = User(name="Karan BDE", email="bde1@yellowpages.com", role=BDE,
                   phone="9999900004", manager_id=team_lead.id, team_id=team.id)
        bde.set_password("Admin@123")
        db.session.add(bde)

        employee = User(name="Sanjay Employee", email="employee1@yellowpages.com", role=EMPLOYEE,
                         phone="9999900006", manager_id=team_lead.id, team_id=team.id)
        employee.set_password("Admin@123")
        db.session.add(employee)
        db.session.flush()

        sample_leads = [
            Lead(business_name="Sunrise Bakery", phone="9812300001", city="Hyderabad",
                 state="Telangana", source=SOURCE_WEBSITE, status=STATUS_NEW,
                 created_by_id=super_admin.id),
            Lead(business_name="Green Valley Electricals", phone="9812300002", city="Secunderabad",
                 state="Telangana", source=SOURCE_SOCIAL_MEDIA, status=STATUS_NEW,
                 created_by_id=super_admin.id, assigned_to_id=telecaller.id),
            Lead(business_name="Metro Furniture Mart", phone="9812300003", city="Vijayawada",
                 state="Andhra Pradesh", source=SOURCE_WEBSITE, status=STATUS_NEW,
                 created_by_id=super_admin.id),
        ]
        db.session.add_all(sample_leads)
        db.session.commit()

        print("Database seeded successfully!")
        print("\nLogin with any of these accounts (all use password: Admin@123):")
        print("  Super Admin : superadmin@yellowpages.com")
        print("  Admin       : admin@yellowpages.com")
        print("  HR Admin    : hradmin@yellowpages.com")
        print("  Team Lead   : teamlead@yellowpages.com")
        print("  Telecaller  : telecaller1@yellowpages.com")
        print("  BDE         : bde1@yellowpages.com")
        print("  Employee    : employee1@yellowpages.com")
