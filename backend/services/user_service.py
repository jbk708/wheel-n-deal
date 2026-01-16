"""User service for managing Signal users."""

from sqlalchemy.orm import Session

from models import User


def get_or_create_signal_user(
    db: Session,
    signal_phone: str,
    signal_username: str | None = None,
) -> User:
    """Get an existing user by Signal phone or create a new one.

    If the user exists and a new username is provided, update the username.

    Args:
        db: Database session.
        signal_phone: The user's Signal phone number in E.164 format.
        signal_username: The user's Signal profile name (optional).

    Returns:
        The existing or newly created User record.
    """
    user = db.query(User).filter(User.signal_phone == signal_phone).first()

    if user is None:
        user = User(signal_phone=signal_phone, signal_username=signal_username)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif signal_username is not None and user.signal_username != signal_username:
        user.signal_username = signal_username
        db.commit()

    return user
