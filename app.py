import os
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from database import get_db_connection, create_tables, seed_data
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "eventora-local-development-key"
)

# -----------------------------
# INITIALIZE DATABASE
# -----------------------------
create_tables()
seed_data()


# -----------------------------
# LOGIN REQUIRED DECORATOR
# -----------------------------
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


# -----------------------------
# ADMIN REQUIRED DECORATOR
# -----------------------------
def admin_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))

        return route_function(*args, **kwargs)

    return wrapper


# -----------------------------
# HOME PAGE
# -----------------------------
@app.route("/")
def index():

    conn = get_db_connection()

    events = conn.execute("""
        SELECT *
        FROM events
        ORDER BY date ASC
        LIMIT 3
    """).fetchall()

    conn.close()

    return render_template("index.html", events=events)


# -----------------------------
# USER REGISTRATION
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        conn = get_db_connection()

        existing_user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("An account with this email already exists.", "warning")
            return redirect(url_for("register"))

        conn.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'user')
        """, (name, email, password))

        conn.commit()
        conn.close()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ? AND password = ?
        """, (email, password)).fetchone()

        conn.close()

        if user:

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out successfully.", "success")

    return redirect(url_for("index"))


# -----------------------------
# USER DASHBOARD
# -----------------------------
@app.route("/dashboard")
@login_required
def dashboard():

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    conn = get_db_connection()

    total_registrations = conn.execute("""
        SELECT COUNT(*) AS count
        FROM registrations
        WHERE user_id = ? AND status = 'Registered'
    """, (session["user_id"],)).fetchone()["count"]

    upcoming_events = conn.execute("""
        SELECT e.*
        FROM events e
        INNER JOIN registrations r
        ON e.id = r.event_id
        WHERE r.user_id = ?
        AND r.status = 'Registered'
        AND e.date >= date('now')
        ORDER BY e.date ASC
        LIMIT 3
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_registrations=total_registrations,
        upcoming_events=upcoming_events
    )


# -----------------------------
# VIEW ALL EVENTS
# -----------------------------
@app.route("/events")
def events():

    conn = get_db_connection()

    events = conn.execute("""
        SELECT *
        FROM events
        ORDER BY date ASC
    """).fetchall()

    conn.close()

    return render_template("events.html", events=events)


# -----------------------------
# EVENT DETAILS
# -----------------------------
@app.route("/event/<int:event_id>")
def event_details(event_id):

    conn = get_db_connection()

    event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    conn.close()

    if event is None:
        flash("Event not found.", "danger")
        return redirect(url_for("events"))

    return render_template("event-details.html", event=event)


# -----------------------------
# REGISTER FOR EVENT
# -----------------------------
@app.route("/register-event/<int:event_id>", methods=["POST"])
@login_required
def register_event(event_id):

    # Admin cannot register for events
    if session.get("role") == "admin":
        flash("Administrators cannot register for events.", "warning")
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

        # Check whether event exists
        event = conn.execute("""
            SELECT *
            FROM events
            WHERE id = ?
        """, (event_id,)).fetchone()

        if event is None:
            flash("Event not found.", "danger")
            return redirect(url_for("events"))

        # Check existing registration
        existing_registration = conn.execute("""
            SELECT *
            FROM registrations
            WHERE user_id = ? AND event_id = ?
        """, (session["user_id"], event_id)).fetchone()

        # Prevent duplicate active registration
        if (
            existing_registration
            and existing_registration["status"] == "Registered"
        ):
            flash("You are already registered for this event.", "warning")
            return redirect(
                url_for("event_details", event_id=event_id)
            )

        # Check available seats
        if event["available_seats"] <= 0:
            flash("Sorry, this event is full.", "danger")
            return redirect(
                url_for("event_details", event_id=event_id)
            )

        registration_date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if existing_registration:

            # Reactivate cancelled registration
            conn.execute("""
                UPDATE registrations
                SET status = 'Registered',
                    registration_date = ?
                WHERE id = ?
            """, (
                registration_date,
                existing_registration["id"]
            ))

        else:

            # Create new registration
            conn.execute("""
                INSERT INTO registrations
                (user_id, event_id, registration_date, status)
                VALUES (?, ?, ?, 'Registered')
            """, (
                session["user_id"],
                event_id,
                registration_date
            ))

        # Reduce available seats
        conn.execute("""
            UPDATE events
            SET available_seats = available_seats - 1
            WHERE id = ?
        """, (event_id,))

        conn.commit()

        flash("Successfully registered for the event!", "success")
        return redirect(url_for("my_events"))

    except Exception as e:

        conn.rollback()
        print("Registration error:", e)

        flash("Something went wrong. Please try again.", "danger")
        return redirect(url_for("events"))

    finally:
        conn.close()


# -----------------------------
# MY REGISTRATIONS
# -----------------------------
@app.route("/my-events")
@login_required
def my_events():

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    conn = get_db_connection()

    registrations = conn.execute("""
        SELECT
            r.id,
            r.user_id,
            r.event_id,
            r.registration_date,
            r.status,
            e.title,
            e.description,
            e.date,
            e.time,
            e.venue,
            e.category,
            e.capacity,
            e.available_seats
        FROM registrations r
        JOIN events e
        ON r.event_id = e.id
        WHERE r.user_id = ?
        ORDER BY e.date ASC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "my-events.html",
        registrations=registrations
    )


# -----------------------------
# CANCEL REGISTRATION
# -----------------------------
@app.route("/cancel/<int:registration_id>", methods=["POST"])
@login_required
def cancel_registration(registration_id):

    if session.get("role") == "admin":
        flash("Administrators cannot cancel user registrations.", "warning")
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

        registration = conn.execute("""
            SELECT *
            FROM registrations
            WHERE id = ?
            AND user_id = ?
            AND status = 'Registered'
        """, (
            registration_id,
            session["user_id"]
        )).fetchone()

        if registration is None:
            flash("Registration not found.", "danger")
            return redirect(url_for("my_events"))

        # Update registration status
        conn.execute("""
            UPDATE registrations
            SET status = 'Cancelled'
            WHERE id = ?
        """, (registration_id,))

        # Increase available seats
        conn.execute("""
            UPDATE events
            SET available_seats = available_seats + 1
            WHERE id = ?
        """, (registration["event_id"],))

        conn.commit()

        flash("Registration cancelled successfully.", "success")

    except Exception as e:

        conn.rollback()
        print("Cancellation error:", e)

        flash("Unable to cancel registration.", "danger")

    finally:
        conn.close()

    return redirect(url_for("my_events"))


# =====================================================
# ADMIN SECTION
# =====================================================

# -----------------------------
# ADMIN DASHBOARD
# -----------------------------
@app.route("/admin")
@admin_required
def admin():

    conn = get_db_connection()

    total_events = conn.execute("""
        SELECT COUNT(*) AS count
        FROM events
    """).fetchone()["count"]

    total_users = conn.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role = 'user'
    """).fetchone()["count"]

    total_registrations = conn.execute("""
        SELECT COUNT(*) AS count
        FROM registrations
        WHERE status = 'Registered'
    """).fetchone()["count"]

    events = conn.execute("""
        SELECT *
        FROM events
        ORDER BY date ASC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        total_events=total_events,
        total_users=total_users,
        total_registrations=total_registrations,
        events=events
    )


# -----------------------------
# ADD EVENT
# -----------------------------
@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def add_event():

    if request.method == "POST":

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        date = request.form["date"]
        time = request.form["time"]
        venue = request.form["venue"].strip()
        category = request.form["category"].strip()
        capacity = request.form["capacity"]

        if not all([
            title,
            description,
            date,
            time,
            venue,
            category,
            capacity
        ]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("add_event"))

        try:

            capacity = int(capacity)

            if capacity <= 0:
                raise ValueError

        except ValueError:
            flash("Capacity must be a positive number.", "danger")
            return redirect(url_for("add_event"))

        conn = get_db_connection()

        conn.execute("""
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
        """, (
            title,
            description,
            date,
            time,
            venue,
            category,
            capacity,
            capacity
        ))

        conn.commit()
        conn.close()

        flash("Event added successfully.", "success")

        return redirect(url_for("admin"))

    return render_template("add-event.html")


# -----------------------------
# EDIT EVENT
# -----------------------------
@app.route("/admin/edit/<int:event_id>", methods=["GET", "POST"])
@admin_required
def edit_event(event_id):

    conn = get_db_connection()

    event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    if not event:
        conn.close()
        flash("Event not found.", "danger")
        return redirect(url_for("admin"))

    if request.method == "POST":

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        date = request.form["date"]
        time = request.form["time"]
        venue = request.form["venue"].strip()
        category = request.form["category"].strip()
        capacity = request.form["capacity"]

        if not all([
            title,
            description,
            date,
            time,
            venue,
            category,
            capacity
        ]):
            conn.close()
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("admin"))

        try:

            capacity = int(capacity)

            if capacity <= 0:
                raise ValueError

            # Count active registrations
            registered_count = conn.execute("""
                SELECT COUNT(*) AS count
                FROM registrations
                WHERE event_id = ?
                AND status = 'Registered'
            """, (event_id,)).fetchone()["count"]

            # Capacity cannot be lower than registrations
            if capacity < registered_count:

                flash(
                    f"Capacity cannot be less than the "
                    f"{registered_count} existing registrations.",
                    "danger"
                )

                conn.close()
                return render_template("edit-event.html", event=event)

            available_seats = capacity - registered_count

            conn.execute("""
                UPDATE events
                SET title = ?,
                    description = ?,
                    date = ?,
                    time = ?,
                    venue = ?,
                    category = ?,
                    capacity = ?,
                    available_seats = ?
                WHERE id = ?
            """, (
                title,
                description,
                date,
                time,
                venue,
                category,
                capacity,
                available_seats,
                event_id
            ))

            conn.commit()
            conn.close()

            flash("Event details updated successfully!", "success")
            return redirect(url_for("admin"))

        except ValueError:

            flash("Capacity must be a valid positive number.", "danger")
            conn.close()

            return render_template("edit-event.html", event=event)

    conn.close()

    return render_template("edit-event.html", event=event)


# -----------------------------
# DELETE EVENT
# -----------------------------
@app.route("/admin/delete/<int:event_id>", methods=["POST"])
@admin_required
def delete_event(event_id):

    conn = get_db_connection()

    conn.execute("""
        DELETE FROM registrations
        WHERE event_id = ?
    """, (event_id,))

    conn.execute("""
        DELETE FROM events
        WHERE id = ?
    """, (event_id,))

    conn.commit()
    conn.close()

    flash("Event deleted successfully.", "success")

    return redirect(url_for("admin"))


# -----------------------------
# VIEW ALL REGISTRATIONS
# -----------------------------
@app.route("/admin/registrations")
@admin_required
def admin_registrations():

    conn = get_db_connection()

    registrations = conn.execute("""
        SELECT
            r.id,
            r.registration_date,
            r.status,
            u.name,
            u.email,
            e.title,
            e.date,
            e.venue
        FROM registrations r
        INNER JOIN users u
        ON r.user_id = u.id
        INNER JOIN events e
        ON r.event_id = e.id
        ORDER BY r.registration_date DESC
    """).fetchall()

    conn.close()

    return render_template(
        "registrations.html",
        registrations=registrations
    )


# -----------------------------
# RUN APPLICATION
# -----------------------------
if __name__ == "__main__":
    app.run(debug=False)