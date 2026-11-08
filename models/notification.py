"""In-app notification model."""
from __future__ import annotations

from extensions import db
from utils.helpers import utcnow


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, default="system", index=True)
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User", back_populates="notifications")

    @property
    def icon(self) -> str:
        return {
            "request": "droplet",
            "account": "user",
            "verification": "shield-check",
            "report": "flag",
            "system": "bell",
        }.get(self.category, "bell")

    @property
    def tone(self) -> str:
        return {
            "request": "red",
            "account": "blue",
            "verification": "green",
            "report": "amber",
            "system": "grey",
        }.get(self.category, "grey")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification {self.id} user={self.user_id}>"
