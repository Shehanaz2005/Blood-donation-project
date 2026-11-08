"""Donor profile model with eligibility and privacy helpers."""
from __future__ import annotations

from datetime import date, timedelta

from flask import current_app

from extensions import db
from utils.constants import BLOOD_GROUPS
from utils.helpers import utcnow


class DonorProfile(db.Model):
    __tablename__ = "donor_profiles"
    __table_args__ = (
        db.CheckConstraint(
            "blood_group IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')",
            name="ck_donor_blood_group",
        ),
        db.Index("ix_donor_search", "blood_group", "city", "is_available"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    blood_group = db.Column(db.String(3), nullable=False, index=True)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(24))
    weight_kg = db.Column(db.Numeric(5, 1))
    city = db.Column(db.String(80), nullable=False, index=True)
    address = db.Column(db.String(255))
    last_donation_date = db.Column(db.Date)
    is_available = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False, index=True)
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    share_contact = db.Column(db.Boolean, nullable=False, default=True)
    total_donations = db.Column(db.Integer, nullable=False, default=0)
    bio = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="donor_profile", foreign_keys=[user_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------
    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    @property
    def cooldown_days(self) -> int:
        return int(current_app.config.get("DONATION_COOLDOWN_DAYS", 90))

    @property
    def next_eligible_date(self) -> date | None:
        if not self.last_donation_date:
            return None
        return self.last_donation_date + timedelta(days=self.cooldown_days)

    @property
    def days_until_eligible(self) -> int:
        if not self.next_eligible_date:
            return 0
        return max((self.next_eligible_date - date.today()).days, 0)

    @property
    def is_in_cooldown(self) -> bool:
        return bool(self.next_eligible_date and self.next_eligible_date > date.today())

    @property
    def weight_ok(self) -> bool:
        if self.weight_kg is None:
            return True
        return float(self.weight_kg) >= current_app.config.get("MIN_DONOR_WEIGHT_KG", 50)

    @property
    def age_ok(self) -> bool:
        if self.age is None:
            return False
        return (
            current_app.config.get("MIN_DONOR_AGE", 18)
            <= self.age
            <= current_app.config.get("MAX_DONOR_AGE", 65)
        )

    @property
    def is_eligible(self) -> bool:
        """Medically eligible today (age, weight, donation interval)."""
        return self.age_ok and self.weight_ok and not self.is_in_cooldown

    @property
    def can_accept_requests(self) -> bool:
        return bool(self.is_available and self.is_verified and self.is_eligible)

    @property
    def eligibility_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.is_verified:
            reasons.append("Your profile is awaiting administrator verification.")
        if not self.is_available:
            reasons.append("You have switched your availability to “Unavailable”.")
        if not self.age_ok:
            reasons.append("Donors must be between 18 and 65 years old.")
        if not self.weight_ok:
            reasons.append("Donors must weigh at least 50 kg.")
        if self.is_in_cooldown:
            reasons.append(
                f"You can donate again in {self.days_until_eligible} day(s) "
                f"({self.next_eligible_date:%d %b %Y})."
            )
        return reasons

    @property
    def profile_completeness(self) -> int:
        fields = (
            self.user.full_name,
            self.user.email,
            self.user.phone,
            self.blood_group,
            self.date_of_birth,
            self.gender,
            self.weight_kg,
            self.city,
            self.address,
            self.bio,
        )
        filled = sum(1 for value in fields if value not in (None, "", []))
        return round(filled / len(fields) * 100)

    @property
    def donation_streak_label(self) -> str:
        count = self.total_donations or 0
        if count >= 10:
            return "Platinum donor"
        if count >= 5:
            return "Gold donor"
        if count >= 2:
            return "Regular donor"
        if count == 1:
            return "First-time hero"
        return "New donor"

    def verify(self, admin_user) -> None:
        self.is_verified = True
        self.verified_at = utcnow()
        self.verified_by_id = admin_user.id

    def unverify(self) -> None:
        self.is_verified = False
        self.verified_at = None
        self.verified_by_id = None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DonorProfile {self.id} {self.blood_group} {self.city}>"
