from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from sqlalchemy import MetaData

# Explicit naming convention so every constraint Alembic generates has a real
# name. Without this, SQLite migrations that need to drop/alter a constraint
# (common once you're using batch_alter_table) fail with "unnamed constraint"
# errors — this makes every future `flask db migrate` safe by default.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access the CRM."
login_manager.login_message_category = "warning"

csrf = CSRFProtect()
migrate = Migrate()
