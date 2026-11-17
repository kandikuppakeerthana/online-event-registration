import sqlite3

DATABASE = "event.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db_connection()
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

            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(id),

            UNIQUE(user_id, event_id)
        )
    """)

    conn.commit()
    conn.close()


def seed_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create default admin
    cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        ("admin@gmail.com",)
    )

    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "System Admin",
            "admin@gmail.com",
            "admin123",
            "admin"
        ))

    # Add sample events only if there are no events
    cursor.execute("SELECT COUNT(*) AS count FROM events")
    event_count = cursor.fetchone()["count"]

    if event_count == 0:
        events = [
            (
                "AI & Machine Learning Workshop",
                "A hands-on workshop covering artificial intelligence, machine learning and real-world applications.",
                "2026-10-15",
                "10:00 AM",
                "Seminar Hall A",
                "Technology",
                100,
                100
            ),
            (
                "Web Development Bootcamp",
                "Learn modern web development concepts including HTML, CSS, JavaScript and backend fundamentals.",
                "2026-10-20",
                "09:30 AM",
                "Computer Lab 2",
                "Development",
                80,
                80
            ),
            (
                "Cyber Security Awareness",
                "Explore common cyber threats, secure computing practices and basic security techniques.",
                "2026-10-25",
                "02:00 PM",
                "Auditorium",
                "Cyber Security",
                150,
                150
            ),
            (
                "Tech Innovation Summit",
                "An interactive event focused on emerging technologies, innovation and future career opportunities.",
                "2026-11-05",
                "10:30 AM",
                "Main Auditorium",
                "Innovation",
                200,
                200
            )
        ]

        cursor.executemany("""
            INSERT INTO events
            (title, description, date, time, venue, category, capacity, available_seats)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, events)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    seed_data()
    print("Database created successfully!")