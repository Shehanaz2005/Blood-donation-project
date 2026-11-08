"""Blood request model and lifecycle helpers."""
from __future__ import annotations

from datetime import date

from extensions import db
from utils.constants import (
    ACTIVE_REQUEST_STATUSES,
    BLOOD_GROUPS,
    REQUEST_ACCEPTED,
    REQUEST_CANCELLED,
    REQUEST_COMPLETED,
    REQUEST_EXPIRED,
    REQUEST_PENDING,
    REQUEST_REJECTED,
    STATUS_META,
    URGENCY_LEVELS,
)
from utils.helpers import generate_reference, utcnow


class BloodRequest(db.Model):
    __tablename__ = "blood_requests"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','accepted','rejected','completed','cancelled','expired')",
            name="ck_requests_status",
        ),
        db.CheckConstraint(
            "urgency IN ('routine','urgent','critical')", name="ck_requests_urgency"
        ),
        db.CheckConstraint("units >= 1 AND units <= 10", name="ck_requests_units"),
        db.CheckConstraint(
            "blood_group IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')",
            name="ck_requests_blood_group",
        ),
        db.Index("ix_requests_donor_status", "donor_id", "status"),
        db.Index("ix_requests_receiver_status", "receiver_id", "status"),
        db.Index("ix_requests_status_created", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(
        db.String(24), nullable=False, unique=True, default=generate_reference
    )
    receiver_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blood_group = db.Column(db.String(3), nullable=False)
    units = db.Column(db.Integer, nullable=False, default=1)
    urgency = db.Column(db.String(12), nullable=False, default="urgent")
    hospital_name = db.Column(db.String(150), nullable=False)
    hospital_address = db.Column(db.String(255))
    city = db.Column(db.String(80), nullable=False)
    needed_by = db.Column(db.Date)
    contact_phone = db.Column(db.String(24), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=REQUEST_PENDING, index=True)
    donor_response = db.Column(db.Text)
    responded_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], back_populates="requests_made"
    )
    donor = db.relationship(
        "User", foreign_keys=[donor_id], back_populates="requests_received"
    )

    # ------------------------------------------------------------------
    # Presentation / lifecycle helpers
    # ------------------------------------------------------------------
    @property
    def status_label(self) -> str:
        return STATUS_META.get(self.status, {}).get("label", self.status.title())

    @property
    def status_badge(self) -> str:
        return STATUS_META.get(self.status, {}).get("badge", "secondary")

    @property
    def status_icon(self) -> str:
        return STATUS_META.get(self.status, {}).get("icon", "circle-info")

    @property
    def is_active_request(self) -> bool:
        return self.status in ACTIVE_REQUEST_STATUSES

    @property
    def is_pending(self) -> bool:
        return self.status == REQUEST_PENDING

    @property
    def is_accepted(self) -> bool:
        return self.status == REQUEST_ACCEPTED

    @property
    def is_completed(self) -> bool:
        return self.status == REQUEST_COMPLETED

    @property
    def is_rejected(self) -> bool:
        return self.status == REQUEST_REJECTED

    @property
    def is_cancelled(self) -> bool:
        return self.status == REQUEST_CANCELLED

    @property
    def is_expired(self) -> bool:
        return self.status == REQUEST_EXPIRED or (
            self.status == REQUEST_PENDING and bool(self.needed_by and self.needed_by < date.today())
        )

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.needed_by
            and self.needed_by < date.today()
            and self.status in ACTIVE_REQUEST_STATUSES
        )

    @property
    def donor_contact_available(self) -> bool:
        donor_profile = self.donor.donor_profile if self.donor else None
        return bool(
            donor_profile
            and donor_profile.share_contact
            and self.status in (REQUEST_ACCEPTED, REQUEST_COMPLETED)
        )

    @property
    def timeline(self) -> list[dict]:
        items = [
            {
                "label": "Request submitted",
                "at": self.created_at,
                "icon": "paper-plane",
                "done": True,
            }
        ]
        if self.responded_at:
            items.append(
                {
                    "label": f"Donor {self.status_label.lower()} the request",
                    "at": self.responded_at,
                    "icon": self.status_icon,
                    "done": True,
                }
            )
        if self.completed_at:
            items.append(
                {
                    "label": "Donation completed",
                    "at": self.completed_at,
                    "icon": "circle-check",
                    "done": True,
                }
            )
        if self.cancelled_at:
            items.append(
                {
                    "label": "Request cancelled",
                    "at": self.cancelled_at,
                    "icon": "ban",
                    "done": True,
                }
            )
        return items

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BloodRequest {self.reference} {self.status}>"
