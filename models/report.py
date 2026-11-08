"""User report / moderation model."""
from __future__ import annotations

from extensions import db
from utils.constants import REPORT_OPEN, REPORT_STATUSES
from utils.helpers import utcnow


class Report(db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('open','reviewing','resolved','dismissed')",
            name="ck_reports_status",
        ),
        db.CheckConstraint("reporter_id <> reported_user_id", name="ck_reports_not_self"),
        db.Index("ix_reports_status_created", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reported_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id = db.Column(
        db.Integer, db.ForeignKey("blood_requests.id", ondelete="SET NULL")
    )
    reason = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=REPORT_OPEN, index=True)
    admin_note = db.Column(db.Text)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    reporter = db.relationship(
        "User", foreign_keys=[reporter_id], back_populates="reports_filed"
    )
    reported_user = db.relationship(
        "User", foreign_keys=[reported_user_id], back_populates="reports_received"
    )
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    @property
    def is_open(self) -> bool:
        return self.status in ("open", "reviewing")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report {self.id} {self.status}>"
