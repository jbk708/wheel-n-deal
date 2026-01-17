"""Tests for user service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, User
from services.user_service import get_or_create_signal_user


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


class TestGetOrCreateSignalUser:
    """Tests for get_or_create_signal_user function."""

    def test_creates_new_user_with_phone_only(self, db_session):
        """Creates a new user when phone number doesn't exist."""
        user = get_or_create_signal_user(db_session, "+1234567890")

        assert user.id is not None
        assert user.signal_phone == "+1234567890"
        assert user.signal_username is None

    def test_creates_new_user_with_phone_and_username(self, db_session):
        """Creates a new user with both phone and username."""
        user = get_or_create_signal_user(db_session, "+1234567890", "John Doe")

        assert user.signal_phone == "+1234567890"
        assert user.signal_username == "John Doe"

    def test_returns_existing_user_by_phone(self, db_session):
        """Returns existing user when phone already exists."""
        existing = User(signal_phone="+1234567890", signal_username="Original Name")
        db_session.add(existing)
        db_session.commit()
        original_id = existing.id

        user = get_or_create_signal_user(db_session, "+1234567890")

        assert user.id == original_id
        assert user.signal_phone == "+1234567890"

    def test_updates_username_when_changed(self, db_session):
        """Updates username when user exists but has new username."""
        existing = User(signal_phone="+1234567890", signal_username="Old Name")
        db_session.add(existing)
        db_session.commit()
        original_id = existing.id

        user = get_or_create_signal_user(db_session, "+1234567890", "New Name")

        assert user.id == original_id
        assert user.signal_username == "New Name"

    def test_does_not_overwrite_username_with_none(self, db_session):
        """Does not clear username when new username is None."""
        existing = User(signal_phone="+1234567890", signal_username="Keep This")
        db_session.add(existing)
        db_session.commit()

        user = get_or_create_signal_user(db_session, "+1234567890", None)

        assert user.signal_username == "Keep This"

    def test_sets_username_when_previously_none(self, db_session):
        """Sets username when user had None before."""
        existing = User(signal_phone="+1234567890", signal_username=None)
        db_session.add(existing)
        db_session.commit()

        user = get_or_create_signal_user(db_session, "+1234567890", "New Name")

        assert user.signal_username == "New Name"

    def test_different_phone_creates_different_user(self, db_session):
        """Different phone numbers create separate users."""
        user1 = get_or_create_signal_user(db_session, "+1111111111", "User One")
        user2 = get_or_create_signal_user(db_session, "+2222222222", "User Two")

        assert user1.id != user2.id
        assert user1.signal_phone == "+1111111111"
        assert user2.signal_phone == "+2222222222"

    def test_user_persisted_to_database(self, db_session):
        """Verifies user is actually saved to database."""
        get_or_create_signal_user(db_session, "+1234567890", "Test User")

        users = db_session.query(User).all()
        assert len(users) == 1
        assert users[0].signal_phone == "+1234567890"
