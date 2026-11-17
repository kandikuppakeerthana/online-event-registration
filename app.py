import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.middleware.proxy_fix import ProxyFix

from database import get_db_connection, create_tables, seed_data


# =====================================================
# APPLICATION CONFIGURATION
# =====================================================

app = Flask(__name__)

IS_RENDER = bool(os.environ.get("RENDER"))

SECRET_KEY = os.environ.get("SECRET_KEY")

if IS_RENDER and not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required on Render."
    )

app.secret_key = SECRET_KEY or "eventora-local-development-key"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get(
            "COOKIE_SECURE",
            "true" if IS_RENDER else "false"
        ).lower() == "true"
    ),
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024
)

# Trust the HTTPS/proxy headers from the Render reverse proxy.
# Render sits in front of the application as a proxy.
if IS_RENDER:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1
    )


# =====================================================
# DATABASE INITIALIZATION
# =====================================================

create_tables()
seed_data()


# =====================================================
# SECURITY HEADERS
# =====================================================

@app.after_request
def add_security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# =====================================================
# PASSWORD HELPERS
# =====================================================

def verify_password(stored_password, entered_password):
    """
    Verify hashed passwords and support existing plaintext
    passwords from the earlier version of the application.

    Legacy plaintext passwords are upgraded after successful login.
    """

    try:
        if check_password_hash(stored_password, entered_password):
            return True, False

    except (ValueError, TypeError):
        pass

    # Legacy plaintext password compatibility
    if stored_password == entered_password:
        return True, True

    return False, False


# =====================================================
# LOGIN REQUIRED DECORATOR
# =====================================================

def login_required(route_function):

    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


# =====================================================
# ADMIN REQUIRED DECORATOR
# =====================================================

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


# =====================================================
# HOME PAGE
# =====================================================

@app.route("/")
def index():

    conn = get_db_connection()

    try:
        events = conn.execute("""
            SELECT *
            FROM events
            ORDER BY date ASC
            LIMIT 3
        """).fetchall()

    finally:
        conn.close()

    return render_template("index.html", events=events)


# =====================================================
# USER REGISTRATION
# =====================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        conn = get_db_connection()

        try:

            existing_user = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if existing_user:
                flash(
                    "An account with this email already exists.",
                    "warning"
                )
                return redirect(url_for("register"))

            hashed_password = generate_password_hash(password)

            conn.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, 'user')
            """, (name, email, hashed_password))

            conn.commit()

            flash(
                "Account created successfully. Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except Exception:

            conn.rollback()

            app.logger.exception("User registration error")

            flash(
                "Unable to create account. Please try again.",
                "danger"
            )

        finally:
            conn.close()

    return render_template("register.html")


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash(
                "Please enter your email and password.",
                "danger"
            )
            return redirect(url_for("login"))

        conn = get_db_connection()

        try:

            user = conn.execute("""
                SELECT *
                FROM users
                WHERE email = ?
            """, (email,)).fetchone()

            if user:

                valid, needs_upgrade = verify_password(
                    user["password"],
                    password
                )

                if valid:

                    # Upgrade an old plaintext password
                    if needs_upgrade:

                        hashed_password = generate_password_hash(
                            password
                        )

                        conn.execute("""
                            UPDATE users
                            SET password = ?
                            WHERE id = ?
                        """, (hashed_password, user["id"]))

                        conn.commit()

                    # Clear old session data before login
                    session.clear()
                    session.permanent = True

                    session["user_id"] = user["id"]
                    session["user_name"] = user["name"]
                    session["role"] = user["role"]

                    if user["role"] == "admin":
                        return redirect(url_for("admin"))

                    return redirect(url_for("dashboard"))

            flash("Invalid email or password.", "danger")

        finally:
            conn.close()

    return render_template("login.html")


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout", methods=["GET", "POST"])
def logout():

    session.clear()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(url_for("index"))


# =====================================================
# USER DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

        total_registrations = conn.execute("""
            SELECT COUNT(*) AS count
            FROM registrations
            WHERE user_id = ?
            AND status = 'Registered'
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

    finally:
        conn.close()

    return render_template(
        "dashboard.html",
        total_registrations=total_registrations,
        upcoming_events=upcoming_events
    )


# =====================================================
# VIEW ALL EVENTS
# =====================================================

@app.route("/events")
def events():

    conn = get_db_connection()

    try:

        events = conn.execute("""
            SELECT *
            FROM events
            ORDER BY date ASC
        """).fetchall()

    finally:
        conn.close()

    return render_template("events.html", events=events)


# =====================================================
# EVENT DETAILS
# =====================================================

@app.route("/event/<int:event_id>")
def event_details(event_id):

    conn = get_db_connection()

    try:

        event = conn.execute("""
            SELECT *
            FROM events
            WHERE id = ?
        """, (event_id,)).fetchone()

    finally:
        conn.close()

    if event is None:
        flash("Event not found.", "danger")
        return redirect(url_for("events"))

    return render_template("event-details.html", event=event)


# =====================================================
# REGISTER FOR EVENT
# =====================================================

@app.route("/register-event/<int:event_id>", methods=["POST"])
@login_required
def register_event(event_id):

    if session.get("role") == "admin":
        flash(
            "Administrators cannot register for events.",
            "warning"
        )
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

        # Prevent two users from reserving the same last seat
        conn.execute("BEGIN IMMEDIATE")

        event = conn.execute("""
            SELECT *
            FROM events
            WHERE id = ?
        """, (event_id,)).fetchone()

        if event is None:
            flash("Event not found.", "danger")
            return redirect(url_for("events"))

        existing_registration = conn.execute("""
            SELECT *
            FROM registrations
            WHERE user_id = ?
            AND event_id = ?
        """, (
            session["user_id"],
            event_id
        )).fetchone()

        if (
            existing_registration
            and existing_registration["status"] == "Registered"
        ):

            flash(
                "You are already registered for this event.",
                "warning"
            )

            return redirect(
                url_for("event_details", event_id=event_id)
            )

        # Atomically reserve one seat
        seat_update = conn.execute("""
            UPDATE events
            SET available_seats = available_seats - 1
            WHERE id = ?
            AND available_seats > 0
        """, (event_id,))

        if seat_update.rowcount == 0:

            flash("Sorry, this event is full.", "danger")

            return redirect(
                url_for("event_details", event_id=event_id)
            )

        registration_date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if existing_registration:

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

            conn.execute("""
                INSERT INTO registrations (
                    user_id,
                    event_id,
                    registration_date,
                    status
                )
                VALUES (?, ?, ?, 'Registered')
            """, (
                session["user_id"],
                event_id,
                registration_date
            ))

        conn.commit()

        flash(
            "Successfully registered for the event!",
            "success"
        )

        return redirect(url_for("my_events"))

    except Exception:

        conn.rollback()

        app.logger.exception("Event registration error")

        flash(
            "Something went wrong. Please try again.",
            "danger"
        )

        return redirect(url_for("events"))

    finally:
        conn.close()


# =====================================================
# MY REGISTRATIONS
# =====================================================

@app.route("/my-events")
@login_required
def my_events():

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

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

    finally:
        conn.close()

    return render_template(
        "my-events.html",
        registrations=registrations
    )


# =====================================================
# CANCEL REGISTRATION
# =====================================================

@app.route("/cancel/<int:registration_id>", methods=["POST"])
@login_required
def cancel_registration(registration_id):

    if session.get("role") == "admin":
        flash(
            "Administrators cannot cancel user registrations.",
            "warning"
        )
        return redirect(url_for("admin"))

    conn = get_db_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

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

        conn.execute("""
            UPDATE registrations
            SET status = 'Cancelled'
            WHERE id = ?
        """, (registration_id,))

        conn.execute("""
            UPDATE events
            SET available_seats = available_seats + 1
            WHERE id = ?
        """, (registration["event_id"],))

        conn.commit()

        flash(
            "Registration cancelled successfully.",
            "success"
        )

    except Exception:

        conn.rollback()

        app.logger.exception("Registration cancellation error")

        flash(
            "Unable to cancel registration.",
            "danger"
        )

    finally:
        conn.close()

    return redirect(url_for("my_events"))


# =====================================================
# ADMIN DASHBOARD
# =====================================================

@app.route("/admin")
@admin_required
def admin():

    conn = get_db_connection()

    try:

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

    finally:
        conn.close()

    return render_template(
        "admin.html",
        total_events=total_events,
        total_users=total_users,
        total_registrations=total_registrations,
        events=events
    )


# =====================================================
# ADD EVENT
# =====================================================

@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def add_event():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        date = request.form.get("date", "").strip()
        time = request.form.get("time", "").strip()
        venue = request.form.get("venue", "").strip()
        category = request.form.get("category", "").strip()
        capacity = request.form.get("capacity", "").strip()

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

            flash(
                "Capacity must be a positive number.",
                "danger"
            )

            return redirect(url_for("add_event"))

        conn = get_db_connection()

        try:

            conn.execute("""
                INSERT INTO events (
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

            flash("Event added successfully.", "success")

            return redirect(url_for("admin"))

        except Exception:

            conn.rollback()

            app.logger.exception("Add event error")

            flash("Unable to add event.", "danger")

        finally:
            conn.close()

    return render_template("add-event.html")


# =====================================================
# EDIT EVENT
# =====================================================

@app.route("/admin/edit/<int:event_id>", methods=["GET", "POST"])
@admin_required
def edit_event(event_id):

    conn = get_db_connection()

    try:

        event = conn.execute("""
            SELECT *
            FROM events
            WHERE id = ?
        """, (event_id,)).fetchone()

        if event is None:
            flash("Event not found.", "danger")
            return redirect(url_for("admin"))

        if request.method == "POST":

            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            date = request.form.get("date", "").strip()
            time = request.form.get("time", "").strip()
            venue = request.form.get("venue", "").strip()
            category = request.form.get("category", "").strip()
            capacity = request.form.get("capacity", "").strip()

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

                return render_template(
                    "edit-event.html",
                    event=event
                )

            try:

                capacity = int(capacity)

                if capacity <= 0:
                    raise ValueError

            except ValueError:

                flash(
                    "Capacity must be a valid positive number.",
                    "danger"
                )

                return render_template(
                    "edit-event.html",
                    event=event
                )

            registered_count = conn.execute("""
                SELECT COUNT(*) AS count
                FROM registrations
                WHERE event_id = ?
                AND status = 'Registered'
            """, (event_id,)).fetchone()["count"]

            if capacity < registered_count:

                flash(
                    f"Capacity cannot be less than the "
                    f"{registered_count} existing registrations.",
                    "danger"
                )

                return render_template(
                    "edit-event.html",
                    event=event
                )

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

            flash(
                "Event details updated successfully!",
                "success"
            )

            return redirect(url_for("admin"))

    except Exception:

        conn.rollback()

        app.logger.exception("Edit event error")

        flash("Unable to update event.", "danger")

        return redirect(url_for("admin"))

    finally:
        conn.close()

    return render_template(
        "edit-event.html",
        event=event
    )


# =====================================================
# DELETE EVENT
# =====================================================

@app.route("/admin/delete/<int:event_id>", methods=["POST"])
@admin_required
def delete_event(event_id):

    conn = get_db_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        event = conn.execute("""
            SELECT id
            FROM events
            WHERE id = ?
        """, (event_id,)).fetchone()

        if event is None:
            flash("Event not found.", "danger")
            return redirect(url_for("admin"))

        conn.execute("""
            DELETE FROM registrations
            WHERE event_id = ?
        """, (event_id,))

        conn.execute("""
            DELETE FROM events
            WHERE id = ?
        """, (event_id,))

        conn.commit()

        flash("Event deleted successfully.", "success")

    except Exception:

        conn.rollback()

        app.logger.exception("Delete event error")

        flash("Unable to delete event.", "danger")

    finally:
        conn.close()

    return redirect(url_for("admin"))


# =====================================================
# VIEW ALL REGISTRATIONS
# =====================================================

@app.route("/admin/registrations")
@admin_required
def admin_registrations():

    conn = get_db_connection()

    try:

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

    finally:
        conn.close()

    return render_template(
        "registrations.html",
        registrations=registrations
    )


# =====================================================
# ERROR HANDLERS
# =====================================================

@app.errorhandler(404)
def page_not_found(error):
    return render_template("index.html", events=[]), 404


@app.errorhandler(500)
def internal_server_error(error):

    app.logger.exception("Internal server error")

    return (
        "Something went wrong. Please try again later.",
        500
    )


# =====================================================
# APPLICATION ENTRY POINT
# =====================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
