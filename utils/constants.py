"""Domain constants and small lookup helpers."""
from __future__ import annotations

BLOOD_GROUPS: tuple[str, ...] = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")

BLOOD_GROUP_LABELS = {
    "A+": "A positive",
    "A-": "A negative",
    "B+": "B positive",
    "B-": "B negative",
    "AB+": "AB positive",
    "AB-": "AB negative",
    "O+": "O positive",
    "O-": "O negative",
}

# Donor group -> recipient groups that can safely receive from that donor.
DONOR_TO_RECIPIENTS: dict[str, tuple[str, ...]] = {
    "O-": BLOOD_GROUPS,
    "O+": ("O+", "A+", "B+", "AB+"),
    "A-": ("A-", "A+", "AB-", "AB+"),
    "A+": ("A+", "AB+"),
    "B-": ("B-", "B+", "AB-", "AB+"),
    "B+": ("B+", "AB+"),
    "AB-": ("AB-", "AB+"),
    "AB+": ("AB+",),
}

# Rarity shown on the landing page (approximate global distribution).
BLOOD_GROUP_RARITY = {
    "O+": "Most common",
    "O-": "Universal donor",
    "A+": "Common",
    "A-": "Rare",
    "B+": "Less common",
    "B-": "Rare",
    "AB+": "Rarest positive",
    "AB-": "Rarest",
}


def compatible_donor_groups(recipient_group: str) -> tuple[str, ...]:
    """Groups whose red cells a recipient with ``recipient_group`` can receive."""
    if recipient_group not in BLOOD_GROUPS:
        return (recipient_group,) if recipient_group else BLOOD_GROUPS
    return tuple(
        donor
        for donor, recipients in DONOR_TO_RECIPIENTS.items()
        if recipient_group in recipients
    )


ROLE_DONOR = "donor"
ROLE_RECEIVER = "receiver"
ROLE_ADMIN = "admin"
ROLES: tuple[str, ...] = (ROLE_DONOR, ROLE_RECEIVER, ROLE_ADMIN)
ROLE_LABELS = {
    ROLE_DONOR: "Donor",
    ROLE_RECEIVER: "Receiver",
    ROLE_ADMIN: "Administrator",
}

GENDERS = ("Male", "Female", "Other", "Prefer not to say")

PATIENT_RELATIONS = (
    "Self",
    "Parent",
    "Child",
    "Sibling",
    "Spouse",
    "Relative",
    "Friend",
    "Other",
)

REQUEST_PENDING = "pending"
REQUEST_ACCEPTED = "accepted"
REQUEST_REJECTED = "rejected"
REQUEST_COMPLETED = "completed"
REQUEST_CANCELLED = "cancelled"
REQUEST_EXPIRED = "expired"

REQUEST_STATUSES: tuple[str, ...] = (
    REQUEST_PENDING,
    REQUEST_ACCEPTED,
    REQUEST_REJECTED,
    REQUEST_COMPLETED,
    REQUEST_CANCELLED,
    REQUEST_EXPIRED,
)
ACTIVE_REQUEST_STATUSES: tuple[str, ...] = (REQUEST_PENDING, REQUEST_ACCEPTED)

STATUS_META = {
    REQUEST_PENDING: {"label": "Pending", "badge": "warning", "icon": "hourglass-half"},
    REQUEST_ACCEPTED: {"label": "Accepted", "badge": "info", "icon": "hand-holding-medical"},
    REQUEST_REJECTED: {"label": "Declined", "badge": "danger", "icon": "circle-xmark"},
    REQUEST_COMPLETED: {"label": "Completed", "badge": "success", "icon": "circle-check"},
    REQUEST_CANCELLED: {"label": "Cancelled", "badge": "secondary", "icon": "ban"},
    REQUEST_EXPIRED: {"label": "Expired", "badge": "dark", "icon": "clock"},
}

URGENCY_ROUTINE = "routine"
URGENCY_URGENT = "urgent"
URGENCY_CRITICAL = "critical"

URGENCY_LEVELS: tuple[str, ...] = (URGENCY_ROUTINE, URGENCY_URGENT, URGENCY_CRITICAL)
URGENCY_META = {
    URGENCY_ROUTINE: {"label": "Routine", "badge": "success", "description": "Within the next few days"},
    URGENCY_URGENT: {"label": "Urgent", "badge": "warning", "description": "Needed within 24-48 hours"},
    URGENCY_CRITICAL: {"label": "Critical", "badge": "danger", "description": "Needed immediately"},
}

REPORT_REASONS = (
    "Fake or misleading profile",
    "Harassment or abusive behaviour",
    "No-show after accepting",
    "Inappropriate contact",
    "Spam or advertising",
    "Other",
)

REPORT_OPEN = "open"
REPORT_REVIEWING = "reviewing"
REPORT_RESOLVED = "resolved"
REPORT_DISMISSED = "dismissed"
REPORT_STATUSES = (REPORT_OPEN, REPORT_REVIEWING, REPORT_RESOLVED, REPORT_DISMISSED)

REPORT_STATUS_META = {
    REPORT_OPEN: {"label": "Open", "badge": "warning"},
    REPORT_REVIEWING: {"label": "Reviewing", "badge": "info"},
    REPORT_RESOLVED: {"label": "Resolved", "badge": "success"},
    REPORT_DISMISSED: {"label": "Dismissed", "badge": "secondary"},
}

NOTIFICATION_CATEGORIES = (
    "system",
    "request",
    "account",
    "verification",
    "report",
)

NAV_LINKS = (
    ("main.home", "Home"),
    ("main.find_donors", "Find Donors"),
    ("auth.register_donor", "Become a Donor"),
    ("main.about", "About Us"),
)
