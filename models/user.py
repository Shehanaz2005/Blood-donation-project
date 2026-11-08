"""User account model and role helpers."""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from utils.constants import ROLE_ADMIN, ROLE_DONOR, ROLE_RECEIVER, ROLES
from utils.helpers import utcnow


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('donor','receiver','admin')", name="ck_users_role"
        ),
        db.Index("ix_users_role_created", "role", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_DONOR, index=True)
    phone = db.Column(db.String(24), index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # one-to-one profile relationships
    donor_profile = db.relationship(
        "DonorProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
        foreign_keys="DonorProfile.user_id",
    )
    receiver_profile = db.relationship(
        "ReceiverProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    admin_profile = db.relationship(
        "AdminProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )

    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
        lazy="dynamic",
    )
    requests_made = db.relationship(
        "BloodRequest",
        foreign_keys="BloodRequest.receiver_id",
        back_populates="receiver",
        lazy="dynamic",
    )
    requests_received = db.relationship(
        "BloodRequest",
        foreign_keys="BloodRequest.donor_id",
        back_populates="donor",
        lazy="dynamic",
    )
    reports_filed = db.relationship(
        "Report",
        foreign_keys="Report.reporter_id",
        back_populates="reporter",
        lazy="dynamic",
    )
    reports_received = db.relationship(
        "Report",
        foreign_keys="Report.reported_user_id",
        back_populates="reported_user",
        lazy="dynamic",
    )

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------
    @property
    def is_donor(self) -> bool:
        return self.role == ROLE_DONOR

    @property
    def is_receiver(self) -> bool:
        return self.role == ROLE_RECEIVER

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_admin_role(self) -> bool:
        """Explicit alias used by templates (avoids clashing with Flask-Login)."""
        return self.role == ROLE_ADMIN

    @property
    def profile(self):
        if self.role == ROLE_DONOR:
            return self.donor_profile
        if self.role == ROLE_RECEIVER:
            return self.receiver_profile
        if self.role == ROLE_ADMIN:
            return self.admin_profile
        return None

    @property
    def display_name(self) -> str:
        parts = (self.full_name or "").strip().split()
        return parts[0] if parts else "There"

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        if not parts:
            return "BC"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def unread_notifications(self) -> int:
        return self.notifications.filter_by(is_read=False).count()

    def touch_login(self) -> None:
        self.last_login_at = utcnow()

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<User {self.id} {self.email} ({self.role})>"
