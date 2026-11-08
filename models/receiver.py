"""Receiver profile model."""
from __future__ import annotations

from extensions import db
from utils.helpers import utcnow


class ReceiverProfile(db.Model):
    __tablename__ = "receiver_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    city = db.Column(db.String(80), nullable=False, index=True)
    address = db.Column(db.String(255))
    preferred_hospital = db.Column(db.String(150))
    patient_relation = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="receiver_profile")

    @property
    def profile_completeness(self) -> int:
        fields = (
            self.user.full_name,
            self.user.email,
            self.user.phone,
            self.city,
            self.address,
            self.preferred_hospital,
            self.patient_relation,
        )
        filled = sum(1 for value in fields if value not in (None, "", []))
        return round(filled / len(fields) * 100)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReceiverProfile {self.id} {self.city}>"
