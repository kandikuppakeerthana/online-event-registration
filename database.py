import os
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash


# Use the deployment database path if provided.
# Otherwise, store event.db in the project directory.
BASE_DIR = Path(__file__).resolve().parent

DATABASE = os.environ.get(
    "DATABASE_PATH",
    str(BASE_DIR / "event.db")
)


def get_db_connection():
    """Create and return a database connection."""

    # Create the database directory if it does not exist.
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    # Enable foreign key constraints.
    conn.execute("PRAGMA foreign_keys = ON")

    # Wait for other database operations to finish.
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def create_tables():
    """Create all required tables."""

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        """)

        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                venue TEXT NOT NULL,
                category TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                available_seats INTEGER NOT NULL
            )
        """)

        # Registrations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                registration_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Registered',

                FOREIGN KEY (user_id)
                    REFERENCES users(id),

                FOREIGN KEY (event_id)
                    REFERENCES events(id),

                UNIQUE(user_id, event_id)
            )
        """)

        # Helpful indexes for frequently accessed records.
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_registrations_user
            ON registrations(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_registrations_event
            ON registrations(event_id)
        """)

        conn.commit()

    finally:
        conn.close()


def seed_data():
    """Insert default admin and sample events if required."""

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        with conn:

            # Create default admin only if it does not exist.
            cursor.execute(
                "SELECT id FROM users WHERE email = ?",
                ("admin@gmail.com",)
            )

            if cursor.fetchone() is None:

                hashed_password = generate_password_hash("admin123")

                cursor.execute("""
                    INSERT INTO users
                    (name, email, password, role)
                    VALUES (?, ?, ?, ?)
                """, (
                    "System Admin",
                    "admin@gmail.com",
                    hashed_password,
                    "admin"
                ))

            # Insert sample events only when the events table is empty.
            cursor.execute("SELECT COUNT(*) AS count FROM events")

            event_count = cursor.fetchone()["count"]

            if event_count == 0:

                events = [
                    (
                        "AI & Machine Learning Workshop",
                        "A hands-on workshop covering artificial intelligence, machine learning and real-world applications.",
                        "2026-11-25",
                        "10:00 AM",
                        "Seminar Hall A",
                        "Technology",
                        100,
                        100
                    ),
                    (
                        "Web Development Bootcamp",
                        "Learn modern web development concepts including HTML, CSS, JavaScript and backend fundamentals.",
                        "2026-12-02",
                        "09:30 AM",
                        "Computer Lab 2",
                        "Development",
                        80,
                        80
                    ),
                    (
                        "Cyber Security Awareness",
                        "Explore common cyber threats, secure computing practices and basic security techniques.",
                        "2026-12-10",
                        "02:00 PM",
                        "Auditorium",
                        "Cyber Security",
                        150,
                        150
                    ),
                    (
                        "Tech Innovation Summit",
                        "An interactive event focused on emerging technologies, innovation and future career opportunities.",
                        "2026-12-18",
                        "10:30 AM",
                        "Main Auditorium",
                        "Innovation",
                        200,
                        200
                    )
                ]

                cursor.executemany("""
                    INSERT INTO events
                    (
                        title,
                        description,
                        date,
                        time,
                        venue,
                        category,
                        capacity,
                        available_seats
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, events)

    finally:
        conn.close()


if __name__ == "__main__":

    create_tables()
    seed_data()

    print("EVENTORA database created successfully!")
    print(f"Database location: {DATABASE}")