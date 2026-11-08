"""Notification helpers."""
from __future__ import annotations

from extensions import db
from models.notification import Notification


def notify(user, title: str, message: str, category: str = "system", link: str | None = None) -> Notification:
    """Queue an in-app notification. The caller owns the transaction."""
    notification = Notification(
        user_id=user.id,
        title=title[:150],
        message=message,
        category=category if category else "system",
        link=link,
    )
    db.session.add(notification)
    return notification


def notify_many(users, title: str, message: str, category: str = "system", link: str | None = None):
    for user in users:
        notify(user, title, message, category=category, link=link)


def mark_all_read(user, commit: bool = True) -> int:
    """Mark every unread notification for ``user`` as read.

    The ``notifications`` relationship declares ``order_by`` for display, and
    SQLAlchemy refuses ``Query.update()`` on an ordered query. ``order_by(None)``
    clears it so the bulk update works.
    """
    count = (
        user.notifications.order_by(None)
        .filter_by(is_read=False)
        .update({"is_read": True}, synchronize_session=False)
    )
    if commit:
        db.session.commit()
    return count
