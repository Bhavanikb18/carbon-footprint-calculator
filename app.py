from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import json
import os
from functools import wraps

BASE_DB = "users.db"

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "replace_this_with_strong_secret"

from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

# ---------------- MAIL CONFIG ---------------- #
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='banashreeumesh@gmail@gmail.com',  # replace with your email
    MAIL_PASSWORD='ggkp qlgu ahkr tjlt'       # replace with app password
)

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)


# ------------------ LOGIN REQUIRED DECORATOR ------------------ #
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ------------------ DB CONNECTION ------------------ #
def get_db():
    need_create = not os.path.exists(BASE_DB)
    conn = sqlite3.connect(BASE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if need_create:
        sql = open("create_db.py").read()
        cur.executescript(sql)
        conn.commit()
    return conn

# ------------------ HOME ------------------ #
@app.route("/")
def home():
    return redirect("/login")

# ------------------ LOGIN ------------------ #
@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, full_name, username, email
            FROM users 
            WHERE (username=? OR email=?) AND password=?
        """, (identifier, identifier, password))
        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect("/dashboard")
        else:
            msg = "Invalid username/email or password."
    return render_template("login.html", msg=msg)

# ------------------ REGISTER ------------------ #
@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username=? OR email=?", (username, email))
        if cur.fetchone():
            msg = "Username or email already exists."
            conn.close()
            return render_template("register.html", msg=msg)

        cur.execute("""
            INSERT INTO users (full_name, username, email, password)
            VALUES (?, ?, ?, ?)
        """, (full_name, username, email, password))
        conn.commit()
        conn.close()
        return redirect("/login")
    return render_template("register.html", msg=msg)

# ------------------ LOGOUT ------------------ #
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------ DASHBOARD ------------------ #
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT total_kg, breakdown_json, recommendations
        FROM carbon_results
        WHERE user_id=?
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    last_result = cur.fetchone()
    conn.close()
    return render_template(
        "dashboard.html",
        username=session.get("username"),
        last_result=last_result
    )

# ------------------ CALCULATOR PAGE ------------------ #
@app.route("/calculator")
@login_required
def calculator_page():
    return render_template("calculator.html")

# ------------------ CALCULATE ------------------ #
@app.route("/calculate", methods=["POST"])
@login_required
def calculate():
    data = request.get_json() or {}

    # ------- Travel -------
    bike = float(data.get("bike") or 0)
    car = float(data.get("car") or 0)
    bus = float(data.get("bus") or 0)
    train = float(data.get("train") or 0)
    travel = bike * 0.12 + car * 0.21 + bus * 0.05 + train * 0.06

    # ------- Electricity -------
    mode = data.get("elec_mode")
    if mode == "units":
        units = float(data.get("units") or 0)
        electricity = units * 0.82
    else:
        lights = int(data.get("lights") or 0)
        fans = int(data.get("fans") or 0)
        fridge = int(data.get("fridge") or 0)
        ac = int(data.get("ac") or 0)
        wm = int(data.get("washing_machine") or 0)
        tv = int(data.get("tv") or 0)
        electricity = lights * 0.10 + fans * 0.15 + fridge * 0.6 + ac * 1.5 + wm * 0.5 + tv * 0.2

    # ------- Food -------
    food_map = {"veg": 1.2, "1-2": 1.8, "2-3": 2.3, "nonveg": 3.5}
    food = food_map.get(data.get("food"), 0)

    # ------- Waste -------
    waste_map = {"small": 0.2, "medium": 0.5, "high": 1.0}
    waste = waste_map.get(data.get("waste_category"), 0)
    habit = data.get("waste_habit")
    if habit == "recycle":
        waste *= 0.7
    elif habit == "compost":
        waste *= 0.5

    total = round(travel + electricity + food + waste, 2)
    breakdown = {
        "travel": round(travel, 3),
        "electricity": round(electricity, 3),
        "food": round(food, 3),
        "waste": round(waste, 3)
    }

    # ------- Recommendations -------
    recommendations = []

    # Travel
    if any([bike, car, bus, train]):
        if travel < 2:
            recommendations.append("🚗 Travel: Excellent low travel emissions.")
        elif travel < 8:
            recommendations.append("🚗 Travel: Use public transport or carpool more.")
        elif travel < 15:
            recommendations.append("🚗 Travel: Replace short car trips with cycling.")
        else:
            recommendations.append("🚗 Travel: High travel emissions — reduce solo car use.")

    # Electricity
    if (mode == "units" and units > 0) or \
       (mode == "appliances" and any([lights, fans, fridge, ac, wm, tv])):
        if electricity < 1:
            recommendations.append("⚡ Electricity: Very low electricity usage — great!")
        elif electricity < 4:
            led_status = data.get("led_bulbs", "no").lower()
            if led_status == "yes":
                recommendations.append("⚡ Electricity: Your LEDs are great! Keep it up.")
            else:
                recommendations.append("⚡ Electricity: Switch to LED bulbs to save energy.")
        elif electricity < 8:
            recommendations.append("⚡ Electricity: Reduce AC/fan usage.")
        else:
            recommendations.append("⚡ Electricity: Very high usage — consider solar energy.")

    # Food
    if data.get("food") and data.get("food") != "none":
        if food < 1.5:
            recommendations.append("🍽 Food: Vegetarian diet reduces emissions.")
        elif food < 2.5:
            recommendations.append("🍽 Food: Reduce non-veg meals by 1/day.")
        elif food < 3:
            recommendations.append("🍽 Food: Prefer plant-based meals.")
        else:
            recommendations.append("🍽 Food: Reduce red meat to lower CO₂.")

    # Waste
    if data.get("waste_category") and data.get("waste_category") != "none":
        if waste < 0.3:
            recommendations.append("🗑 Waste: Low waste — great job!")
        elif waste < 0.6:
            recommendations.append("🗑 Waste: Increase recycling.")
        elif waste < 1:
            recommendations.append("🗑 Waste: Start composting kitchen waste.")
        else:
            recommendations.append("🗑 Waste: Reduce disposables and compost waste.")

    rec_text = "<br>".join(recommendations) if recommendations else "No input values provided. Enter values to get recommendations."

    # ------- Save to DB -------
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO carbon_results (user_id, total_kg, breakdown_json, recommendations)
        VALUES (?, ?, ?, ?)
    """, (session["user_id"], total, json.dumps(breakdown), rec_text))
    conn.commit()
    conn.close()

    return jsonify({"total": total, "breakdown": breakdown, "recommendations": rec_text})

# ------------------ HISTORY ------------------ #
@app.route("/history")
@login_required
def history():
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    conn = get_db()
    cur = conn.cursor()
    query = """
        SELECT total_kg, breakdown_json, recommendations, created_at
        FROM carbon_results
        WHERE user_id = ?
    """
    params = [session["user_id"]]

    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date + " 00:00:00")
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date + " 23:59:59")

    query += " ORDER BY created_at ASC"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    dates = [r["created_at"][:10] for r in rows]
    totals = [r["total_kg"] for r in rows]

    return render_template(
        "history.html",
        records=rows,
        username=session.get("username"),
        dates=dates,
        totals=totals
    )

# ------------------ FORGOT PASSWORD ------------------ #
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    msg = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()
        if user:
            token = s.dumps(email, salt='password-reset')
            reset_link = f"http://127.0.0.1:5000/reset-password/{token}"

            # Send email
            try:
                msg_email = Message("Password Reset Request",
                                    sender=app.config['MAIL_USERNAME'],
                                    recipients=[email])
                msg_email.body = f"Hi {user['username']},\n\nClick the link to reset your password:\n{reset_link}\n\nIf you didn't request this, ignore."
                mail.send(msg_email)
                msg = "Password reset link sent! Check your email."
            except Exception as e:
                msg = f"Failed to send email: {e}"
        else:
            msg = "No account found with this email."
    return render_template("forgot_password.html", msg=msg)

#-------------------/reset-password/<token>--------------#
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = s.loads(token, salt='password-reset', max_age=3600)  # 1 hour validity
    except:
        return "The reset link is invalid or expired."

    msg = ""
    if request.method == "POST":
        new_pass = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=? WHERE email=?", (new_pass, email))
        conn.commit()
        conn.close()
        msg = "Password updated successfully! You can now login."
        return redirect("/login")
    return render_template("reset_password.html", msg=msg)


# ------------------ RUN ------------------ #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
    
