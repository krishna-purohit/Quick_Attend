from flask import Flask, request, jsonify
import mysql.connector

import qrcode
import io, base64
from datetime import datetime
import io, base64, json, datetime as dt

from flask_cors import CORS

app = Flask(__name__)

# Enable CORS for specific origins
CORS(app, origins=["http://127.0.0.1:5500", "http://localhost:5500"])

# Or for a specific route
# CORS(app, resources={r"/api/*": {"origins": "http://127.0.0.1:5500"}})
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
            # It's a username, fetch the actual teacher ID
            cursor.execute("SELECT teacher_id FROM teacher WHERE username = %s", (teacher_input,))
            teacher_result = cursor.fetchone()
            
            if not teacher_result:
                cursor.close()
                db.close()
                return jsonify(ok=False, error="Teacher not found"), 404
            
            actual_teacher_id = teacher_result[0]
        else:
            # It's already an ID (integer or numeric string)
            actual_teacher_id = int(teacher_input)

        # Insert into database with actual integer teacher ID
        cursor.execute("""
        INSERT INTO qrsession (teacher_id, subject, class, stream, semester, date, time)
        VALUES (%s, %s, %s, %s, %s, CURDATE(), CURTIME())
        """, (
            actual_teacher_id,
            data["subject"],
            data["class"],
            data["stream"],
            data["semester"]
        ))
        
        db.commit()
        new_session_id = cursor.lastrowid
        cursor.close()
        db.close()

        # Create payload with the actual session_id from database
        payload = {
            "type": "attendance",
            "session_id": new_session_id,
            "teacher_id": actual_teacher_id,
            "class": data["class"],
            "stream": data["stream"],
            "semester": data["semester"],
            "subject": data["subject"],
            "date": dt.date.today().isoformat(),
            "time": dt.datetime.now().strftime("%H:%M:%S")
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
        return jsonify({"error": "Missing roll_number or session_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ roll_number → student_id
        cursor.execute("SELECT student_id FROM student WHERE roll_number=%s", (roll_number,))
        student = cursor.fetchone()
        if not student:
            return jsonify({"error": "Invalid roll number"}), 400

        student_id = student["student_id"]

        # 2️⃣ check if already marked
        cursor.execute(
            "SELECT 1 FROM attendance WHERE student_id=%s AND session_id=%s",
            (student_id, session_id)
        )
        if cursor.fetchone():
            return jsonify({"ok": False, "message": "Attendance already marked"}), 400

        # 3️⃣ insert attendance
        cursor.execute(
            "INSERT INTO attendance (student_id, session_id, status) VALUES (%s, %s, %s)",
            (student_id, session_id, status)
        )
        conn.commit()

        # ✅ return student_id instead of roll_number
        return jsonify({
            "ok": True,
            "student_id": student_id,
            "message": f"Attendance marked for student_id {student_id}"
        })

    except Exception as e:
        conn.rollback()
        print("Error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

#-------------
# view today for student
#--------------
@app.post("/api/student/today-attendance")
def student_today_attendance():
    data = request.get_json()
    student_id = data.get("student_id")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        today = datetime.today().date()

        # 1️⃣ Student ka stream, semester, class nikaalo
        cursor.execute("SELECT class,stream, semester FROM student WHERE student_id=%s", (student_id,))
        student = cursor.fetchone()
        if not student:
            return jsonify({"error": "Student not found"}), 404

        stream = student["stream"]
        semester = student["semester"]
        class_name = student["class"]

        # 2️⃣ Filtered query
        cursor.execute("""
    SELECT q.session_id, q.subject, q.date,
           IF(a.attendance_id IS NULL, 'Present', a.status) AS status
    FROM qrsession q
    LEFT JOIN attendance a 
      ON q.session_id = a.session_id AND a.student_id = %s
    WHERE q.date = %s 
      AND LOWER(REPLACE(q.stream, ' ', '')) = LOWER(REPLACE(%s, ' ', ''))
      AND q.semester = %s 
      AND q.class = %s
""", (student_id, today, stream, semester, class_name))
       
        records = cursor.fetchall()

        cursor.close()
        conn.close()
        return jsonify(records)

    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({"error": str(e)}), 500

# ------------- 
# Summary for Student 
# -------------------
@app.route("/api/student/<roll>/monthly", methods=["GET"])
def student_monthly_report(roll):
    # month format YYYY-MM
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
            r["percentage"] = round((att/total)*100) if total else 0

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

# ----------------------------
# Run Flask
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
