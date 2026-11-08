"""Administrator metadata profile."""
from __future__ import annotations

from extensions import db
from utils.helpers import utcnow


class AdminProfile(db.Model):
    __tablename__ = "admin_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title = db.Column(db.String(80), nullable=False, default="Administrator")
    notes = db.Column(db.String(255))
    can_manage_admins = db.Column(db.Boolean, nullable=False, default=False)
    last_action_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="admin_profile")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminProfile {self.id} {self.title}>"
