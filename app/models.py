from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="passenger")
    phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class BusRoute(db.Model):
    __tablename__ = "bus_routes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    origin = db.Column(db.String(120), nullable=False)
    destination = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

class PassType(db.Model):
    __tablename__ = "pass_types"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(30), nullable=False)
    duration = db.Column(db.String(30), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    __table_args__ = (db.UniqueConstraint("category", "duration"),)

class FareRule(db.Model):
    __tablename__ = "fare_rules"
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey("bus_routes.id"), nullable=False)
    pass_type_id = db.Column(db.Integer, db.ForeignKey("pass_types.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    route = db.relationship("BusRoute")
    pass_type = db.relationship("PassType")
    __table_args__ = (db.UniqueConstraint("route_id", "pass_type_id"),)

class PassApplication(db.Model):
    __tablename__ = "pass_applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey("bus_routes.id"), nullable=False)
    pass_type_id = db.Column(db.Integer, db.ForeignKey("pass_types.id"), nullable=False)
    status = db.Column(db.String(20), default="Pending", nullable=False, index=True)
    review_reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime)
    user = db.relationship("User")
    route = db.relationship("BusRoute")
    pass_type = db.relationship("PassType")

class BusPass(db.Model):
    __tablename__ = "bus_passes"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("pass_applications.id"), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey("bus_routes.id"), nullable=False)
    pass_type_id = db.Column(db.Integer, db.ForeignKey("pass_types.id"), nullable=False)
    pass_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    verification_token = db.Column(db.String(64), unique=True, nullable=False)
    issued_at = db.Column(db.Date, nullable=False)
    expires_at = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), default="Active", nullable=False, index=True)
    user = db.relationship("User")
    route = db.relationship("BusRoute")
    pass_type = db.relationship("PassType")

class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("pass_applications.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    transaction_ref = db.Column(db.String(50), unique=True, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class VerificationLog(db.Model):
    __tablename__ = "verification_logs"
    id = db.Column(db.Integer, primary_key=True)
    pass_id = db.Column(db.Integer, db.ForeignKey("bus_passes.id"))
    verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    result = db.Column(db.String(30), nullable=False)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)


