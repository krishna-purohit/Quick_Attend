from flask import Flask, request, jsonify
import mysql.connector

import qrcode
import io, base64
from datetime import datetime, timedelta
import io, base64, json, datetime as dt

from flask_cors import CORS

app = Flask(__name__)

# Enable CORS for specific origins
CORS(app)

# ✅ MySQL connection function
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="sql_24",   # tumhara password
        database="attendance_system"
    )

# ----------------------------
# Student Login API
# ----------------------------
@app.post("/api/student/login")
def student_login():
    data = request.json
    roll = data.get("roll_number")
    password = data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM student WHERE roll_number=%s AND password=%s", (roll, password))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    if student:
        return jsonify({"ok": True, "role": "student", "data": student})
    else:
        return jsonify({"ok": False, "message": "Invalid Student login!"}), 401

# ----------------------------
# Teacher Login API
# ----------------------------
@app.post("/api/teacher/login")
def teacher_login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM teacher WHERE username=%s AND password=%s", (username, password))
    teacher = cursor.fetchone()
    cursor.close()
    conn.close()

    if teacher:
        return jsonify({"ok": True, "role": "teacher", "data": teacher})
    else:
        return jsonify({"ok": False, "message": "Invalid Teacher login!"}), 401

# ----------------------------
# Generate QR API
# ----------------------------
def make_qr_png_bytes(payload):
    
    import json
    qr_data = json.dumps(payload)
    
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    return img_buffer.getvalue()

@app.route("/api/generate_qr", methods=["POST"])
def generate_qr():
    data = request.get_json(silent=True) or {}

    required = ["class", "stream", "semester", "subject", "teacher_id"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify(ok=False, error=f"Missing fields: {', '.join(missing)}"), 400

    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        # Convert username to actual teacher ID
        teacher_input = data["teacher_id"]
        if isinstance(teacher_input, str) and not teacher_input.isdigit():
            cursor.execute("SELECT teacher_id FROM teacher WHERE username = %s", (teacher_input,))
            teacher_result = cursor.fetchone()
            if not teacher_result:
                cursor.close()
                db.close()
                return jsonify(ok=False, error="Teacher not found"), 404
            actual_teacher_id = teacher_result[0]
        else:
            actual_teacher_id = int(teacher_input)

        # Set expiration time (e.g., 15 minutes from now)
        expire_minutes = 15
        expires_at = datetime.now() + timedelta(minutes=expire_minutes)

        # Insert into database with actual integer teacher ID and expires_at
        cursor.execute("""
        INSERT INTO qrsession (teacher_id, subject, class, stream, semester, date, time, expires_at)
        VALUES (%s, %s, %s, %s, %s, CURDATE(), CURTIME(), %s)
        """, (
            actual_teacher_id,
            data["subject"],
            data["class"],
            data["stream"],
            data["semester"],
            expires_at.strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        db.commit()
        new_session_id = cursor.lastrowid
        cursor.close()
        db.close()

        # Create payload with the actual session_id and expires_at
        payload = {
            "type": "attendance",
            "session_id": new_session_id,
            "teacher_id": actual_teacher_id,
            "class": data["class"],
            "stream": data["stream"],
            "semester": data["semester"],
            "subject": data["subject"],
            "date": dt.date.today().isoformat(),
            "time": dt.datetime.now().strftime("%H:%M:%S"),
            "expires_at": expires_at.isoformat()
        }

        # QR image base64
        png_bytes = make_qr_png_bytes(payload)
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"

        return jsonify(
            ok=True, 
            qr_data_url=data_url, 
            payload=payload, 
            session_id=new_session_id
        )

    except Exception as e:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()
        return jsonify(ok=False, error=f"Server error: {str(e)}"), 500
# ----------------------------
# mark attendance for student  
# ----------------------------
@app.route('/api/attendance/mark', methods=['POST'])
def mark_attendance():
    data = request.get_json()
    roll_number = data.get("roll_number")
    session_id = data.get("session_id")
    status = data.get("status", "Present")

    if not roll_number or not session_id:
        return jsonify({"ok": False, "error": "Missing roll_number or session_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1) get student_id from roll
        cursor.execute("SELECT student_id FROM student WHERE roll_number=%s", (roll_number,))
        student = cursor.fetchone()
        if not student:
            return jsonify({"ok": False, "error": "Invalid roll number"}), 400
        student_id = student["student_id"]

        # 2) get session details and check expiry
        cursor.execute("SELECT date, time, expires_at FROM qrsession WHERE session_id=%s", (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return jsonify({"ok": False, "expired": True, "message": "Invalid or expired QR session"}), 400

        # Convert expires_at safely to datetime
        expires_at = session_row.get("expires_at")
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
            except:
                expires_at = datetime.now()  # fallback → expired
        elif expires_at is None:
            expires_at = datetime.now()  # fallback → expired

        # Check expiry
        if datetime.now() > expires_at:
            cursor.close()
            conn.close()
            return jsonify({"ok": False, "expired": True, "message": "QR code has expired"}), 400

        # 3) check if already marked
        cursor.execute(
            "SELECT attendance_id, status FROM attendance WHERE student_id=%s AND session_id=%s",
            (student_id, session_id)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.close()
            conn.close()
            return jsonify({
                "ok": True,
                "already_marked": True,
                "student_id": student_id,
                "attendance_id": existing.get("attendance_id"),
                "status": existing.get("status"),
                "message": "Attendance already marked for this session"
            }), 200

        # 4) insert attendance
        cursor.execute(
            "INSERT INTO attendance (student_id, session_id, status) VALUES (%s, %s, %s)",
            (student_id, session_id, status)
        )
        conn.commit()
        attendance_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return jsonify({
            "ok": True,
            "already_marked": False,
            "student_id": student_id,
            "attendance_id": attendance_id,
            "message": "Attendance marked successfully"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error in mark_attendance:", str(e))
        try: cursor.close()
        except: pass
        try: conn.close()
        except: pass
        # frontend safe error
        return jsonify({"ok": False, "error": "Server error while marking attendance. Please try again later."}), 500

#-------------
# update attendace by teacher
#--------------
@app.route("/api/update_attendance", methods=["POST"])
def update_attendance():
    data = request.get_json()
    roll_no = data.get("roll_no")
    date = data.get("date")
    subject = data.get("subject")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1. find current status
    cur.execute("""
        SELECT a.status, a.attendance_id
        FROM attendance a
        JOIN student s ON s.student_id = a.student_id
        JOIN qrsession q ON a.session_id = q.session_id
        WHERE s.roll_number=%s AND q.date=%s AND q.subject=%s
    """, (roll_no, date, subject))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"status": "error", "message": "Attendance record not found"}), 404

    current_status = row["status"]
    new_status = "Absent" if current_status in ("P","Present") else "Present"

    # 2. update status
    cur.execute("UPDATE attendance SET status=%s WHERE attendance_id=%s", (new_status, row["attendance_id"]))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "success", "message": f"Updated to {new_status}"})

# ----------------------------
# TS -Student Overall Attendance Summary (by roll number)
# ----------------------------
@app.route("/api/student/<roll>/summary", methods=["GET"])
def student_summary(roll):
    """
    Returns subject-wise attendance summary for a student by roll number
    """
    month = request.args.get("month")
    if not month:
        month = dt.date.today().strftime("%Y-%m")

    query = """
        SELECT 
            q.subject AS subject,
            COUNT(*) AS total_classes,
            SUM(CASE WHEN a.status IN ('P','Present') THEN 1 ELSE 0 END) AS attended
        FROM qrsession q
        LEFT JOIN attendance a 
            ON q.session_id = a.session_id
        LEFT JOIN student s
            ON a.student_id = s.student_id
        WHERE s.roll_number = %s
          AND DATE_FORMAT(q.date, '%%Y-%%m') = %s
        GROUP BY q.subject
        ORDER BY q.subject;
    """

    try:
        cnx = get_db_connection()
        cur = cnx.cursor(dictionary=True)
        cur.execute(query, (roll, month))
        rows = cur.fetchall()

        for r in rows:
            total = int(r["total_classes"]) or 0
            att = int(r["attended"]) or 0
            r["percentage"] = round((att / total) * 100, 2) if total else 0

        cur.close()
        cnx.close()

        return jsonify({
            "roll": roll,
            "month": month,
            "records": rows
        }), 200

    except Exception as e:
        print("ERR:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Dropdown APIs ----------
@app.route("/api/get_classes")
def get_classes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT class_name FROM classes;")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

@app.route("/api/get_streams")
def get_streams():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stream_name FROM streams;")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

@app.route("/api/get_semesters")
def get_semesters():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT semester_name FROM semesters;")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

@app.route("/api/get_subjects")
def get_subjects():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT subject_name FROM subjects;")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

# ---------- Attendance API ----------
@app.route("/api/get_attendance")
def get_attendance():
    class_name = request.args.get("class")
    stream = request.args.get("stream")
    semester = request.args.get("semester")
    subject = request.args.get("subject")  # optional
    date = request.args.get("date")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # optional subject filter
    subject_filter = ""
    params = []

    # Query
    query = f"""
        SELECT s.roll_number, s.name, COALESCE(a.status,'Absent') AS status
        FROM student s
        JOIN qrsession q
            ON LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(q.class,' ','')))
            AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(q.stream,' ','')))
            AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(q.semester,'Sem ','')))
            AND DATE(q.date) = %s
        LEFT JOIN attendance a
            ON a.student_id = s.student_id AND a.session_id = q.session_id
        WHERE LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(%s,' ','')))
          AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(%s,' ','')))
          AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(%s,'Sem ','')))
        ORDER BY s.roll_number;
    """

    # Params order: subject(if exists), date, class, stream, semester
    params = params + [date, class_name, stream, semester]

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = [{"roll_no": r["roll_number"], "name": r["name"], "status": r["status"]} for r in rows]

    return jsonify(data)

# ----------------------------
# Teacher Summary API
# ----------------------------
@app.route("/api/teacher/summary")
def teacher_summary():
    from datetime import date as dt
    # -----------------------------
    # Get query params
    # -----------------------------
    class_name = request.args.get("class")
    stream = request.args.get("stream")
    semester = request.args.get("semester")
    subject = request.args.get("subject")  # optional
    date_param = datetime.now()

    # -----------------------------
    # DB connection
    # -----------------------------
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # -----------------------------
    # Prepare subject filter
    # -----------------------------
    subject_filter = ""
    params = []

    if subject:
        subject_filter = "AND LOWER(TRIM(q.subject)) = LOWER(TRIM(%s))"
        params.append(subject)

    # Add date, class, stream, semester params
    params = [date_param] + params + [class_name, stream, semester]

    # -----------------------------
    # SQL query
    # -----------------------------
    query = f"""
    SELECT 
        s.roll_number,
        s.name,
        COUNT(q.session_id) AS total_classes,
        SUM(CASE WHEN a.status IN ('P','Present') THEN 1 ELSE 0 END) AS attended
    FROM student s
    JOIN qrsession q
        ON LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(q.class,' ','')))
        AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(q.stream,' ','')))
        AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(q.semester,'Sem ','')))
        AND DATE(q.date) <= %s
        {subject_filter}
    LEFT JOIN attendance a
        ON a.student_id = s.student_id
        AND a.session_id = q.session_id
    WHERE LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(%s,' ','')))
      AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(%s,' ','')))
      AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(%s,'Sem ','')))
    GROUP BY s.student_id, s.roll_number, s.name
    ORDER BY s.roll_number;
    """

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # -----------------------------
    # Format data
    # -----------------------------
    data = []
    for r in rows:
        total = r["total_classes"] or 0
        attended = r["attended"] or 0
        percentage = round((attended / total) * 100, 2) if total > 0 else 0.0
        data.append({
            "roll_no": r["roll_number"],
            "name": r["name"],
            "total_classes": total,
            "attended": attended,
            "attendance_percentage": percentage
        })

    return jsonify(data)

#---------------------
# Student - Date wise Attendance (already present, fixed)
#---------------------
@app.route("/api/student/<roll>/attendance", methods=["GET"])
def student_attendance_by_date(roll):
    """
    Returns attendance records of a student by roll number for a given date
    Default: today
    """
    date = request.args.get("date")
    if not date:
        date = dt.date.today().strftime("%Y-%m-%d")

    query = """
        SELECT 
            q.subject AS subject,
            COALESCE(a.status, 'Absent') AS status
        FROM qrsession q
        JOIN student s
            ON s.roll_number = %s
            AND s.class = q.class
            AND s.stream = q.stream
            AND s.semester = q.semester
        LEFT JOIN attendance a 
            ON a.session_id = q.session_id
            AND a.student_id = s.student_id
        WHERE q.date = %s
        ORDER BY q.subject;
    """

    try:
        cnx = get_db_connection()
        cur = cnx.cursor(dictionary=True)
        cur.execute(query, (roll, date))
        rows = cur.fetchall()
        cur.close()
        cnx.close()

        return jsonify({
            "roll": roll,
            "date": date,
            "records": rows
        }), 200

    except Exception as e:
        print("ERR:", e)
        return jsonify({"error": str(e)}), 500
# ---------- Student: Monthly Attendance ----------
@app.route("/api/student/<roll>/monthly", methods=["GET"])
def student_monthly_report(roll):
    """
    Returns subject-wise attendance for a student for all months (or specific month if passed)
    """
    month = request.args.get("month")  # optional, YYYY-MM

    try:
        cnx = get_db_connection()
        cur = cnx.cursor(dictionary=True)

        if month:
            # if month is passed, use only that month
            query = """
            SELECT 
                q.subject AS subject,
                COUNT(q.session_id) AS total_classes,
                SUM(CASE WHEN a.attendance_id IS NOT NULL AND a.status IN ('P','Present') THEN 1 ELSE 0 END) AS attended
            FROM qrsession q
            JOIN student s
                ON s.roll_number = %s
                AND LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(q.class,' ','')))
                AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(q.stream,' ','')))
                AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(q.semester,'Sem ','')))
            LEFT JOIN attendance a
                ON a.session_id = q.session_id
                AND a.student_id = s.student_id
            WHERE DATE_FORMAT(q.date, '%%Y-%%m') = %s
            GROUP BY q.subject
            ORDER BY q.subject;
            """
            cur.execute(query, (roll, month))
            month_label = month
        else:
            # No month passed → get all sessions for the student
            query = """
            SELECT 
                q.subject AS subject,
                COUNT(q.session_id) AS total_classes,
                SUM(CASE WHEN a.attendance_id IS NOT NULL AND a.status IN ('P','Present') THEN 1 ELSE 0 END) AS attended
            FROM qrsession q
            JOIN student s
                ON s.roll_number = %s
                AND LOWER(TRIM(REPLACE(s.class,' ',''))) = LOWER(TRIM(REPLACE(q.class,' ','')))
                AND LOWER(TRIM(REPLACE(s.stream,' ',''))) = LOWER(TRIM(REPLACE(q.stream,' ','')))
                AND LOWER(TRIM(REPLACE(s.semester,'Sem ',''))) = LOWER(TRIM(REPLACE(q.semester,'Sem ','')))
            LEFT JOIN attendance a
                ON a.session_id = q.session_id
                AND a.student_id = s.student_id
            GROUP BY q.subject
            ORDER BY q.subject;
            """
            cur.execute(query, (roll,))
            month_label = "all_sessions"

        rows = cur.fetchall()
        cur.close()
        cnx.close()

        records = []
        for r in rows:
            total = int(r.get("total_classes") or 0)
            attended = int(r.get("attended") or 0)
            percentage = round((attended / total) * 100, 2) if total > 0 else 0.0
            records.append({
                "subject": r.get("subject"),
                "total_classes": total,
                "attended": attended,
                "percentage": percentage
            })

        return jsonify({
            "roll": roll,
            "month": month_label,
            "records": records
        }), 200

    except Exception as e:
        print("ERR in student_monthly_report:", str(e))
        try:
            cur.close()
            cnx.close()
        except:
            pass
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Run Flask
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
