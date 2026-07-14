"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Mirrors the patterns in test_collection.py:
happy path, duplicate/conflict handling, and a nonexistent film id, plus a
test that pins down the watchlist's sort order.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a WatchlistEntry in the database.
    """
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        # Verify it persisted
        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInWatchlistError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        # Confirm only one entry exists
        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── Nonexistent film ─────────────────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── get_watchlist sort order ─────────────────────────────────────────────────

def test_get_watchlist_returns_alphabetical_by_title(app, sample_user):
    """
    get_watchlist() sorts by film title ascending. A watchlist is a
    reference list you scan to pick what to watch next, so a stable
    alphabetical order is more useful than recency (see PR discussion,
    Comment 5). This test pins that decision down.
    """
    with app.app_context():
        # Add out of alphabetical order to prove the sort, not insertion order.
        film_z = Film(title="Zodiac", year=2007, genre="Thriller")
        film_a = Film(title="Amelie", year=2001, genre="Romance")
        film_m = Film(title="Memento", year=2000, genre="Thriller")
        db.session.add_all([film_z, film_a, film_m])
        db.session.commit()

        add_to_watchlist(user_id=sample_user, film_id=film_z.id)
        add_to_watchlist(user_id=sample_user, film_id=film_a.id)
        add_to_watchlist(user_id=sample_user, film_id=film_m.id)

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        assert titles == ["Amelie", "Memento", "Zodiac"]
