from flask import Flask, request, jsonify, send_file
import os
import sqlite3
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
import time
import hashlib
import hmac
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pdf2image
import pytesseract
from PIL import Image
import io
import base64
import re
import sys
import json

# Add ML modules path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

try:
    from certificate_fraud_detection import CertificateFraudDetector
    from certificate_validator import CertificateValidator
    from unified_validator import UnifiedCertificateValidator
    ML_ENABLED = True
    # Initialize fraud detector
    fraud_detector = CertificateFraudDetector(
        model_path=os.path.join(os.path.dirname(__file__), '..', 'models', 'fraud_detector.pkl')
    )
    # Initialize certificate validator
    certificate_validator = CertificateValidator(
        model_path=os.path.join(os.path.dirname(__file__), '..', 'models', 'certificate_validator.pkl')
    )
    # Initialize unified validator
    unified_validator = UnifiedCertificateValidator(
        models_dir=os.path.join(os.path.dirname(__file__), '..', 'models')
    )
    print("ML Fraud Detection, Certificate Validation, and Unified Validator initialized successfully")
except ImportError as e:
    print(f"ML modules not available: {e}")
    ML_ENABLED = False
    fraud_detector = None
    certificate_validator = None
    unified_validator = None
except Exception as e:
    print(f"Error initializing ML model: {e}")
    ML_ENABLED = False
    fraud_detector = None
    certificate_validator = None
    unified_validator = None

# Ensure we can import from mindvault/modules when running this file directly
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
# Also ensure project root is on sys.path so root-level verify.py is importable
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.verify import verify_certificate  # expects callable verify_certificate(file_path)
from modules.analyze import analyze_certificate  # callable analyze_certificate(file_path)
from modules.integrations.linkedin_client import publish_post as linkedin_publish
from mindvault.modules.analytics.student_analytics import StudentAnalytics
from mindvault.modules.roadmap.roadmap_generator import RoadmapGenerator
try:
    from mindvault.modules.integrations.gemini_client import generate_roadmap as gemini_generate
except Exception:
    gemini_generate = None

try:
    from mindvault.modules.roadmap.openai_roadmap_generator import OpenAIRoadmapGenerator
    OPENAI_ROADMAP_GENERATOR = OpenAIRoadmapGenerator()
except Exception:
    OPENAI_ROADMAP_GENERATOR = None

# Folders and database initialization
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "uploads")
VAULT_FOLDER = os.path.join(os.path.dirname(__file__), "..", "vault")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VAULT_FOLDER, exist_ok=True)

# SQLite DB for storing certificate info
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "master.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password_hash TEXT,
    salt TEXT,
    role TEXT CHECK(role IN ('student','mentor')) NOT NULL DEFAULT 'student',
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT,
    created_at TEXT
)
"""
)
c.execute(
    """
CREATE TABLE IF NOT EXISTS certificates (
    filename TEXT,
    student TEXT,
    verified INTEGER,
    reason TEXT,
    summary TEXT,
    skills TEXT,
    goal TEXT,
    event_date TEXT
)
"""
)
# Skill store
c.execute(
    """
CREATE TABLE IF NOT EXISTS skills (
    student TEXT,
    skill TEXT,
    count INTEGER DEFAULT 0,
    last_seen_at TEXT,
    UNIQUE(student, skill)
)
"""
)
# Goals store
c.execute(
    """
CREATE TABLE IF NOT EXISTS goals (
    student TEXT PRIMARY KEY,
    goal TEXT,
    confirmed INTEGER DEFAULT 0,
    updated_at TEXT
)
"""
)
# Events store
c.execute(
    """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    date TEXT,
    source TEXT,
    created_at TEXT
)
"""
)
# Reminders store
c.execute(
    """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student TEXT,
    event_id INTEGER,
    reminder_date TEXT,
    reminder_time TEXT,
    message TEXT,
    is_sent BOOLEAN DEFAULT FALSE,
    created_at TEXT,
    FOREIGN KEY (event_id) REFERENCES events (id)
)
"""
)
# Attendance store
c.execute(
    """
CREATE TABLE IF NOT EXISTS attendance (
    student TEXT,
    date TEXT,
    status TEXT,
    source_cert TEXT
)
"""
)

# Notifications store (simple)
c.execute(
    """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student TEXT,
    message TEXT,
    created_at TEXT
)
"""
)
conn.commit()

app = Flask(__name__)
app.config['ROADMAPS_FOLDER'] = os.path.join(os.path.dirname(__file__), "..", "roadmaps")
os.makedirs(app.config['ROADMAPS_FOLDER'], exist_ok=True)

# ------------------- Auth helpers -------------------
JWT_SECRET = os.environ.get("JWT_SECRET") or "dev_secret_change_me"

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "docx"}
# MIME types vary by browser/OS; we will not block on MIME alone. Keep for reference if needed.
ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/octet-stream",  # some browsers send generic type
}

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def _b64url_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)

def _sign(payload: dict, exp_seconds: int = 1800) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["exp"] = int(time.time()) + exp_seconds
    h = _b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    b = _b64url(json.dumps(body, separators=(',', ':')).encode('utf-8'))
    msg = f"{h}.{b}".encode('utf-8')
    sig = _b64url(hmac.new(JWT_SECRET.encode('utf-8'), msg, hashlib.sha256).digest())
    return f"{h}.{b}.{sig}"

def _verify(token: str) -> dict:
    try:
        h, b, s = token.split('.')
        msg = f"{h}.{b}".encode('utf-8')
        exp_sig = _b64url(hmac.new(JWT_SECRET.encode('utf-8'), msg, hashlib.sha256).digest())
        if not hmac.compare_digest(exp_sig, s):
            return {}
        payload = json.loads(_b64url_decode(b))
        if int(payload.get("exp", 0)) < int(time.time()):
            return {}
        return payload
    except Exception:
        return {}

def _hash_password(password: str, salt: str = None) -> (str, str):
    if not salt:
        salt = base64.urlsafe_b64encode(os.urandom(16)).decode('utf-8')
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100_000)
    return base64.b64encode(dk).decode('utf-8'), salt

def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    calc, _ = _hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)

def _auth_user() -> dict:
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        token = auth.split(' ', 1)[1].strip()
        return _verify(token) or {}
    return {}

def require_auth(fn):
    def wrapper(*args, **kwargs):
        user = _auth_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        request.user = user  # type: ignore
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

def require_role(role):
    def deco(fn):
        def wrapper(*args, **kwargs):
            user = _auth_user()
            if not user or user.get('role') != role:
                return jsonify({"error": "forbidden"}), 403
            request.user = user  # type: ignore
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ------------------- Auth endpoints -------------------
@app.route('/auth/signup', methods=['POST'])
def auth_signup():
    body = request.get_json(silent=True) or {}
    email = (body.get('email') or '').strip().lower()
    password = body.get('password') or ''
    role = (body.get('role') or 'student').strip().lower()
    if role not in ('student', 'mentor'):
        role = 'student'
    if not email or not password:
        return jsonify({"error": "email_and_password_required"}), 400
    ph, salt = _hash_password(password)
    try:
        c.execute(
            "INSERT INTO users(email, password_hash, salt, role, created_at) VALUES(?,?,?,?,?)",
            (email, ph, salt, role, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "email_exists"}), 409
    token = _sign({"email": email, "role": role})
    return jsonify({"token": token, "user": {"email": email, "role": role}})


@app.route('/auth/login', methods=['POST'])
def auth_login():
    body = request.get_json(silent=True) or {}
    email = (body.get('email') or '').strip().lower()
    password = body.get('password') or ''
    if not email or not password:
        return jsonify({"error": "email_and_password_required"}), 400
    row = c.execute("SELECT id, password_hash, salt, role, failed_attempts, locked_until FROM users WHERE email=?", (email,)).fetchone()
    if not row:
        return jsonify({"error": "invalid_credentials"}), 401
    uid, p_hash, salt, role, failed, locked_until = row
    # lockout check
    if locked_until:
        try:
            if datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
                return jsonify({"error": "account_locked"}), 423
        except Exception:
            pass
    if not _verify_password(password, p_hash, salt):
        failed = (failed or 0) + 1
        locked = None
        if failed >= 3:
            locked = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            failed = 0
        c.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?", (failed, locked, uid))
        conn.commit()
        return jsonify({"error": "invalid_credentials"}), 401
    # reset attempts
    c.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?", (0, None, uid))
    conn.commit()
    token = _sign({"email": email, "role": role})
    return jsonify({"token": token, "user": {"email": email, "role": role}})


@app.route('/auth/me', methods=['GET'])
@require_auth
def auth_me():
    user = getattr(request, 'user', {})  # type: ignore
    return jsonify({"user": user})


# ------------------- Social share endpoints -------------------
@app.route('/share/linkedin', methods=['POST'])
@require_auth
def share_linkedin():
    """Publish a simple post to LinkedIn using env LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN.
    Body: { text: str, link?: str }
    """
    body = request.get_json(silent=True) or {}
    text = (body.get('text') or '').strip()
    link = (body.get('link') or '').strip() or None
    if not text:
        return jsonify({"error": "text_required"}), 400
    
    # Check if LinkedIn credentials are configured
    if not os.environ.get('LINKEDIN_ACCESS_TOKEN') or not os.environ.get('LINKEDIN_AUTHOR_URN'):
        return jsonify({
            "error": "LinkedIn integration not configured",
            "message": "Please set LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN environment variables"
        }), 503
    
    try:
        res = linkedin_publish(text=text, link=link)
        return jsonify({"status": "ok", "response": res})
    except Exception as e:
        # Provide more specific error information
        error_msg = str(e)
        if "LINKEDIN_ACCESS_TOKEN" in error_msg or "LINKEDIN_AUTHOR_URN" in error_msg:
            return jsonify({
                "error": "LinkedIn configuration error",
                "message": "LinkedIn integration is not properly configured"
            }), 503
        elif "HTTP" in error_msg or "urlopen" in error_msg:
            return jsonify({
                "error": "LinkedIn API error",
                "message": "Unable to connect to LinkedIn API. Please check your credentials."
            }), 502
        else:
            return jsonify({"error": "share_failed", "message": error_msg}), 500


def _parse_event_date_from_summary(summary: str) -> str:
    if not summary:
        return ""
    # naive date patterns: YYYY-MM-DD or DD/MM/YYYY or DD-MM-YYYY
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{2}-\d{2}-\d{4})",
    ]
    for p in patterns:
        m = re.search(p, summary)
        if m:
            return m.group(1)
    return ""


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "file_required"}), 400
    
    student = request.form.get('student') or request.form.get('student_id')
    if not student:
        return jsonify({"error": "student_required"}), 400
    
    skip_validation = request.form.get('skip_validation', 'false').lower() == 'true'
    
    student_folder = os.path.join(VAULT_FOLDER, student)
    os.makedirs(student_folder, exist_ok=True)
    
    # Validate file type
    filename = file.filename or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    # Rely primarily on file extension to avoid false negatives from MIME detection
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "invalid_file_type", "allowed": sorted(list(ALLOWED_EXTENSIONS))}), 400

    file_path = os.path.join(student_folder, filename)
    file.save(file_path)

    # Step 0: Unified Certificate Validation (NEW - replaces individual validations)
    unified_validation_result = None
    if ML_ENABLED and unified_validator and not skip_validation:
        try:
            unified_validation_result = unified_validator.validate_certificate_comprehensive(file_path)
            
            # If unified validation fails, delete the file and return error
            if not unified_validation_result['is_valid_certificate']:
                os.remove(file_path)
                return jsonify({
                    "error": "certificate_validation_failed",
                    "unified_validation": unified_validation_result,
                    "message": "The uploaded document did not pass comprehensive certificate validation"
                }), 400
            
            # If low confidence, warn but allow
            if unified_validation_result['overall_confidence'] < 0.6:
                print(f"Warning: Low confidence certificate upload: {filename} - {unified_validation_result['overall_confidence']:.2f}")
        
        except Exception as e:
            print(f"Unified certificate validation error: {e}")
            # Continue with upload even if validation fails
            unified_validation_result = {"error": str(e), "is_valid_certificate": True, "overall_confidence": 0.5}

    # Step 1: Verify certificate
    verification = verify_certificate(file_path)

    # Step 2: Analyze certificate only if verified
    if verification.get("verified"):
        analysis = analyze_certificate(file_path)
    else:
        analysis = {"summary": "", "skills": [], "goal": ""}

    # Step 3: Save results to DB
    c.execute(
        """
        INSERT INTO certificates VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file.filename,
            student,
            int(verification.get("verified", 0)),
            verification.get("reason", ""),
            analysis.get("summary", ""),
            ",".join(analysis.get("skills", [])),
            analysis.get("goal", ""),
            verification.get("event_date", ""),
        ),
    )
    conn.commit()

    # Persist skills (increment counts)
    skills = analysis.get("skills", []) or []
    now_iso = datetime.now(timezone.utc).isoformat()
    for sk in skills:
        try:
            c.execute(
                """
                INSERT INTO skills(student, skill, count, last_seen_at)
                VALUES(?, ?, 1, ?)
                ON CONFLICT(student, skill) DO UPDATE SET
                  count = count + 1,
                  last_seen_at = excluded.last_seen_at
                """,
                (student, sk, now_iso)
            )
        except Exception:
            pass
    conn.commit()

    # Upsert predicted goal (unconfirmed)
    goal_val = analysis.get("goal", "")
    if goal_val:
        c.execute(
            """
            INSERT INTO goals(student, goal, confirmed, updated_at)
            VALUES(?, ?, 0, ?)
            ON CONFLICT(student) DO UPDATE SET
              goal = excluded.goal,
              confirmed = 0,
              updated_at = excluded.updated_at
            """,
            (student, goal_val, now_iso)
        )
        conn.commit()

    # Build response
    response_data = {
        "filename": file.filename,
        "student": student,
        "verified": verification.get("verified", False),
        "verification": verification,
        "analysis": analysis
    }
    
    # Include unified validation results if available
    if unified_validation_result:
        response_data["unified_validation"] = {
            "is_valid_certificate": unified_validation_result["is_valid_certificate"],
            "overall_confidence": unified_validation_result["overall_confidence"],
            "status": unified_validation_result["status"],
            "criteria_summary": unified_validation_result.get("criteria_summary", {}),
            "recommendations": unified_validation_result.get("recommendations", []),
            "warnings": unified_validation_result.get("warnings", [])
        }

    return jsonify(response_data)

    # Attendance auto-sync using event date
    evt_date = verification.get("event_date") or _parse_event_date_from_summary(analysis.get("summary", ""))
    if verification.get("verified") and evt_date:
        try:
            c.execute(
                """
                INSERT INTO attendance(student, date, status, source_cert) VALUES(?, ?, ?, ?)
                """,
                (student, evt_date, "On-Duty", file.filename)
            )
            conn.commit()
        except Exception:
            pass

    return jsonify({
        "verification": verification,
        "analysis": analysis
    })


@app.route("/certificates", methods=["GET"])
@require_auth
def list_certificates():
    student = request.args.get("student")
    if student:
        rows = c.execute("SELECT * FROM certificates WHERE student= ?", (student,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM certificates").fetchall()
    cols = ["filename","student","verified","reason","summary","skills","goal","event_date"]
    data = [dict(zip(cols, r)) for r in rows]
    return jsonify({"certificates": data})


@app.route("/skills/<student>", methods=["GET"])
@require_auth
def get_skills(student):
    rows = c.execute("SELECT skill, count, last_seen_at FROM skills WHERE student=? ORDER BY count DESC", (student,)).fetchall()
    data = [{"skill": r[0], "count": r[1], "last_seen_at": r[2]} for r in rows]
    return jsonify({"student": student, "skills": data})


@app.route("/goal/<student>", methods=["GET"])
@require_auth
def get_goal(student):
    row = c.execute("SELECT goal, confirmed, updated_at FROM goals WHERE student=?", (student,)).fetchone()
    if not row:
        return jsonify({"student": student, "goal": None, "confirmed": 0, "updated_at": None})
    return jsonify({"student": student, "goal": row[0], "confirmed": row[1], "updated_at": row[2]})


@app.route("/goal/<student>", methods=["POST"])
@require_auth
def set_goal(student):
    body = request.get_json(silent=True) or {}
    goal = body.get("goal", "")
    confirmed = int(bool(body.get("confirmed", False)))
    now_iso = datetime.now(timezone.utc).isoformat()
    c.execute(
        """
        INSERT INTO goals(student, goal, confirmed, updated_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(student) DO UPDATE SET
          goal = excluded.goal,
          confirmed = excluded.confirmed,
          updated_at = excluded.updated_at
        """,
        (student, goal, confirmed, now_iso)
    )
    conn.commit()
    return jsonify({"student": student, "goal": goal, "confirmed": confirmed, "updated_at": now_iso})


@app.route("/events", methods=["GET"])
@require_auth
def list_events():
    rows = c.execute("SELECT id, title, date, source, created_at FROM events ORDER BY date ASC").fetchall()
    data = [{"id": r[0], "title": r[1], "date": r[2], "source": r[3], "created_at": r[4]} for r in rows]
    return jsonify(data)


@app.route("/events", methods=["POST"])
@require_role('mentor')
def create_event():
    body = request.get_json(silent=True) or {}
    title = body.get("title", "")
    date = body.get("date", "")
    source = body.get("source", "manual")
    created_at = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO events(title, date, source, created_at) VALUES(?, ?, ?, ?)", (title, date, source, created_at))
    conn.commit()
    eid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({"id": eid, "title": title, "date": date, "source": source, "created_at": created_at})


@app.route("/events/<int:eid>", methods=["PUT"])
@require_role('mentor')
def update_event(eid):
    body = request.get_json(silent=True) or {}
    title = body.get("title")
    date = body.get("date")
    source = body.get("source")
    row = c.execute("SELECT id FROM events WHERE id=?", (eid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    if title is not None:
        c.execute("UPDATE events SET title=? WHERE id=?", (title, eid))
    if date is not None:
        c.execute("UPDATE events SET date=? WHERE id=?", (date, eid))
    if source is not None:
        c.execute("UPDATE events SET source=? WHERE id=?", (source, eid))
    conn.commit()
    row = c.execute("SELECT id, title, date, source, created_at FROM events WHERE id=?", (eid,)).fetchone()
    return jsonify({"id": row[0], "title": row[1], "date": row[2], "source": row[3], "created_at": row[4]})


@app.route("/events/<int:eid>", methods=["DELETE"])
@require_role('mentor')
def delete_event(eid):
    c.execute("DELETE FROM events WHERE id=?", (eid,))
    conn.commit()
    return jsonify({"deleted": True, "id": eid})


@app.route("/events/generate", methods=["POST"])
@require_role('mentor')
def generate_events():
    """Automatically generate events for the next 3 months"""
    body = request.get_json(silent=True) or {}
    event_types = body.get("event_types", ["workshop", "seminar", "bootcamp", "course"])
    frequency = body.get("frequency", "weekly")  # weekly, biweekly, monthly
    
    import random
    from datetime import datetime, timedelta
    
    # Sample event templates
    workshop_templates = [
        "React Advanced Patterns",
        "Node.js Microservices",
        "Python Data Science",
        "JavaScript ES6+ Features",
        "Cloud Architecture Basics",
        "DevOps Fundamentals",
        "Machine Learning Intro",
        "Web Security Best Practices",
        "API Design Principles",
        "Database Optimization"
    ]
    
    seminar_templates = [
        "Career Development in Tech",
        "Industry Trends Discussion",
        "Tech Leadership Skills",
        "Startup Fundamentals",
        "Open Source Contributions",
        "Remote Work Strategies",
        "Tech Interview Prep",
        "Portfolio Building Workshop"
    ]
    
    bootcamp_templates = [
        "Full Stack Development Bootcamp",
        "Data Science Intensive",
        "Cloud Computing Bootcamp",
        "Mobile Development Camp"
    ]
    
    course_templates = [
        "Introduction to Programming",
        "Web Development Basics",
        "Advanced JavaScript",
        "Python Programming",
        "Database Design Fundamentals"
    ]
    
    # Generate events for next 3 months
    start_date = datetime.now()
    end_date = start_date + timedelta(days=90)
    current_date = start_date
    
    created_events = []
    
    while current_date <= end_date:
        # Skip weekends for most events
        if current_date.weekday() < 5:  # Monday to Friday
            # Randomly select event type and template
            event_type = random.choice(event_types)
            
            if event_type == "workshop":
                title = random.choice(workshop_templates)
            elif event_type == "seminar":
                title = random.choice(seminar_templates)
            elif event_type == "bootcamp":
                title = random.choice(bootcamp_templates)
            else:  # course
                title = random.choice(course_templates)
            
            # Add date-specific suffix
            if frequency == "weekly":
                date_suffix = f" - {current_date.strftime('%B %d')}"
            elif frequency == "biweekly":
                if (current_date - start_date).days % 14 == 0:
                    date_suffix = f" - {current_date.strftime('%B %d')}"
                else:
                    current_date += timedelta(days=1)
                    continue
            else:  # monthly
                if current_date.day <= 7:  # First week of month
                    date_suffix = f" - {current_date.strftime('%B %d')}"
                else:
                    current_date += timedelta(days=1)
                    continue
            
            event_title = title + date_suffix
            event_date = current_date.strftime('%Y-%m-%d')
            created_at = datetime.now(timezone.utc).isoformat()
            
            # Insert event
            c.execute(
                "INSERT INTO events(title, date, source, created_at) VALUES(?, ?, ?, ?)",
                (event_title, event_date, event_type, created_at)
            )
            
            event_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            created_events.append({
                "id": event_id,
                "title": event_title,
                "date": event_date,
                "source": event_type,
                "created_at": created_at
            })
        
        # Move to next date based on frequency
        if frequency == "weekly":
            current_date += timedelta(days=7)
        elif frequency == "biweekly":
            current_date += timedelta(days=14)
        else:  # monthly
            current_date += timedelta(days=30)
    
    conn.commit()
    return jsonify({
        "message": f"Generated {len(created_events)} events",
        "events": created_events
    })


@app.route("/reminders", methods=["GET"])
@require_auth
def get_reminders():
    """Get reminders for the authenticated student"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    student = payload.get("sub")
    
    rows = c.execute("""
        SELECT r.id, r.event_id, r.reminder_date, r.reminder_time, r.message, r.is_sent, r.created_at,
               e.title, e.date as event_date, e.source
        FROM reminders r
        JOIN events e ON r.event_id = e.id
        WHERE r.student = ?
        ORDER BY r.reminder_date ASC, r.reminder_time ASC
    """, (student,)).fetchall()
    
    reminders = []
    for row in rows:
        reminders.append({
            "id": row[0],
            "event_id": row[1],
            "reminder_date": row[2],
            "reminder_time": row[3],
            "message": row[4],
            "is_sent": row[5],
            "created_at": row[6],
            "event": {
                "title": row[7],
                "date": row[8],
                "source": row[9]
            }
        })
    
    return jsonify({"reminders": reminders})


@app.route("/reminders", methods=["POST"])
@require_auth
def create_reminder():
    """Create a reminder for an event"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    student = payload.get("sub")
    
    body = request.get_json(silent=True) or {}
    event_id = body.get("event_id")
    reminder_date = body.get("reminder_date")
    reminder_time = body.get("reminder_time", "09:00")
    message = body.get("message", "Event reminder")
    
    if not event_id or not reminder_date:
        return jsonify({"error": "event_id and reminder_date are required"}), 400
    
    # Verify event exists
    event = c.execute("SELECT id, title, date FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        return jsonify({"error": "Event not found"}), 404
    
    created_at = datetime.now(timezone.utc).isoformat()
    
    c.execute("""
        INSERT INTO reminders(student, event_id, reminder_date, reminder_time, message, created_at)
        VALUES(?, ?, ?, ?, ?, ?)
    """, (student, event_id, reminder_date, reminder_time, message, created_at))
    
    conn.commit()
    reminder_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    return jsonify({
        "id": reminder_id,
        "event_id": event_id,
        "reminder_date": reminder_date,
        "reminder_time": reminder_time,
        "message": message,
        "created_at": created_at,
        "event": {
            "title": event[1],
            "date": event[2]
        }
    })


@app.route("/reminders/<int:reminder_id>", methods=["DELETE"])
@require_auth
def delete_reminder(reminder_id):
    """Delete a reminder"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    student = payload.get("sub")
    
    # Verify reminder belongs to student
    reminder = c.execute("SELECT id FROM reminders WHERE id=? AND student=?", (reminder_id, student)).fetchone()
    if not reminder:
        return jsonify({"error": "Reminder not found"}), 404
    
    c.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
    conn.commit()
    
    return jsonify({"deleted": True, "id": reminder_id})


@app.route("/analytics/performance", methods=["GET"])
@require_auth
def get_performance_analytics():
    """Get performance analytics for student or mentor"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    user = payload.get("sub")
    role = payload.get("role")
    
    # Get query parameters
    student_id = request.args.get("student_id", "")
    period = request.args.get("period", "monthly")  # weekly, monthly, quarterly
    
    # For mentors, they can view any student's performance
    if role == "mentor" and student_id:
        target_student = student_id
    else:
        target_student = user
    
    # Generate performance data over time
    from datetime import datetime, timedelta
    
    performance_data = []
    
    if period == "weekly":
        # Last 12 weeks
        for i in range(12):
            date = datetime.now() - timedelta(weeks=11-i)
            start_date = date - timedelta(days=7)
            
            # Count certificates in this period
            cert_count = c.execute("""
                SELECT COUNT(*) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Count unique skills
            skills_count = c.execute("""
                SELECT COUNT(DISTINCT skill) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Calculate performance score (0-100)
            score = min(100, (cert_count * 10) + (skills_count * 15))
            
            performance_data.append({
                "date": date.strftime('%Y-%m-%d'),
                "certificates": cert_count,
                "skills": skills_count,
                "score": score
            })
    
    elif period == "monthly":
        # Last 6 months
        for i in range(6):
            date = datetime.now() - timedelta(days=30*(5-i))
            start_date = date - timedelta(days=30)
            
            # Count certificates in this period
            cert_count = c.execute("""
                SELECT COUNT(*) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Count unique skills
            skills_count = c.execute("""
                SELECT COUNT(DISTINCT skill) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Calculate performance score (0-100)
            score = min(100, (cert_count * 10) + (skills_count * 15))
            
            performance_data.append({
                "date": date.strftime('%Y-%m-%d'),
                "certificates": cert_count,
                "skills": skills_count,
                "score": score
            })
    
    else:  # quarterly
        # Last 4 quarters
        for i in range(4):
            date = datetime.now() - timedelta(days=90*(3-i))
            start_date = date - timedelta(days=90)
            
            # Count certificates in this period
            cert_count = c.execute("""
                SELECT COUNT(*) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Count unique skills
            skills_count = c.execute("""
                SELECT COUNT(DISTINCT skill) FROM certificates 
                WHERE student=? AND created_at BETWEEN ? AND ?
            """, (target_student, start_date.isoformat(), date.isoformat())).fetchone()[0]
            
            # Calculate performance score (0-100)
            score = min(100, (cert_count * 10) + (skills_count * 15))
            
            performance_data.append({
                "date": date.strftime('%Y-%m-%d'),
                "certificates": cert_count,
                "skills": skills_count,
                "score": score
            })
    
    return jsonify({
        "student": target_student,
        "period": period,
        "data": performance_data
    })


@app.route("/analytics/performance/students", methods=["GET"])
@require_role('mentor')
def get_students_performance():
    """Get performance data for all students (mentor only)"""
    period = request.args.get("period", "monthly")
    
    # Get all students
    students = c.execute("SELECT DISTINCT student FROM certificates").fetchall()
    
    all_performance = []
    
    for student_row in students:
        student = student_row[0]
        
        # Get current performance
        from datetime import datetime, timedelta
        
        if period == "weekly":
            date = datetime.now()
            start_date = date - timedelta(days=7)
        elif period == "monthly":
            date = datetime.now()
            start_date = date - timedelta(days=30)
        else:  # quarterly
            date = datetime.now()
            start_date = date - timedelta(days=90)
        
        # Count certificates
        cert_count = c.execute("""
            SELECT COUNT(*) FROM certificates 
            WHERE student=? AND created_at BETWEEN ? AND ?
        """, (student, start_date.isoformat(), date.isoformat())).fetchone()[0]
        
        # Count unique skills
        skills_count = c.execute("""
            SELECT COUNT(DISTINCT skill) FROM certificates 
            WHERE student=? AND created_at BETWEEN ? AND ?
        """, (student, start_date.isoformat(), date.isoformat())).fetchone()[0]
        
        # Calculate performance score
        score = min(100, (cert_count * 10) + (skills_count * 15))
        
        all_performance.append({
            "student": student,
            "certificates": cert_count,
            "skills": skills_count,
            "score": score
        })
    
    # Sort by performance score
    all_performance.sort(key=lambda x: x["score"], reverse=True)
    
    return jsonify({
        "period": period,
        "students": all_performance
    })


@app.route("/attendance/<student>", methods=["GET"])
@require_auth
def get_attendance(student):
    rows = c.execute("SELECT date, status, source_cert FROM attendance WHERE student=? ORDER BY date DESC", (student,)).fetchall()
    data = [{"date": r[0], "status": r[1], "source_cert": r[2]} for r in rows]
    return jsonify({"student": student, "attendance": data})


@app.route('/roadmap/<student_id>', methods=['GET'])
def get_roadmap(student_id):
    """
    Get or generate a learning roadmap for a student.
    
    Query parameters:
    - refresh: Set to 'true' to force regeneration of the roadmap
    - start_date: Custom start date for the roadmap (YYYY-MM-DD)
    - format: Output format ('json' or 'pdf') - PDF support coming soon
    """
    try:
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        start_date = request.args.get('start_date')
        output_format = request.args.get('format', 'json').lower()
        
        # Validate output format
        if output_format not in ['json']:  # Add 'pdf' when implemented
            return jsonify({'error': f'Unsupported format: {output_format}. Only JSON is currently supported.'}), 400
        
        # Check if we already have a roadmap for this student
        roadmap_path = os.path.join(app.config['ROADMAPS_FOLDER'], f'roadmap_{student_id}.json')
        
        if not refresh and os.path.exists(roadmap_path):
            # Load existing roadmap
            with open(roadmap_path, 'r') as f:
                roadmap = json.load(f)
        else:
            # Generate a new roadmap
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            
            # Get student's goal
            cursor = conn.cursor()
            cursor.execute('SELECT goal FROM goals WHERE student = ?', (student_id,))
            goal_row = cursor.fetchone()
            
            if not goal_row or not goal_row[0]:
                # Fallback: use a sensible default to avoid blocking the UI
                goal = 'software_engineer'
            else:
                goal = goal_row[0]
            
            # Get student's skills
            cursor.execute('''
                SELECT DISTINCT skill 
                FROM skills 
                WHERE student = ?
            ''', (student_id,))
            skills = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            # Generate the roadmap: try OpenAI first, then Gemini, fallback to curated generator
            roadmap = None
            
            # Try OpenAI first
            if OPENAI_ROADMAP_GENERATOR is not None:
                try:
                    roadmap = OPENAI_ROADMAP_GENERATOR.generate_roadmap(
                        goal=goal,
                        current_skills=skills,
                        start_date=start_date
                    )
                    print(f"Successfully generated roadmap using OpenAI for goal: {goal}")
                except Exception as e:
                    print(f"OpenAI roadmap generation failed: {e}")
                    roadmap = None
            
            # Fallback to Gemini if OpenAI fails
            if roadmap is None and gemini_generate is not None:
                try:
                    g = gemini_generate(goal, skills) or {}
                    phases = g.get('phases') or []
                    # Map Gemini phases to our schema, computing dates from start_date
                    from datetime import datetime, timedelta
                    sdt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.now()
                    cur = sdt
                    mapped_phases = []
                    for ph in phases:
                        # offset
                        off = int(ph.get('start_weeks_offset') or 0)
                        cur = sdt + timedelta(weeks=off)
                        dur = int(ph.get('duration_weeks') or 4)
                        end = cur + timedelta(weeks=dur)
                        resources = []
                        for r in ph.get('resources') or []:
                            resources.append({
                                'type': r.get('type') or 'resource',
                                'name': r.get('name') or 'Resource',
                                'duration_weeks': int(r.get('duration_weeks') or dur),
                                'difficulty': r.get('difficulty') or 'intermediate',
                                'status': 'pending',
                            })
                        mapped_phases.append({
                            'name': ph.get('name') or 'Phase',
                            'description': ph.get('description') or '',
                            'start_date': cur.strftime('%Y-%m-%d'),
                            'end_date': (end - timedelta(days=1)).strftime('%Y-%m-%d'),
                            'resources': resources,
                        })
                    if mapped_phases:
                        roadmap = {
                            'goal': goal,
                            'start_date': (sdt.strftime('%Y-%m-%d')),
                            'generated_on': datetime.now().strftime('%Y-%m-%d'),
                            'phases': mapped_phases,
                            'end_date': (mapped_phases[-1]['end_date']),
                            'total_duration_weeks': max(1, ( (end - sdt).days // 7) ),
                            'generated_by': 'Gemini'
                        }
                except Exception:
                    roadmap = None

            # Final fallback to curated generator
            if roadmap is None:
                roadmap = RoadmapGenerator().generate_roadmap(
                    goal=goal,
                    current_skills=skills,
                    start_date=start_date
                )
                roadmap['generated_by'] = 'Curated Generator'
            
            # Save the roadmap for future reference
            with open(roadmap_path, 'w') as f:
                json.dump(roadmap, f, indent=2)
        
        # Return in the requested format
        if output_format == 'json':
            return jsonify(roadmap)
        # Add PDF export when implemented
        # elif output_format == 'pdf':
        #     return generate_pdf_roadmap(roadmap)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ------------------- Mentor review queue -------------------
@app.route('/mentor/review', methods=['GET'])
@require_role('mentor')
def mentor_review_list():
    """List certificates pending review (verified = 0). Optional ?student=<id> filter."""
    student = request.args.get('student')
    if student:
        rows = c.execute(
            "SELECT filename, student, verified, reason, summary, skills, goal, event_date FROM certificates WHERE student=? AND verified=0 ORDER BY rowid DESC",
            (student,)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT filename, student, verified, reason, summary, skills, goal, event_date FROM certificates WHERE verified=0 ORDER BY rowid DESC"
        ).fetchall()
    colnames = ["filename","student","verified","reason","summary","skills","goal","event_date"]
    data = [dict(zip(colnames, r)) for r in rows]
    return jsonify({"pending": data})


@app.route('/mentor/approve', methods=['POST'])
@require_role('mentor')
def mentor_approve():
    body = request.get_json(silent=True) or {}
    filename = (body.get('filename') or '').strip()
    student = (body.get('student') or '').strip()
    skip_ml_analysis = body.get('skip_ml_analysis', False)
    
    if not filename or not student:
        return jsonify({"error": "filename_and_student_required"}), 400
    
    # Perform ML analysis if enabled and not skipped
    ml_analysis = None
    if ML_ENABLED and not skip_ml_analysis:
        try:
            cert_path = os.path.join(UPLOAD_FOLDER, student, filename)
            if os.path.exists(cert_path):
                ml_result = fraud_detector.predict_fraud_probability(cert_path)
                
                # If high risk detected, warn mentor but still allow approval
                if ml_result['fraud_probability'] > 0.7:
                    ml_analysis = {
                        "warning": "High fraud risk detected",
                        "risk_level": ml_result['risk_level'],
                        "probability": ml_result['fraud_probability'],
                        "recommendation": ml_result['recommendation']
                    }
                
                # Store analysis result
                try:
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS certificate_analysis (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            filename TEXT NOT NULL,
                            student TEXT NOT NULL,
                            fraud_probability REAL,
                            risk_level TEXT,
                            recommendation TEXT,
                            features TEXT,
                            analyzed_at TEXT,
                            FOREIGN KEY (filename, student) REFERENCES certificates(filename, student)
                        )
                    ''')
                    
                    c.execute('''
                        INSERT INTO certificate_analysis 
                        (filename, student, fraud_probability, risk_level, recommendation, features, analyzed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        filename, student, ml_result['fraud_probability'], ml_result['risk_level'],
                        ml_result['recommendation'], json.dumps(ml_result.get('features', {})),
                        datetime.now(timezone.utc).isoformat()
                    ))
                except Exception as e:
                    print(f"Error saving ML analysis: {e}")
        except Exception as e:
            print(f"Error in ML analysis during approval: {e}")
    
    # Update certificate
    c.execute("UPDATE certificates SET verified=1, reason='approved_by_mentor' WHERE filename=? AND student=?", (filename, student))
    
    # Attendance sync if event_date present
    try:
        row = c.execute("SELECT event_date FROM certificates WHERE filename=? AND student=?", (filename, student)).fetchone()
        if row and row[0]:
            c.execute(
                "INSERT INTO attendance(student, date, status, source_cert) VALUES(?,?,?,?)",
                (student, row[0], 'present', filename)
            )
    except Exception:
        pass
    
    # Notification for student
    try:
        c.execute(
            "INSERT INTO notifications(student, message, created_at) VALUES(?,?,?)",
            (student, f"Certificate '{filename}' approved by mentor", datetime.now(timezone.utc).isoformat())
        )
    except Exception:
        pass
    
    conn.commit()
    
    response_data = {"status": "ok"}
    if ml_analysis:
        response_data["ml_analysis"] = ml_analysis
    
    return jsonify(response_data)


@app.route('/mentor/reject', methods=['POST'])
@require_role('mentor')
def mentor_reject():
    body = request.get_json(silent=True) or {}
    filename = (body.get('filename') or '').strip()
    student = (body.get('student') or '').strip()
    reason = (body.get('reason') or 'rejected_by_mentor').strip()
    if not filename or not student:
        return jsonify({"error": "filename_and_student_required"}), 400
    c.execute("UPDATE certificates SET verified=0, reason=? WHERE filename=? AND student=?", (reason, filename, student))
    # Notification for student
    try:
        c.execute(
            "INSERT INTO notifications(student, message, created_at) VALUES(?,?,?)",
            (student, f"Certificate '{filename}' rejected: {reason}", datetime.now(timezone.utc).isoformat())
        )
    except Exception:
        pass
    conn.commit()
    return jsonify({"status": "ok"})


# ------------------- ML-based Fraud Detection -------------------
@app.route('/ml/analyze-certificate', methods=['POST'])
@require_role('mentor')
def ml_analyze_certificate():
    """Analyze a certificate for fraud using ML"""
    if not ML_ENABLED:
        return jsonify({"error": "ML fraud detection not available"}), 503
    
    try:
        body = request.get_json(silent=True) or {}
        filename = (body.get('filename') or '').strip()
        student = (body.get('student') or '').strip()
        
        if not filename or not student:
            return jsonify({"error": "filename_and_student_required"}), 400
        
        # Get certificate file path
        cert_path = os.path.join(UPLOAD_FOLDER, student, filename)
        if not os.path.exists(cert_path):
            return jsonify({"error": "certificate_file_not_found"}), 404
        
        # Analyze with ML model
        result = fraud_detector.predict_fraud_probability(cert_path)
        
        # Store analysis result in database
        analysis_data = {
            'filename': filename,
            'student': student,
            'fraud_probability': result['fraud_probability'],
            'risk_level': result['risk_level'],
            'recommendation': result['recommendation'],
            'features': result.get('features', {}),
            'analyzed_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Save analysis to database (create new table if needed)
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS certificate_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    student TEXT NOT NULL,
                    fraud_probability REAL,
                    risk_level TEXT,
                    recommendation TEXT,
                    features TEXT,
                    analyzed_at TEXT,
                    FOREIGN KEY (filename, student) REFERENCES certificates(filename, student)
                )
            ''')
            
            c.execute('''
                INSERT INTO certificate_analysis 
                (filename, student, fraud_probability, risk_level, recommendation, features, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                filename, student, result['fraud_probability'], result['risk_level'],
                result['recommendation'], json.dumps(result.get('features', {})),
                analysis_data['analyzed_at']
            ))
            conn.commit()
        except Exception as e:
            print(f"Error saving analysis to database: {e}")
        
        return jsonify({
            "success": True,
            "analysis": result,
            "recommendation": result['recommendation'],
            "risk_level": result['risk_level']
        })
        
    except Exception as e:
        print(f"Error in ML analysis: {e}")
        return jsonify({"error": f"analysis_failed: {str(e)}"}), 500


@app.route('/ml/compare-certificates', methods=['POST'])
@require_role('mentor')
def ml_compare_certificates():
    """Compare multiple certificates for consistency"""
    if not ML_ENABLED:
        return jsonify({"error": "ML fraud detection not available"}), 503
    
    try:
        body = request.get_json(silent=True) or {}
        certificates = body.get('certificates', [])  # List of {filename, student} objects
        
        if len(certificates) < 2:
            return jsonify({"error": "at_least_two_certificates_required"}), 400
        
        # Get file paths for all certificates
        cert_paths = []
        for cert in certificates:
            filename = cert.get('filename', '').strip()
            student = cert.get('student', '').strip()
            
            if not filename or not student:
                return jsonify({"error": "filename_and_student_required"}), 400
            
            cert_path = os.path.join(UPLOAD_FOLDER, student, filename)
            if not os.path.exists(cert_path):
                return jsonify({"error": f"certificate_file_not_found: {filename}"}), 404
            
            cert_paths.append(cert_path)
        
        # Compare certificates
        result = fraud_detector.compare_certificates(cert_paths)
        
        return jsonify({
            "success": True,
            "comparison": result,
            "recommendation": result.get('recommendation', 'Manual review recommended')
        })
        
    except Exception as e:
        print(f"Error in certificate comparison: {e}")
        return jsonify({"error": f"comparison_failed: {str(e)}"}), 500


@app.route('/ml/analysis-history', methods=['GET'])
@require_role('mentor')
def ml_analysis_history():
    """Get history of ML analyses for certificates"""
    if not ML_ENABLED:
        return jsonify({"error": "ML fraud detection not available"}), 503
    
    try:
        student = request.args.get('student', '')
        
        if student:
            rows = c.execute('''
                SELECT filename, student, fraud_probability, risk_level, recommendation, analyzed_at
                FROM certificate_analysis 
                WHERE student=? 
                ORDER BY analyzed_at DESC
            ''', (student,)).fetchall()
        else:
            rows = c.execute('''
                SELECT filename, student, fraud_probability, risk_level, recommendation, analyzed_at
                FROM certificate_analysis 
                ORDER BY analyzed_at DESC
                LIMIT 100
            ''').fetchall()
        
        colnames = ["filename", "student", "fraud_probability", "risk_level", "recommendation", "analyzed_at"]
        data = [dict(zip(colnames, r)) for r in rows]
        
        return jsonify({
            "success": True,
            "history": data
        })
        
    except Exception as e:
        print(f"Error getting analysis history: {e}")
        return jsonify({"error": f"history_failed: {str(e)}"}), 500


@app.route('/ml/student-risk-summary', methods=['GET'])
@require_role('mentor')
def ml_student_risk_summary():
    """Get risk summary for all students"""
    if not ML_ENABLED:
        return jsonify({"error": "ML fraud detection not available"}), 503
    
    try:
        # Get latest analysis for each student
        rows = c.execute('''
            SELECT student, 
                   AVG(fraud_probability) as avg_risk,
                   MAX(fraud_probability) as max_risk,
                   COUNT(*) as total_analyzed,
                   SUM(CASE WHEN risk_level = 'High' THEN 1 ELSE 0 END) as high_risk_count,
                   SUM(CASE WHEN risk_level = 'Medium' THEN 1 ELSE 0 END) as medium_risk_count,
                   SUM(CASE WHEN risk_level = 'Low' THEN 1 ELSE 0 END) as low_risk_count
            FROM certificate_analysis 
            GROUP BY student
            ORDER BY avg_risk DESC
        ''').fetchall()
        
        colnames = ["student", "avg_risk", "max_risk", "total_analyzed", "high_risk_count", "medium_risk_count", "low_risk_count"]
        data = [dict(zip(colnames, r)) for r in rows]
        
        return jsonify({
            "success": True,
            "summary": data
        })
        
    except Exception as e:
        print(f"Error getting risk summary: {e}")
        return jsonify({"error": f"summary_failed: {str(e)}"}), 500


@app.route('/notifications', methods=['GET'])
@require_auth
def list_notifications():
    student = request.args.get('student')
    if not student:
        return jsonify({"error": "student_required"}), 400
    rows = c.execute(
        "SELECT id, student, message, created_at FROM notifications WHERE student=? ORDER BY id DESC",
        (student,)
    ).fetchall()
    data = [
        {"id": r[0], "student": r[1], "message": r[2], "created_at": r[3]}
        for r in rows
    ]
    return jsonify({"notifications": data})

@app.route('/analytics/skills', methods=['GET'])
@require_auth
def get_skills_analytics():
    """
    Get skill distribution analytics.
    
    Query parameters:
    - student_id: Optional student ID to filter by
    - time_range: Optional time range ('7d', '30d', '90d', '1y')
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "")
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user = payload.get("sub")
        role = payload.get("role")
        
        student_id = request.args.get('student_id')
        time_range = request.args.get('time_range')
        
        analytics = StudentAnalytics(DB_PATH)
        
        if student_id:
            # Get skills for a specific student (from manual entries + certificates)
            if role == "mentor" or student_id == user:
                skills_list = analytics.get_student_skills(student_id)
                return jsonify({
                    'student_id': student_id,
                    'skills': skills_list
                })
            else:
                return jsonify({"error": "Unauthorized to view other student's skills"}), 403
        else:
            # Get overall skill distribution
            skill_distribution = analytics.get_skill_distribution()
            return jsonify({
                'skill_distribution': skill_distribution,
                'total_unique_skills': len(skill_distribution),
                'total_skill_occurrences': sum(skill_distribution.values())
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics/achievements', methods=['GET'])
@require_auth
def get_achievements_analytics():
    """
    Get achievements analytics (certificates as achievements).
    
    Query parameters:
    - student_id: Optional student ID to filter by
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "")
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user = payload.get("sub")
        role = payload.get("role")
        
        student_id = request.args.get('student_id')
        
        # If student_id is provided, check authorization
        if student_id and role != "mentor" and student_id != user:
            return jsonify({"error": "Unauthorized to view other student's achievements"}), 403
        
        # Use the requesting user's ID if no student_id specified
        target_student = student_id or user
        
        # Get certificates as achievements for the student
        rows = c.execute(
            "SELECT filename, verified, summary, goal, event_date FROM certificates WHERE student = ? ORDER BY event_date DESC",
            (target_student,)
        ).fetchall()
        
        certificates = []
        for row in rows:
            certificates.append({
                "name": row[0],  # filename
                "type": "Certificate",
                "verified": row[1],
                "summary": row[2],
                "goal": row[3],
                "date": row[4]
            })
        
        # Get authenticity stats
        analytics = StudentAnalytics(DB_PATH)
        authenticity = analytics.get_authenticity_ratio(target_student)
        
        return jsonify({
            'student_id': target_student,
            'achievements': certificates,
            'total_certificates': len(certificates),
            'verified_count': len([c for c in certificates if c['verified']]),
            'authenticity': authenticity
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/<student_id>', methods=['GET'])
def get_student_portfolio(student_id):
    """
    Generate a portfolio for a student.
    
    Query parameters:
    - format: Output format ('json' or 'pdf') - PDF support coming soon
    """
    try:
        output_format = request.args.get('format', 'json').lower()
        
        # Validate output format
        if output_format not in ['json','pdf']:
            return jsonify({'error': f'Unsupported format: {output_format}. Use json or pdf'}), 400
        
        analytics = StudentAnalytics(DB_PATH)
        portfolio_data = analytics.generate_portfolio_data(student_id)
        
        # Return in the requested format
        if output_format == 'json':
            return jsonify(portfolio_data)
        elif output_format == 'pdf':
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfgen import canvas
                from io import BytesIO
                buffer = BytesIO()
                cpdf = canvas.Canvas(buffer, pagesize=letter)
                width, height = letter
                y = height - 50
                cpdf.setFont("Helvetica-Bold", 16)
                cpdf.drawString(50, y, f"MindVault Portfolio - {student_id}")
                y -= 30
                cpdf.setFont("Helvetica", 12)
                cpdf.drawString(50, y, f"Goal: {portfolio_data.get('goal') or 'N/A'}")
                y -= 20
                # Skills
                cpdf.setFont("Helvetica-Bold", 12)
                cpdf.drawString(50, y, "Skills:")
                y -= 18
                cpdf.setFont("Helvetica", 11)
                for sk in (portfolio_data.get('skills') or [])[:25]:
                    cpdf.drawString(60, y, f"- {sk}")
                    y -= 14
                    if y < 80:
                        cpdf.showPage(); y = height - 50
                        cpdf.setFont("Helvetica", 11)
                # Certificates
                y -= 6
                cpdf.setFont("Helvetica-Bold", 12)
                if y < 80: cpdf.showPage(); y = height - 50
                cpdf.drawString(50, y, "Certificates:")
                y -= 18
                cpdf.setFont("Helvetica", 11)
                for cert in (portfolio_data.get('certificates') or [])[:20]:
                    title = cert.get('title') or cert.get('file_path') or 'Certificate'
                    status = cert.get('verification_status') or cert.get('verified')
                    cpdf.drawString(60, y, f"- {title} ({status})")
                    y -= 14
                    if y < 80:
                        cpdf.showPage(); y = height - 50
                        cpdf.setFont("Helvetica", 11)
                cpdf.showPage()
                cpdf.save()
                buffer.seek(0)
                return send_file(buffer, as_attachment=True, download_name=f"portfolio_{student_id}.pdf", mimetype='application/pdf')
            except Exception as e:
                return jsonify({'error': 'pdf_not_supported', 'detail': str(e)}), 501
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
