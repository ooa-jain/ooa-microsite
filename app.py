import re
import os
import logging
import random
import json
import platform
from functools import wraps
from datetime import datetime, timedelta, date
from io import StringIO, BytesIO

# ── Environment ────────────────────────────────────────────────────────
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
from dotenv import load_dotenv
load_dotenv()

# ── Flask & extensions ─────────────────────────────────────────────────
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, send_from_directory, jsonify, json as flask_json)
from flask_pymongo import PyMongo
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# ── Database / serialization ───────────────────────────────────────────
from bson import ObjectId
import pytz
import pandas as pd
import requests as http_requests

# ── Google OAuth ───────────────────────────────────────────────────────
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ── APScheduler ────────────────────────────────────────────────────────
from apscheduler.schedulers.background import BackgroundScheduler

# ── Groq (Jain AI) ────────────────────────────────────────────────────
from groq import Groq

# ── PDF extraction ─────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not installed — PDF text extraction disabled.")

# ══════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  FLASK APP INIT
# ══════════════════════════════════════════════════════════════════════
app = Flask(__name__)
from config import Config
app.config.from_object(Config)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SECURE']   = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

UPLOAD_FOLDER      = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf','docx','txt','png','jpg','jpeg','gif','xlsx','csv','xls'}
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

mongo = PyMongo(app)
db    = mongo.db

_mail_user = os.getenv('EMAIL_USER', '')
_mail_pass = os.getenv('EMAIL_PASS', '')
_mail_server = os.getenv('MAIL_SERVER', 'smtp.hostinger.com')
_mail_port = int(os.getenv('MAIL_PORT', 465))
_mail_tls = os.getenv('MAIL_USE_TLS', 'False').lower() == 'true'
_mail_ssl = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'

app.config['MAIL_SERVER']            = _mail_server
app.config['MAIL_PORT']              = _mail_port
app.config['MAIL_USE_TLS']           = _mail_tls
app.config['MAIL_USE_SSL']           = _mail_ssl
app.config['MAIL_USERNAME']          = _mail_user
app.config['MAIL_PASSWORD']          = _mail_pass
app.config['MAIL_DEFAULT_SENDER']    = (_mail_user, 'Office of Academics – Jain University')
app.config['MAIL_MAX_EMAILS']        = None
app.config['MAIL_ASCII_ATTACHMENTS'] = False
mail = Mail(app)
logger.info(f"Mail configured: {_mail_server}:{_mail_port} user={_mail_user}")

_groq_key = os.getenv("GROQ_API_KEY", "").strip()
if not _groq_key:
    logger.warning("⚠️  GROQ_API_KEY not set — Jain AI features will return errors")
ai_client = Groq(api_key=_groq_key)

IST = pytz.timezone('Asia/Kolkata')
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/drive']
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# ══════════════════════════════════════════════════════════════════════
#  TIMEZONE HELPERS
# ══════════════════════════════════════════════════════════════════════
def make_timezone_aware(dt):
    if dt is None: return None
    if dt.tzinfo is None: return IST.localize(dt)
    return dt.astimezone(IST)

def make_timezone_naive(dt):
    if dt is None: return None
    if dt.tzinfo is not None: return dt.astimezone(IST).replace(tzinfo=None)
    return dt

def normalize_datetime_for_query(dt):
    if dt is None: return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt

def get_indian_time():
    return datetime.now(IST).replace(tzinfo=None)

def get_indian_time_aware():
    return datetime.now(IST)

def convert_to_ist(dt):
    if dt.tzinfo is None: dt = pytz.utc.localize(dt)
    return dt.astimezone(IST)

def get_today_ist_string():
    return datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(IST).strftime("%Y-%m-%d")

def normalize_date(date_str):
    if not date_str: return ""
    date_str = str(date_str).strip()
    if len(date_str) == 10 and date_str[4] == "-": return date_str
    for fmt in ["%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%m/%d/%Y","%Y/%m/%d"]:
        try: return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError: continue
    return date_str

def parse_name_from_email(email):
    if not email:
        return 'User'
    username = email.split('@')[0]
    # Replace dots, numbers, hyphens, underscores with spaces
    name_parts = re.split(r'[\._\-0-9]+', username)
    clean_parts = [part.capitalize() for part in name_parts if part]
    return " ".join(clean_parts)

# ══════════════════════════════════════════════════════════════════════
#  DB INDEXES
# ══════════════════════════════════════════════════════════════════════
def create_indexes():
    try:
        db.users.create_index([('email',1)], unique=True)
        db.users.create_index([('approved',1)])
        db.users.create_index([('user_type',1)])
        db.users.create_index([('special_role',1)])
        db.users.create_index([('is_online',1)])
        db.users.create_index([('last_seen',-1)])
        db.events.create_index([('event_date',1)])
        db.events.create_index([('school',1)])
        db.events.create_index([('department',1)])
        db.campus_gallery.create_index([('date_happened',-1)])
        db.campus_gallery.create_index([('department',1)])
        db.event_reminders.create_index([('user_id',1)])
        db.event_reminders.create_index([('reminder_datetime',1)])
        db.event_reminders.create_index([('sent',1)])
        db.event_reminders.create_index([('sent',1),('reminder_datetime',1)])
        db.office_documents.create_index([('user_id',1)])
        db.office_documents.create_index([('status',1)])
        db.office_documents.create_index([('submitted_at',-1)])
        db.document_shares.create_index([('shared_by',1)])
        db.document_shares.create_index([('shared_with',1)])
        db.document_shares.create_index([('shared_at',-1)])
        db.chat_messages.create_index([('sender_id',1)])
        db.chat_messages.create_index([('receiver_id',1)])
        db.chat_messages.create_index([('group_id',1)])
        db.chat_messages.create_index([('timestamp',-1)])
        db.chat_groups.create_index([('group_type',1)])
        db.tasks.create_index([('assigned_to',1)])
        db.tasks.create_index([('assigned_by',1)])
        db.tasks.create_index([('status',1)])
        db.tasks.create_index([('due_date',1)])
        db.activity_logs.create_index([('user_id',1)])
        db.activity_logs.create_index([('timestamp',-1)])
        db.user_files.create_index([('user_email',1)])
        db.user_files.create_index([('uploaded_at',-1)])
        db.public_files.create_index([('uploaded_at',-1)])
        db.ugc_data.create_index([('uploaded_at',-1)])
        db.monthly_engagement.create_index([('uploaded_at',-1)])
        db.newsletters.create_index([('uploaded_at',-1)])
        db.direct_messages.create_index([('sender_id',1)])
        db.direct_messages.create_index([('receiver_id',1)])
        db.direct_messages.create_index([('timestamp',-1)])
        db.direct_messages.create_index([('read',1)])
        logger.info("✅ DB indexes created")
    except Exception as e:
        logger.error(f"❌ Index creation error: {e}")

# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def _allowed(filename):
    return allowed_file(filename)

# ══════════════════════════════════════════════════════════════════════
#  AUTH DECORATORS
# ══════════════════════════════════════════════════════════════════════
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'email' not in session:
            if request.path.startswith('/api/') or request.is_json or \
               request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Not logged in'}), 401
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def approval_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'email' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Not logged in'}), 401
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        approved = session.get('approved', False)
        if not approved:
            user = db.users.find_one({'email': session['email']})
            if user:
                approved = user.get('approved', False)
                session['approved'] = approved
        if not approved:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Account pending approval'}), 403
            flash('⏳ Your account is pending admin approval.', 'warning')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

def _login_required(f):
    return login_required(f)

def _core_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('email'):
            return redirect(url_for('login'))
        if not (session.get('user_type') == 'core' or
                session.get('special_role') == 'office_barrier' or
                session.get('role') == 'admin'):
            flash('Access denied. Core team only.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

def _core_or_leader_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('email'):
            return redirect(url_for('login'))
        if not (session.get('user_type') == 'core' or
                session.get('special_role') in ['office_barrier', 'leader'] or
                session.get('role') == 'admin'):
            flash('Access denied.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════════════
#  ROLE CHECKS
# ══════════════════════════════════════════════════════════════════════
def is_faculty():
    return (session.get('role') == 'user' and
            session.get('user_type') == 'faculty' and
            not session.get('special_role'))

def is_core_member():
    if session.get('special_role') in ['core','office_barrier'] or session.get('user_type') == 'core':
        return True
    if 'email' in session:
        user = db.users.find_one({'email': session['email']})
        if user and (user.get('special_role') in ['core','office_barrier'] or user.get('user_type') == 'core'):
            return True
    return False

def is_leader():
    if session.get('special_role') == 'leader':
        return True
    if 'email' in session:
        user = db.users.find_one({'email': session['email']})
        if user and user.get('special_role') == 'leader':
            return True
    return False

def is_core_or_leader():
    return is_core_member() or is_leader()

def is_office_barrier():
    return is_core_member()

def has_special_access():
    return is_core_or_leader()

# ══════════════════════════════════════════════════════════════════════
#  USER INFO HELPER
# ══════════════════════════════════════════════════════════════════════
def _get_user_info():
    return {
        'user_logged_in':   bool(session.get('email')),
        'user_email':       session.get('email', ''),
        'user_role':        session.get('role', 'user'),
        'user_type':        session.get('user_type', ''),
        'special_role':     session.get('special_role', ''),
        'approved':         session.get('approved', False),
        'user_department':  session.get('user_department', ''),
        'user_location':    session.get('user_location', ''),
    }

def _track_activity(action_description=None):
    email = session.get('email')
    if not email: return
    update = {'$set': {'last_seen': datetime.utcnow()}}
    if action_description:
        update['$inc'] = {'changes_made': 1}
        update['$push'] = {
            'activity_log': {
                'action': action_description,
                'at': datetime.utcnow(),
                'session_id': session.get('session_id', '')
            }
        }
    db.users.update_one({'email': email}, update)

# ══════════════════════════════════════════════════════════════════════
#  JAIN AI HELPERS
# ══════════════════════════════════════════════════════════════════════
def extract_text_from_file(file_url: str, max_chars: int = 4000) -> str:
    try:
        response = http_requests.get(file_url, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type or file_url.lower().endswith(".pdf"):
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(stream=response.content, filetype="pdf")
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
                return text[:max_chars]
            return ""
        elif any(file_url.lower().endswith(ext) for ext in [".txt", ".csv", ".md"]):
            return response.text[:max_chars]
        elif file_url.lower().endswith(".docx"):
            try:
                from docx import Document
                doc = Document(BytesIO(response.content))
                return "\n".join(p.text for p in doc.paragraphs)[:max_chars]
            except ImportError:
                return ""
        return ""
    except Exception as e:
        logger.error(f"[Jain AI] File extraction error: {e}")
        return ""

def call_claude(prompt: str, system: str = None, max_tokens: int = 1000) -> str:
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        err = str(e).lower()
        if "auth" in err or "api key" in err or "unauthorized" in err:
            raise Exception("Invalid GROQ_API_KEY — please check your .env file")
        if "rate" in err:
            raise Exception("Jain AI rate limit reached — please try again in a moment")
        if "connect" in err:
            raise Exception("Could not connect to Jain AI — check your internet connection")
        raise Exception(f"Jain AI error: {str(e)}")

def call_claude_chat(messages: list, system: str = None, max_tokens: int = 800) -> str:
    try:
        groq_messages = []
        if system:
            groq_messages.append({"role": "system", "content": system})
        groq_messages.extend(messages)
        response = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=groq_messages,
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        err = str(e).lower()
        if "auth" in err or "api key" in err or "unauthorized" in err:
            raise Exception("Invalid GROQ_API_KEY — please check your .env file")
        if "rate" in err:
            raise Exception("Jain AI rate limit reached — please try again in a moment")
        raise Exception(f"Jain AI error: {str(e)}")

# ══════════════════════════════════════════════════════════════════════
#  GOOGLE DRIVE HELPERS
# ══════════════════════════════════════════════════════════════════════
def get_drive_service():
    if 'drive_creds' not in session: return None
    try:
        c = session['drive_creds']
        required = ['token','refresh_token','token_uri','client_id','client_secret']
        for f in required:
            if f not in c: return None
        creds = Credentials(
            token=c['token'], refresh_token=c['refresh_token'],
            token_uri=c['token_uri'], client_id=c['client_id'],
            client_secret=c['client_secret'], scopes=c.get('scopes', DRIVE_SCOPES)
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Drive service error: {e}")
        session.pop('drive_creds', None)
        return None

def make_file_public(service, file_id):
    try:
        service.permissions().create(fileId=file_id, body={'type':'anyone','role':'reader'}).execute()
        return True
    except Exception as e:
        logger.error(f"Make public error: {e}")
        return False

def make_file_private(service, file_id):
    try:
        perms = service.permissions().list(fileId=file_id).execute()
        for p in perms.get('permissions', []):
            if p.get('type') == 'anyone':
                service.permissions().delete(fileId=file_id, permissionId=p['id']).execute()
        return True
    except Exception as e:
        logger.error(f"Make private error: {e}")
        return False

def delete_drive_file(service, file_id):
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        logger.error(f"Delete drive file error: {e}")
        return False

def get_drive_stats():
    try:
        service = get_drive_service()
        if not service: return {'total_files': 0, 'recent_uploads': []}
        seven_days_ago = (get_indian_time() - timedelta(days=7)).isoformat()
        recent = service.files().list(
            q=f"createdTime >= '{seven_days_ago}' and trashed=false",
            pageSize=10, orderBy="createdTime desc",
            fields="files(id,name,mimeType,createdTime,parents,webViewLink)"
        ).execute()
        recent_files = recent.get('files', [])
        for f in recent_files:
            if f.get('parents'):
                try:
                    folder = service.files().get(fileId=f['parents'][0], fields='name').execute()
                    f['folder_name'] = folder.get('name', 'Root')
                except:
                    f['folder_name'] = 'Root'
            else:
                f['folder_name'] = 'Root'
        all_files = service.files().list(q="trashed=false", pageSize=1000, fields="files(id)").execute()
        return {'total_files': len(all_files.get('files', [])), 'recent_uploads': recent_files}
    except Exception as e:
        logger.error(f"Drive stats error: {e}")
        return {'total_files': 0, 'recent_uploads': []}

NAVBAR_CACHE = {} # email -> (timestamp, items)

def get_user_navbar(email):
    try:
        now = time.time()
        if email in NAVBAR_CACHE:
            ts, cached = NAVBAR_CACHE[email]
            if now - ts < 60: # Cache navbar for 60 seconds
                return cached
        nav = db.user_navbars.find_one({"user_email": email})
        res = nav.get('items', []) if nav else []
        NAVBAR_CACHE[email] = (now, res)
        return res
    except Exception as e:
        logger.error(f"Error in get_user_navbar: {e}")
        return []

def get_all_campuses():
    try:
        campuses_cursor = db.campuses.find()
        campuses = [c['name'] for c in campuses_cursor if c.get('name')]
        if not campuses:
            default_campuses = [
                "JP Nagar Campus",
                "Whitefield Campus",
                "Yelahanka Campus",
                "JC Road Campus",
                "Lalbagh Campus",
                "Kanakapura Campus",
                "Sheshadripuram Campus",
                "Shankarapuram Campus",
                "Kochi Campus"
            ]
            for name in default_campuses:
                db.campuses.insert_one({'name': name})
            campuses = default_campuses
        return sorted(campuses)
    except Exception as e:
        logger.error(f"Error in get_all_campuses: {e}")
        return [
            "JP Nagar Campus",
            "Whitefield Campus",
            "Yelahanka Campus",
            "JC Road Campus",
            "Lalbagh Campus",
            "Kanakapura Campus",
            "Sheshadripuram Campus",
            "Shankarapuram Campus",
            "Kochi Campus"
        ]

GLOBAL_DASHBOARD_CACHE = {}

def get_cached_dashboard_data(cache_key, query_func, ttl=15):
    now = time.time()
    if cache_key in GLOBAL_DASHBOARD_CACHE:
        cache_time, cached_val = GLOBAL_DASHBOARD_CACHE[cache_key]
        if now - cache_time < ttl:
            return cached_val
    res = query_func()
    GLOBAL_DASHBOARD_CACHE[cache_key] = (now, res)
    return res

def fetch_formatted_events():
    all_events_raw = list(db.events.find({}).sort("event_date", 1))
    formatted = []
    for ev in all_events_raw:
        ev_copy = dict(ev)
        ev_copy["_id"] = str(ev_copy["_id"])
        ev_copy["event_date"] = normalize_date(ev_copy.get("event_date", ""))
        formatted.append(ev_copy)
    return formatted

def serialize_doc(doc):
    if not doc:
        return doc
    d = dict(doc)
    if '_id' in d:
        d['_id'] = str(d['_id'])
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, ObjectId):
            d[k] = str(v)
        elif isinstance(v, list):
            d[k] = [serialize_doc(x) if isinstance(x, dict) else str(x) if isinstance(x, ObjectId) else x for x in v]
        elif isinstance(v, dict):
            d[k] = serialize_doc(v)
    return d

@app.route("/api/home_data", methods=["GET"])
def api_home_data():
    try:
        today_str = get_today_ist_string()
        
        all_events_raw = get_cached_dashboard_data('all_events', fetch_formatted_events, ttl=15)
        
        today_events = []; upcoming_events = []; all_upcoming = []
        for ev in all_events_raw:
            ev_copy = dict(ev)
            event_date = ev_copy.get("event_date", "")
            end_date   = normalize_date(ev_copy.get("end_date", "")) if ev_copy.get("end_date") else ""
            
            if not event_date: continue
            if end_date and event_date <= today_str <= end_date:
                today_events.append(ev_copy); all_upcoming.append(ev_copy)
            elif event_date == today_str:
                today_events.append(ev_copy); all_upcoming.append(ev_copy)
            elif event_date > today_str:
                upcoming_events.append(ev_copy); all_upcoming.append(ev_copy)
                
        ugc_records_raw = get_cached_dashboard_data('ugc_records', lambda: list(db.ugc_data.find().sort("uploaded_at",-1).limit(50)), ttl=15)
        
        serialized_records = [serialize_doc(r) for r in ugc_records_raw]
        serialized_today = [serialize_doc(e) for e in today_events]
        serialized_upcoming = [serialize_doc(e) for e in upcoming_events]
        serialized_all_upcoming = [serialize_doc(e) for e in all_upcoming]
        serialized_all_events = [serialize_doc(e) for e in all_events_raw]
        
        try:
            campus_highlights = get_cached_dashboard_data(
                'campus_gallery_home',
                lambda: [serialize_doc(d) for d in db.campus_gallery.find({}).sort([('date_happened',-1),('created_at',-1)]).limit(8)],
                ttl=15)
        except Exception:
            campus_highlights = []

        return jsonify({
            "success": True,
            "records": serialized_records,
            "campus_highlights": campus_highlights,
            "today_events": serialized_today,
            "upcoming_events": serialized_upcoming,
            "all_upcoming": serialized_all_upcoming,
            "all_events": serialized_all_events,
            "today": today_str
        })
    except Exception as e:
        logger.error(f"api_home_data error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  NOTIFICATION HELPERS
# ══════════════════════════════════════════════════════════════════════
import time
NOTIFICATIONS_CACHE = {} # key: email, value: (timestamp, notifications)

def get_user_notifications():
    try:
        if 'email' not in session: return []
        email = session['email']
        
        now = time.time()
        if email in NOTIFICATIONS_CACHE:
            cache_time, cached_val = NOTIFICATIONS_CACHE[email]
            if now - cache_time < 15: # Cache for 15 seconds
                return cached_val
        
        user = db.users.find_one({'email': email})
        if not user: return []
        notifications = []
        upcoming_reminders = list(db.event_reminders.find(
            {'user_id': user['_id'], 'sent': False}).sort('reminder_datetime',1).limit(5))
        for reminder in upcoming_reminders:
            event = db.events.find_one({'_id': reminder['event_id']})
            if event:
                notifications.append({
                    'type':'reminder','icon':'bell',
                    'title':f"Reminder: {event['event_name']}",
                    'message':f"Set for {reminder['reminder_datetime'].strftime('%d %b at %I:%M %p')}",
                    'time': reminder.get('created_at', get_indian_time()),
                    'link': url_for('jainevents')
                })
        subscriptions = list(db.event_subscriptions.find(
            {'user_id': user['_id']}).sort('subscribed_at',-1).limit(3))
        for sub in subscriptions:
            event = db.events.find_one({'_id': sub['event_id']})
            if event:
                notifications.append({
                    'type':'subscription','icon':'envelope',
                    'title':f"Subscribed to {event['event_name']}",
                    'message':f"Event on {event['event_date']}",
                    'time': sub.get('subscribed_at', get_indian_time()),
                    'link': url_for('jainevents')
                })
        recent_uploads = list(db.user_files.find(
            {'user_email': session['email']}).sort('uploaded_at',-1).limit(3))
        for upload in recent_uploads:
            notifications.append({
                'type':'file','icon':'file',
                'title':f"File uploaded: {upload['file_name']}",
                'message':f"Source: {upload.get('source','Local')}",
                'time': upload.get('uploaded_at', get_indian_time()),
                'link': url_for('my_files')
            })
        office_files = list(db.public_files.find().sort('uploaded_at',-1).limit(3))
        for file in office_files:
            notifications.append({
                'type':'office','icon':'building',
                'title':f"New Public File: {file['name']}",
                'message':'Uploaded by Office of Academics',
                'time': file.get('uploaded_at', get_indian_time()),
                'link': url_for('home')
            })
        if is_leader():
            shared_docs = list(db.document_shares.find(
                {'shared_with': user['_id']}).sort('shared_at',-1).limit(3))
            for share in shared_docs:
                sender = db.users.find_one({'_id': share['shared_by']})
                notifications.append({
                    'type':'share','icon':'share-alt',
                    'title':f"Document Shared: {share['document_name']}",
                    'message':f"From: {sender['email'].split('@')[0] if sender else 'Unknown'}",
                    'time': share.get('shared_at', get_indian_time()),
                    'link': url_for('leader_dashboard')
                })
        # unread direct messages
        unread_dms = db.direct_messages.count_documents({
            'receiver_id': user['_id'], 'read': False
        })
        if unread_dms > 0:
            notifications.append({
                'type':'message','icon':'comments',
                'title':f"You have {unread_dms} unread message(s)",
                'message':'Click Messages in the navbar to read',
                'time': get_indian_time(),
                'link': '#'
            })
        notifications.sort(key=lambda x: x['time'], reverse=True)
        res = notifications[:10]
        NOTIFICATIONS_CACHE[email] = (now, res)
        return res
    except Exception as e:
        logger.error(f"Notifications error: {e}")
        return []

# ══════════════════════════════════════════════════════════════════════
#  CONTEXT PROCESSORS
# ══════════════════════════════════════════════════════════════════════
@app.context_processor
def inject_notifications():
    try:
        if 'email' in session and session.get('role') == 'user':
            return dict(notifications=get_user_notifications())
    except:
        pass
    return dict(notifications=[])

@app.context_processor
def inject_user_navbar():
    try:
        if 'email' in session and session.get('role') == 'user':
            return dict(user_navbar=get_user_navbar(session['email']))
    except:
        pass
    return dict(user_navbar=[])

@app.context_processor
def inject_current_time():
    return dict(now=get_indian_time())

@app.context_processor
def inject_firebase_config():
    return dict(
        firebase_config={
            'api_key': os.getenv('FIREBASE_API_KEY'),
            'auth_domain': os.getenv('FIREBASE_AUTH_DOMAIN'),
            'project_id': os.getenv('FIREBASE_PROJECT_ID'),
            'storage_bucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
            'messaging_sender_id': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
            'app_id': os.getenv('FIREBASE_APP_ID'),
            'measurement_id': os.getenv('FIREBASE_MEASUREMENT_ID')
        }
    )

# ══════════════════════════════════════════════════════════════════════
#  EMAIL NOTIFICATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════
def send_microsite_email(subject, recipients, title, content_html, subtitle=None, cta_text=None, cta_url=None, status_type=None, status_text=None):
    try:
        try:
            url_root = request.url_root.rstrip('/')
        except Exception:
            url_root = "https://juooa.cloud"

        msg = Message(
            subject=subject,
            sender=app.config['MAIL_USERNAME'],
            recipients=recipients
        )
        
        # Attach logo
        try:
            with app.open_resource("static/images/jainu.png") as fp:
                msg.attach("jainu.png", "image/png", fp.read(), headers=[['Content-ID', '<jain_logo>']])
        except Exception as logo_err:
            logger.error(f"Failed to attach logo in send_microsite_email: {logo_err}")

        # Status banner configurations
        status_tr = ""
        if status_type and status_text:
            colors = {
                'success': ('#16a34a', '✅'),
                'info': ('#2563eb', 'ℹ️'),
                'warning': ('#d97706', '⚠️'),
                'error': ('#dc2626', '❌'),
                'rework': ('#ea580c', '🔄'),
                'pending': ('#4b5563', '⏳')
            }
            bg_color, icon = colors.get(status_type, ('#1e3a5f', '🔔'))
            status_tr = f"""
      <!-- ═══ STATUS BANNER ═══ -->
      <tr>
        <td style="background:{bg_color};padding:14px 48px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td valign="middle" style="width:24px;font-size:18px;line-height:1;color:#ffffff;">
                {icon}
              </td>
              <td valign="middle" style="padding-left:10px;">
                <p style="margin:0;color:#ffffff;font-size:14px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">
                  {status_text}
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
"""

        # CTA Button
        cta_tr = ""
        if cta_text and cta_url:
            full_cta_url = cta_url if cta_url.startswith('http') else f"{url_root}{cta_url}"
            cta_tr = f"""
          <!-- CTA BUTTON -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px;margin-bottom:8px;">
            <tr>
              <td align="center">
                <a href="{full_cta_url}"
                   style="display:inline-block;background:linear-gradient(135deg,#090e1a,#1a2a4a);color:#ffffff;
                          text-decoration:none;padding:14px 36px;border-radius:50px;font-size:14px;
                          font-weight:700;letter-spacing:0.5px;box-shadow:0 4px 16px rgba(9,14,26,0.3);">
                  {cta_text} &nbsp;→
                </a>
              </td>
            </tr>
          </table>
"""

        subtitle_html = f'<p style="margin:0 0 20px;color:#6b7280;font-size:14px;line-height:1.5;">{subtitle}</p>' if subtitle else ""

        msg.html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f8;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f8;padding:48px 16px;">
  <tr><td align="center">

    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 48px rgba(9,14,26,0.14);">

      <!-- ═══ HEADER ═══ -->
      <tr>
        <td style="background:#ffffff;padding:0;border-bottom:1px solid #e5e7eb;">
          <!-- top gold bar -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="height:4px;background:linear-gradient(90deg,#d97706,#f59e0b,#fbbf24,#f59e0b,#d97706);"></td></tr>
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 48px 24px;">
            <tr>
              <td align="left" valign="middle" width="95">
                <img src="cid:jain_logo"
                     alt="Jain University"
                     width="84" height="84"
                     style="display:block;border-radius:12px;object-fit:contain;padding:4px;">
              </td>
              <td valign="middle" style="padding-left:20px;">
                <p style="margin:0 0 3px;color:#d97706;font-size:10px;font-weight:800;letter-spacing:3.5px;text-transform:uppercase;">Office of Academics</p>
                <h1 style="margin:0;color:#090e1a;font-size:20px;font-weight:700;letter-spacing:0.3px;line-height:1.3;">Jain (Deemed-to-be University)</h1>
                <p style="margin:4px 0 0;color:#5e718d;font-size:11px;letter-spacing:1px;">OOA Microsite · Academic Excellence</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      {status_tr}

      <!-- ═══ BODY ═══ -->
      <tr>
        <td style="padding:40px 48px 32px;">
          <h2 style="margin:0 0 16px;color:#090e1a;font-size:20px;font-weight:700;line-height:1.3;">{title}</h2>
          {subtitle_html}
          <div style="font-size:15px;color:#374151;line-height:1.6;">
            {content_html}
          </div>
          {cta_tr}
        </td>
      </tr>

      <!-- ═══ FOOTER ═══ -->
      <tr>
        <td style="background:#f8fafc;border-top:1px solid #e5e7eb;padding:24px 48px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center">
                <p style="margin:0 0 6px;font-size:12px;color:#9ca3af;line-height:1.6;">
                  This is an automated notification from the OOA Microsite.<br>
                  Jain (Deemed-to-be University) · Office of Academics
                </p>
                <p style="margin:0;font-size:12px;">
                  <a href="mailto:officeofacademics@juooa.cloud"
                     style="color:#d97706;text-decoration:none;font-weight:600;">
                    officeofacademics@juooa.cloud
                  </a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- bottom gold bar -->
      <tr>
        <td style="height:4px;background:linear-gradient(90deg,#d97706,#f59e0b,#fbbf24,#f59e0b,#d97706);"></td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

        import re
        text_clean = re.sub('<[^<]+?>', '', content_html)
        msg.body = f"{title}\n\n{text_clean}\n\nVisit: {url_root}\n-- Office of Academics, Jain University"
        
        mail.send(msg)
        return True
    except Exception as e:
        logger.error(f"Error in send_microsite_email: {e}", exc_info=True)
        return False

def send_document_notification(sender, receiver, document, message):
    try:
        subject = f"📄 New Document for Review: {document['document_name']}"
        title = "New Document for Review"
        subtitle = f"From: {sender['email']}"
        content_html = f"""
        <strong>Document Name:</strong> {document['document_name']}<br>
        <strong>Description:</strong> {document.get('description','')}<br><br>
        <strong>Sender Message:</strong><br>
        {message}
        """
        send_microsite_email(
            subject=subject,
            recipients=[receiver['email']],
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            cta_text="View Dashboard",
            cta_url="/leader_dashboard",
            status_type="info",
            status_text="Document Pending Review"
        )
    except Exception as e:
        logger.error(f"Doc notification error: {e}")

def send_task_notification(sender, receiver, task_title, due_date, attachment_msg="", priority="medium", description=""):
    try:
        subject = f"📋 New Task Assigned: {task_title}"
        title = "New Task Assigned"
        subtitle = f"From: {sender['email'].split('@')[0]}"
        content_html = f"""
        <strong>Task Title:</strong> {task_title}<br>
        <strong>Due Date:</strong> {due_date}<br>
        <strong>Priority:</strong> <span style="text-transform:uppercase;font-weight:bold;">{priority}</span>{attachment_msg}<br><br>
        <strong>Description:</strong><br>
        {description}
        """
        send_microsite_email(
            subject=subject,
            recipients=[receiver['email']],
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            cta_text="View Dashboard",
            cta_url="/core_dashboard",
            status_type="info",
            status_text="Task Assigned"
        )
    except Exception as e:
        logger.error(f"Task notification error: {e}")

def send_review_reply(reviewer, recipient, document, comments, status):
    try:
        subject = f"{'✅' if status=='approved' else '❌'} Document Review: {document['document_name']}"
        title = "Document Review Complete"
        subtitle = f"Reviewed by: {reviewer['email']}"
        content_html = f"""
        <strong>Document:</strong> {document['document_name']}<br>
        <strong>Status:</strong> <span style="color:{'#16a34a' if status=='approved' else '#dc2626'};text-transform:uppercase;font-weight:bold;">{status}</span><br><br>
        <strong>Review Comments:</strong><br>
        {comments}
        """
        send_microsite_email(
            subject=subject,
            recipients=[recipient['email']],
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            cta_text="View Dashboard",
            cta_url="/core_dashboard",
            status_type="success" if status=="approved" else "error",
            status_text=f"Document {status.title()}"
        )
    except Exception as e:
        logger.error(f"Review reply error: {e}")

def send_chat_notification(sender, receiver, message_preview):
    try:
        subject = f"💬 New message from {sender['email'].split('@')[0]}"
        title = "New Chat Message"
        subtitle = f"From: {sender['email']}"
        content_html = f"""
        You have received a new message in your chat room:<br><br>
        <div style="background:#f3f4f6;border-left:4px solid #090e1a;padding:12px 16px;font-style:italic;color:#4b5563;border-radius:4px;">
          "{message_preview}..."
        </div>
        """
        send_microsite_email(
            subject=subject,
            recipients=[receiver['email']],
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            cta_text="Open Dashboard",
            cta_url="/core_dashboard",
            status_type="info",
            status_text="New Message"
        )
    except Exception as e:
        logger.error(f"Chat notification error: {e}")

def notify_group_chat(sender, message_preview):
    try:
        online_core = list(db.users.find({
            'is_online': True,
            '$or': [{'user_type':'core'},{'special_role':'office_barrier'}],
            'email': {'$ne': sender['email']}
        }))
        for member in online_core:
            send_chat_notification(sender, member, message_preview)
    except Exception as e:
        logger.error(f"Group chat notify error: {e}")

def send_newsletter_email(title, content, image_filename, recipients):
    try:
        msg = Message(subject=title, sender=app.config['MAIL_USERNAME'], recipients=recipients)
        msg.html = (f"<html><body><div style='max-width:600px;margin:0 auto;font-family:Arial,sans-serif'>"
                    f"<div style='background:#04043a;color:#FFD700;padding:20px;text-align:center'><h1>{title}</h1></div>"
                    f"<div style='padding:20px'>{content}</div>"
                    f"<div style='text-align:center;font-size:12px;color:#666;padding:20px'>Jain University - Office of Academics</div>"
                    f"</div></body></html>")
        if image_filename:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            if os.path.exists(image_path):
                with app.open_resource(image_path) as img:
                    msg.attach(image_filename, "image/jpeg", img.read())
        mail.send(msg)
        logger.info(f"Newsletter '{title}' sent to {len(recipients)} recipients")
    except Exception as e:
        logger.error(f"Newsletter email error: {e}")
        raise

def send_completion_notification(assigner, completer, task, comment, attachment_url=None):
    try:
        subject = f"✅ Task Completed: {task['title']}"
        title = "Task Completed"
        subtitle = f"Completed by: {completer['email'].split('@')[0]}"
        attachment_html = f'<br><strong>Attachment:</strong> <a href="{attachment_url}" style="color:#d97706;text-decoration:none;font-weight:bold;">View Attached File</a>' if attachment_url else ""
        content_html = f"""
        <strong>Task:</strong> {task['title']}<br>
        <strong>Progress:</strong> {task.get('progress',0)}%{attachment_html}<br><br>
        <strong>Completion Note:</strong><br>
        {comment if comment else 'Marked as completed.'}
        """
        send_microsite_email(
            subject=subject,
            recipients=[assigner['email']],
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            cta_text="Review Task",
            cta_url="/leader_dashboard",
            status_type="success",
            status_text="Task Completed"
        )
    except Exception as e:
        logger.error(f"Completion notification error: {e}")

def record_login(email):
    import uuid
    sid = str(uuid.uuid4())[:8]
    session['session_id'] = sid
    db.users.update_one({'email': email}, {
        '$set': {'last_login': datetime.utcnow(), 'last_seen': datetime.utcnow(),
                 'is_active': True, 'session_id': sid},
        '$inc': {'total_logins': 1}
    })

def record_logout(email):
    db.users.update_one({'email': email}, {
        '$set': {'is_active': False, 'last_seen': datetime.utcnow(), 'session_id': ''}
    })

# ══════════════════════════════════════════════════════════════════════
#  SCHEDULED REMINDERS
# ══════════════════════════════════════════════════════════════════════
def send_event_reminders():
    try:
        now = get_indian_time_aware()
        now_naive = make_timezone_naive(now)
        reminders = list(db.event_reminders.find({'sent': False, 'reminder_datetime': {'$lte': now_naive}}))
        logger.info(f"[REMINDER] Found {len(reminders)} pending")
        sent_count = 0
        for reminder in reminders:
            try:
                reminder_id = reminder['_id']
                event = db.events.find_one({'_id': reminder['event_id']})
                if not event:
                    db.event_reminders.update_one({'_id': reminder_id}, {'$set': {'sent': True, 'error': 'Event not found'}})
                    continue
                user = db.users.find_one({'_id': reminder['user_id']})
                if not user:
                    db.event_reminders.update_one({'_id': reminder_id}, {'$set': {'sent': True, 'error': 'User not found'}})
                    continue
                reminder_dt = reminder.get('reminder_datetime')
                if isinstance(reminder_dt, datetime):
                    if reminder_dt.tzinfo is None:
                        reminder_dt = IST.localize(reminder_dt)
                    else:
                        reminder_dt = reminder_dt.astimezone(IST)
                msg = Message(subject=f"🔔 Event Reminder: {event['event_name']}",
                              sender=app.config['MAIL_USERNAME'],
                              recipients=[user['email']])
                try:
                    with app.open_resource("static/images/jainu.png") as fp:
                        msg.attach("jainu.png", "image/png", fp.read(), headers=[['Content-ID', '<jain_logo>']])
                except Exception as logo_err:
                    logger.error(f"Failed to attach logo in reminder email: {logo_err}")

                try:
                    url_root = request.url_root.rstrip('/')
                except Exception:
                    url_root = "https://juooa.cloud"
                
                reminder_time_str = reminder_dt.strftime('%d %B %Y at %I:%M %p IST') if isinstance(reminder_dt, datetime) else ''
                user_name = user.get('name') or user['email'].split('@')[0].replace('.', ' ').title()
                event_time = event.get('event_time', 'All Day')
                
                msg.html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Event Reminder – {event['event_name']}</title></head>
<body style="margin:0;padding:0;background:#f4f6fa;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fa;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.10);">
        
        <!-- HEADER -->
        <tr>
          <td style="background:#ffffff;padding:36px 40px 24px;text-align:center;border-bottom:1px solid #e5e7eb;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center" style="padding-bottom:12px;">
                  <img src="cid:jain_logo" alt="Jain University" width="110" style="height:auto;">
                </td>
              </tr>
              <tr>
                <td align="center">
                  <p style="margin:0;color:#d97706;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">Office of Academics</p>
                  <h1 style="margin:6px 0 0;color:#090e1a;font-size:22px;font-weight:700;letter-spacing:0.5px;">Jain (Deemed-to-be University)</h1>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        
        <!-- REMINDER BADGE -->
        <tr>
          <td style="background:linear-gradient(90deg,#d97706,#f59e0b);padding:14px 40px;text-align:center;">
            <p style="margin:0;color:#ffffff;font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">
              🔔 &nbsp; Event Reminder
            </p>
          </td>
        </tr>
        
        <!-- BODY -->
        <tr>
          <td style="padding:36px 40px 28px;">
            <p style="margin:0 0 20px;font-size:16px;color:#374151;">Dear <strong>{user_name}</strong>,</p>
            <p style="margin:0 0 28px;font-size:15px;color:#6b7280;line-height:1.6;">
              This is a reminder for an upcoming event you registered interest in. Here are the details:
            </p>
            
            <!-- EVENT CARD -->
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1.5px solid #e5e7eb;border-radius:12px;overflow:hidden;margin-bottom:28px;">
              <tr>
                <td style="background:#090e1a;padding:16px 24px;">
                  <h2 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">{event['event_name']}</h2>
                </td>
              </tr>
              <tr>
                <td style="padding:24px;">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td width="32" valign="top" style="padding-bottom:14px;">
                        <span style="display:inline-block;width:28px;height:28px;background:#fef3c7;border-radius:6px;text-align:center;line-height:28px;font-size:14px;">📅</span>
                      </td>
                      <td style="padding-bottom:14px;padding-left:10px;">
                        <p style="margin:0;font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Date</p>
                        <p style="margin:4px 0 0;font-size:15px;color:#111827;font-weight:600;">{event['event_date']}</p>
                      </td>
                    </tr>
                    <tr>
                      <td width="32" valign="top" style="padding-bottom:14px;">
                        <span style="display:inline-block;width:28px;height:28px;background:#dbeafe;border-radius:6px;text-align:center;line-height:28px;font-size:14px;">🕐</span>
                      </td>
                      <td style="padding-bottom:14px;padding-left:10px;">
                        <p style="margin:0;font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Time</p>
                        <p style="margin:4px 0 0;font-size:15px;color:#111827;font-weight:600;">{event_time}</p>
                      </td>
                    </tr>
                    <tr>
                      <td width="32" valign="top" style="padding-bottom:4px;">
                        <span style="display:inline-block;width:28px;height:28px;background:#d1fae5;border-radius:6px;text-align:center;line-height:28px;font-size:14px;">📍</span>
                      </td>
                      <td style="padding-bottom:4px;padding-left:10px;">
                        <p style="margin:0;font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Venue</p>
                        <p style="margin:4px 0 0;font-size:15px;color:#111827;font-weight:600;">{event['venue']}</p>
                      </td>
                    </tr>
                  </table>
                  {f'<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0"><p style="margin:0;font-size:13.5px;color:#4b5563;line-height:1.7;">{event.get("description","")}</p>' if event.get('description') else ''}
                </td>
              </tr>
            </table>
            
            <!-- REMINDER TIME -->
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fef9f0;border:1px solid #fcd34d;border-radius:10px;margin-bottom:28px;">
              <tr>
                <td style="padding:14px 20px;">
                  <p style="margin:0;font-size:13px;color:#92400e;">
                    ⏰ &nbsp; <strong>Your reminder was scheduled for:</strong> {reminder_time_str}
                  </p>
                </td>
              </tr>
            </table>
            
            <!-- CTA -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center">
                  <a href="{url_root}/home" style="display:inline-block;background:linear-gradient(135deg,#090e1a,#1a2a4a);color:#ffffff;text-decoration:none;padding:14px 36px;border-radius:50px;font-size:14px;font-weight:700;letter-spacing:0.5px;">
                    View OOA Microsite &nbsp; →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        
        <!-- FOOTER -->
        <tr>
          <td style="background:#f8fafc;border-top:1px solid #e5e7eb;padding:24px 40px;text-align:center;">
            <p style="margin:0 0 6px;font-size:12px;color:#9ca3af;">This reminder was sent by the OOA Microsite – Jain (Deemed-to-be University)</p>
            <p style="margin:0;font-size:12px;color:#d1d5db;">© 2024 Office of Academics · <a href="mailto:officeofacademics@juooa.cloud" style="color:#d97706;text-decoration:none;">officeofacademics@juooa.cloud</a></p>
          </td>
        </tr>
        
      </table>
    </td></tr>
  </table>
</body>
</html>"""
                msg.body = f"""EVENT REMINDER

Event: {event['event_name']}
Date: {event['event_date']}
Time: {event_time}
Venue: {event['venue']}
{f"Description: {event.get('description','')}" if event.get('description') else ''}

Your reminder was scheduled for: {reminder_time_str}

Visit: {url_root}/home"""

                mail.send(msg)
                db.event_reminders.update_one({'_id': reminder_id},
                    {'$set': {'sent': True, 'sent_at': now_naive, 'email_sent': True}})
                sent_count += 1
            except Exception as e:
                logger.exception(f"Reminder send error {reminder.get('_id')}: {e}")
                db.event_reminders.update_one({'_id': reminder['_id']},
                    {'$set': {'last_error': str(e), 'last_attempt': now_naive,
                              'attempt_count': reminder.get('attempt_count', 0) + 1}})
        logger.info(f"[REMINDER] Sent: {sent_count}")
    except Exception as e:
        logger.error(f"[REMINDER SYSTEM ERROR] {e}")

# ══════════════════════════════════════════════════════════════════════
#  JAIN AI ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route("/api/ai/summarize", methods=["POST"])
@login_required
def ai_summarize():
    try:
        data        = request.get_json(force=True) or {}
        doc_name    = data.get("document_name", "Document")
        description = data.get("description", "")
        file_url    = data.get("file_url", "")
        file_text   = extract_text_from_file(file_url) if file_url else ""
        context     = file_text or description or "No content available."
        prompt = (f"You are an assistant for a university student organisation (OOA, Jain University).\n"
                  f"Summarize the following document concisely for a team member.\n\n"
                  f"Document name: {doc_name}\nContent:\n{context[:3000]}\n\n"
                  f"Provide:\n1. Main topic (1 sentence)\n2. Key points (3-5 bullet points)\n"
                  f"3. Action items, if any\n\nBe concise and professional. Plain text only.")
        summary = call_claude(prompt, max_tokens=800)
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        logger.error(f"[Jain AI] summarize error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/task-help", methods=["POST"])
@login_required
def ai_task_help():
    try:
        data        = request.get_json(force=True) or {}
        title       = data.get("title", "")
        description = data.get("description", "")
        due_date    = data.get("due_date", "")
        priority    = data.get("priority", "medium")
        prompt = (f"You are a helpful assistant for a university student organisation (OOA, Jain University).\n"
                  f"A core team member needs help completing this task:\n\n"
                  f"Task: {title}\nDescription: {description}\nDue date: {due_date}\nPriority: {priority}\n\n"
                  f"Give a clear, practical step-by-step plan to complete this task on time.\n"
                  f"Be specific and actionable. Include time estimates if helpful. Plain text only.")
        help_text = call_claude(prompt, max_tokens=900)
        return jsonify({"success": True, "help": help_text})
    except Exception as e:
        logger.error(f"[Jain AI] task-help error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/chat", methods=["POST"])
@login_required
def ai_chat():
    try:
        data       = request.get_json(force=True) or {}
        message    = data.get("message", "")
        task_title = data.get("task_title", "")
        task_desc  = data.get("task_desc", "")
        history    = data.get("history", [])
        system = (f"You are Jain AI, an AI assistant embedded in the Jain University OOA "
                  f"(Office of Academics) dashboard. You help core team members and leaders "
                  f"with tasks, document reviews, planning, and general questions.\n"
                  f"Current context — Task: {task_title}. Description: {task_desc}.\n"
                  f"Be concise, helpful, and professional. Use plain text without markdown.")
        messages = []
        for h in history[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": message})
        reply = call_claude_chat(messages, system=system, max_tokens=800)
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        logger.error(f"[Jain AI] chat error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/suggest-feedback", methods=["POST"])
@login_required
def ai_suggest_feedback():
    try:
        data         = request.get_json(force=True) or {}
        doc_name     = data.get("document_name", "")
        description  = data.get("description", "")
        submitted_by = data.get("submitted_by", "a core member")
        prompt = (f"You are a Jain University OOA leader reviewing a submitted document.\n\n"
                  f"Document: {doc_name}\nSubmitted by: {submitted_by}\nDescription: {description}\n\n"
                  f"Write professional, constructive feedback (150-200 words).\n"
                  f"- Be specific and actionable\n- Point out what is good and what needs improvement\n"
                  f"- Do NOT approve or reject — only provide feedback\n- Plain text, no markdown")
        feedback = call_claude(prompt, max_tokens=600)
        return jsonify({"success": True, "feedback": feedback})
    except Exception as e:
        logger.error(f"[Jain AI] suggest-feedback error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/suggest-task-desc", methods=["POST"])
@login_required
def ai_suggest_task_desc():
    try:
        data  = request.get_json(force=True) or {}
        title = data.get("title", "")
        prompt = (f"You are a Jain University OOA leader creating a task for a core team member.\n\n"
                  f"Task title: {title}\n\n"
                  f"Write a clear, detailed task description (3-5 sentences) that:\n"
                  f"- Explains what needs to be done\n- Mentions deliverables or outputs expected\n"
                  f"- Notes quality standards or guidelines\n- Is specific enough to act on\n\nPlain text only.")
        description = call_claude(prompt, max_tokens=400)
        return jsonify({"success": True, "description": description})
    except Exception as e:
        logger.error(f"[Jain AI] suggest-task-desc error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/analyze-task", methods=["POST"])
@login_required
def ai_analyze_task():
    try:
        data        = request.get_json(force=True) or {}
        title       = data.get("title", "")
        description = data.get("description", "")
        progress    = data.get("progress", 0)
        status      = data.get("status", "pending")
        prompt = (f"You are a Jain University OOA leader reviewing a task's progress.\n\n"
                  f"Task: {title}\nDescription: {description}\n"
                  f"Current progress: {progress}%\nStatus: {status}\n\n"
                  f"Provide a brief progress analysis (100-150 words):\n"
                  f"- Is the progress on track?\n- Any risks or concerns?\n"
                  f"- Recommendations (accept, request rework, follow up)?\n\nPlain text only.")
        analysis = call_claude(prompt, max_tokens=500)
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        logger.error(f"[Jain AI] analyze-task error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/suggest-rework-feedback", methods=["POST"])
@login_required
def ai_suggest_rework_feedback():
    try:
        data        = request.get_json(force=True) or {}
        title       = data.get("title", "")
        description = data.get("description", "")
        progress    = data.get("progress", 100)
        prompt = (f"You are a Jain University OOA leader requesting a rework on a completed task.\n\n"
                  f"Task: {title}\nDescription: {description}\nProgress reported: {progress}%\n\n"
                  f"Write specific, constructive rework instructions (100-150 words) that:\n"
                  f"- Clearly explain what was not satisfactory\n"
                  f"- State exactly what changes or additions are needed\n"
                  f"- Are respectful and professional in tone\n\nPlain text only.")
        feedback = call_claude(prompt, max_tokens=500)
        return jsonify({"success": True, "feedback": feedback})
    except Exception as e:
        logger.error(f"[Jain AI] suggest-rework-feedback error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ai/member-insight", methods=["POST"])
@login_required
def ai_member_insight():
    try:
        data     = request.get_json(force=True) or {}
        name     = data.get("name", "")
        email    = data.get("email", "")
        total    = data.get("total_documents", 0)
        pending  = data.get("pending", 0)
        approved = data.get("approved", 0)
        revision = data.get("revision", 0)
        prompt = (f"You are a Jain University OOA leader reviewing a core team member's performance.\n\n"
                  f"Member: {name} ({email})\n"
                  f"Documents submitted: {total}\nApproved: {approved}\n"
                  f"Pending: {pending}\nNeeds revision: {revision}\n\n"
                  f"Write a brief performance insight (100-150 words):\n"
                  f"- Highlight strengths\n- Note areas for improvement\n"
                  f"- Give 1-2 concrete suggestions for the leader\n\nPlain text, professional tone.")
        insight = call_claude(prompt, max_tokens=500)
        return jsonify({"success": True, "insight": insight})
    except Exception as e:
        logger.error(f"[Jain AI] member-insight error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ── NEW: AI dashboard stats summary ──
@app.route("/api/ai/dashboard-summary", methods=["POST"])
@login_required
def ai_dashboard_summary():
    """Generate an AI summary of the user's current dashboard stats."""
    try:
        data   = request.get_json(force=True) or {}
        stats  = data.get("stats", {})
        role   = data.get("role", "core")
        lines  = "\n".join(f"- {k.replace('_',' ').title()}: {v}" for k, v in stats.items())
        prompt = (f"You are Jain AI, assistant for Jain University OOA microsite.\n"
                  f"The user is a {role} team member. Here are their current dashboard stats:\n\n"
                  f"{lines}\n\n"
                  f"Give a concise (120-180 word) performance snapshot:\n"
                  f"1. Overall status (healthy/needs attention)\n"
                  f"2. Top 2 priorities right now\n"
                  f"3. One practical recommendation\n"
                  f"Be encouraging but honest. Plain text only.")
        summary = call_claude(prompt, max_tokens=500)
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        logger.error(f"[Jain AI] dashboard-summary error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect(url_for('index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('index'))
        if not email.endswith('@jainuniversity.ac.in'):
            flash('Only @jainuniversity.ac.in emails allowed', 'error')
            return redirect(url_for('index'))
        user = db.users.find_one({'email': email})
        stored_hash = user.get('password') if user else None
        if user and stored_hash and check_password_hash(stored_hash, password):
            session.clear()
            session['email']        = email
            session['role']         = user['role']
            session['user_type']    = user.get('user_type', 'faculty')
            session['special_role'] = user.get('special_role', None)
            session['approved']     = user.get('approved', False)
            session['user_id']      = str(user['_id'])
            session.permanent       = True
            profile = user.get('profile', {}) or {}
            session['user_department'] = user.get('department','') or profile.get('department','')
            session['user_location']   = user.get('location','') or profile.get('location','')
            
            user_name = user.get('name') or profile.get('name') or parse_name_from_email(email)
            user_photo = user.get('photo_url') or profile.get('photo_url') or f"https://ui-avatars.com/api/?name={user_name.replace(' ', '+')}&background=0A2A44&color=fff"
            session['user_name'] = user_name
            session['user_photo'] = user_photo
            
            db.users.update_one({'email': email},
                {'$set': {'is_online': True, 'last_seen': get_indian_time(), 'name': user_name, 'photo_url': user_photo, 'profile.name': user_name, 'profile.photo_url': user_photo}})
            db.activity_logs.insert_one({
                'user_id': user['_id'], 'user_email': email,
                'action': 'login', 'details': 'User logged in',
                'timestamp': get_indian_time(), 'ip_address': request.remote_addr
            })
            if user['role'] == 'admin':
                flash('✅ Welcome back, Admin!', 'success')
                return redirect(url_for('home'))
            else:
                if not user.get('approved', False):
                    flash('⏳ Account pending approval. Limited access.', 'warning')
                else:
                    if user.get('special_role') == 'leader':
                        flash('✅ Leader login successful!', 'success')
                    elif user.get('user_type') == 'core' or user.get('special_role') == 'office_barrier':
                        flash('✅ Core Team login successful!', 'success')
                    else:
                        flash('✅ Login successful!', 'success')
                return redirect(url_for('home'))
        else:
            flash('Invalid credentials', 'error')
            return redirect(url_for('index'))
    return redirect(url_for('index'))

@app.route('/login/google', methods=['POST'])
def login_google():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data received'}), 400
        
        token = data.get('idToken')
        if not token:
            return jsonify({'success': False, 'message': 'No ID token received'}), 400
            
        # Verify the Google ID token using Google Auth library
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        
        project_id = os.getenv('FIREBASE_PROJECT_ID')
        try:
            logger.info(f"Verifying Firebase ID token with project_id={project_id}")
            decoded_token = google_id_token.verify_firebase_token(
                token, 
                google_requests.Request(), 
                audience=project_id
            )
            email = decoded_token.get('email')
            name = decoded_token.get('name')
            picture = decoded_token.get('picture')
        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            try:
                decoded_token = google_id_token.verify_firebase_token(
                    token, 
                    google_requests.Request(), 
                    audience=None
                )
                email = decoded_token.get('email')
                name = decoded_token.get('name')
                picture = decoded_token.get('picture')
                logger.info(f"Token verified successfully without audience restriction. Token aud: {decoded_token.get('aud')}")
            except Exception as e2:
                logger.error(f"Fallback token verification failed: {e2}")
                return jsonify({'success': False, 'message': f'Invalid Google Token: {e2}'}), 400
            
        if not email:
            return jsonify({'success': False, 'message': 'Email not found in Google profile'}), 400
            
        # Check domain
        if not email.endswith('@jainuniversity.ac.in'):
            return jsonify({'success': False, 'message': 'Only @jainuniversity.ac.in emails allowed'}), 400
            
        # Find user
        user = db.users.find_one({'email': email})
        is_new = False
        
        if not user:
            is_new = True
            # New user registration: check pre-assigned leader / core
            assigned_leader = db.pre_assigned_leaders.find_one({'email': email})
            assigned_core   = db.pre_assigned_core.find_one({'email': email})
            
            if assigned_leader:
                role = 'user'
                user_type = 'faculty'
                special_role = 'leader'
                approved = True
                db.pre_assigned_leaders.delete_one({'email': email})
            elif assigned_core:
                role = 'user'
                user_type = 'core'
                special_role = 'office_barrier'
                approved = True
                db.pre_assigned_core.delete_one({'email': email})
            else:
                role = 'user'
                user_type = 'faculty'
                special_role = None
                approved = False  # requires admin approval
                
            # Create user document
            user_doc = {
                'email': email,
                'name': name,
                'photo_url': picture,
                'role': role,
                'user_type': user_type,
                'special_role': special_role,
                'approved': approved,
                'is_online': True,
                'last_seen': get_indian_time(),
                'department': '',
                'location': '',
                'profile': {
                    'department': '',
                    'location': '',
                    'school': '',
                    'phone': '',
                    'name': name,
                    'photo_url': picture
                },
                'created_at': get_indian_time()
            }
            db.users.insert_one(user_doc)
            user = db.users.find_one({'email': email})
        else:
            # Update user profile information with latest Google details
            update_fields = {
                'name': name,
                'photo_url': picture,
                'is_online': True,
                'last_seen': get_indian_time()
            }
            db.users.update_one({'email': email}, {
                '$set': update_fields
            })
            db.users.update_one({'email': email}, {
                '$set': {
                    'profile.name': name,
                    'profile.photo_url': picture
                }
            })
            
        # Log activity
        db.activity_logs.insert_one({
            'user_id': user['_id'],
            'user_email': email,
            'action': 'login_google',
            'details': 'User logged in via Google Auth',
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        
        # Setup session
        session.clear()
        session['email'] = email
        session['role'] = user['role']
        session['user_type'] = user.get('user_type', 'faculty')
        session['special_role'] = user.get('special_role', None)
        session['approved'] = user.get('approved', False)
        session['user_id'] = str(user['_id'])
        session['user_name'] = name
        session['user_photo'] = picture
        session['user_department'] = user.get('department') or (user.get('profile') or {}).get('department', '')
        session['user_location'] = user.get('location') or (user.get('profile') or {}).get('location', '')
        session.permanent = True
        
        # Check if missing department or location
        needs_setup = not session['user_department'] or not session['user_location']
        
        return jsonify({
            'success': True,
            'needs_setup': needs_setup,
            'approved': session['approved'],
            'role': session['role'],
            'is_new': is_new,
            'redirect': url_for('home')
        })
        
    except Exception as e:
        logger.error(f"Error in Google Login API: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/complete-profile', methods=['POST'])
@login_required
def complete_profile():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data received'}), 400
        
        department = data.get('department', '').strip()
        location = data.get('location', '').strip()
        
        if not department or not location:
            return jsonify({'success': False, 'message': 'Department and Campus are required'}), 400
            
        email = session['email']
        db.users.update_one({'email': email}, {
            '$set': {
                'department': department,
                'location': location,
                'profile.department': department,
                'profile.location': location
            }
        })
        
        session['user_department'] = department
        session['user_location'] = location
        
        return jsonify({'success': True, 'message': 'Profile completed successfully'})
    except Exception as e:
        logger.error(f"Error completing profile: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/logout')
def logout():
    if 'email' in session:
        db.users.update_one({'email': session['email']},
            {'$set': {'is_online': False, 'last_seen': get_indian_time()}})
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('home'))
    firebase_config = {
        'api_key':             os.getenv('FIREBASE_API_KEY'),
        'auth_domain':         os.getenv('FIREBASE_AUTH_DOMAIN'),
        'project_id':          os.getenv('FIREBASE_PROJECT_ID'),
        'storage_bucket':      os.getenv('FIREBASE_STORAGE_BUCKET'),
        'messaging_sender_id': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        'app_id':              os.getenv('FIREBASE_APP_ID'),
        'measurement_id':      os.getenv('FIREBASE_MEASUREMENT_ID'),
    }
    
    # Fetch today's events for the landing page
    today_str = get_today_ist_string()
    all_events_raw = list(db.events.find({}).sort("event_date", 1))
    today_events = []
    for ev in all_events_raw:
        ev["_id"]       = str(ev["_id"])
        event_date      = normalize_date(ev.get("event_date", ""))
        end_date        = normalize_date(ev.get("end_date", "")) if ev.get("end_date") else ""
        ev["event_date"]= event_date
        if not event_date: continue
        if end_date and event_date <= today_str <= end_date:
            today_events.append(ev)
        elif event_date == today_str:
            today_events.append(ev)
            
    return render_template('index.html', firebase_config=firebase_config, today_events=today_events)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'step' not in session:
        session['step'] = 1
    if request.method == 'POST':
        if session['step'] == 1:
            email = request.form.get('email')
            if not email.endswith('@jainuniversity.ac.in'):
                flash('Only @jainuniversity.ac.in emails allowed', 'error')
                return redirect(url_for('register'))
            if db.users.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            otp = str(random.randint(100000, 999999))
            session['email'] = email
            session['otp']   = otp
            try:
                content_html = f"""
                Hello,<br><br>
                Thank you for registering on the OOA Microsite.<br>
                Your One-Time Password (OTP) for verification is:<br><br>
                <div style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#090e1a;text-align:center;padding:16px;background:#f3f4f6;border-radius:10px;margin:20px 0;">
                  {otp}
                </div>
                Please enter this code on the registration page to complete your registration. This code is valid for this session only.<br><br>
                If you did not initiate this request, please ignore this email.
                """
                send_microsite_email(
                    subject="Your OTP for Registration",
                    recipients=[email],
                    title="Account Verification OTP",
                    content_html=content_html,
                    status_type="info",
                    status_text="Verification Pending"
                )
                session['step'] = 2
                flash('OTP sent to your email.', 'info')
            except Exception as e:
                logger.error(f"OTP send error: {e}")
                flash('Error sending OTP. Please try again.', 'error')
            return redirect(url_for('register'))
        elif session['step'] == 2:
            if request.form.get('otp') == session.get('otp'):
                session['otp_verified'] = True
                session['step'] = 3
                flash('OTP verified. Set your password.', 'success')
            else:
                flash('Invalid OTP.', 'error')
            return redirect(url_for('register'))
        elif session['step'] == 3:
            password   = request.form.get('password')
            department = request.form.get('department', '').strip()
            location   = request.form.get('location', '').strip()
            if not department:
                flash('Please select your department.', 'error')
                return redirect(url_for('register'))
            if not location:
                flash('Please select your campus.', 'error')
                return redirect(url_for('register'))
            email = session['email']
            assigned_leader = db.pre_assigned_leaders.find_one({'email': email})
            assigned_core   = db.pre_assigned_core.find_one({'email': email})
            hashed_pw = generate_password_hash(password)
            parsed_name = parse_name_from_email(email)
            default_photo = f"https://ui-avatars.com/api/?name={parsed_name.replace(' ', '+')}&background=0A2A44&color=fff"
            if assigned_leader:
                db.users.insert_one({
                    'email': email, 'password': hashed_pw, 'role': 'user',
                    'user_type': 'faculty', 'special_role': 'leader', 'approved': True,
                    'is_online': True, 'last_seen': get_indian_time(),
                    'department': department, 'location': location,
                    'name': parsed_name, 'photo_url': default_photo,
                    'profile': {'department': department, 'location': location,
                                'school': assigned_leader.get('school',''), 'phone': '',
                                'name': parsed_name, 'photo_url': default_photo},
                    'created_at': get_indian_time()
                })
                db.pre_assigned_leaders.delete_one({'email': email})
                flash('✅ Registered as Leader! Please log in.', 'success')
            elif assigned_core:
                db.users.insert_one({
                    'email': email, 'password': hashed_pw, 'role': 'user',
                    'user_type': 'core', 'special_role': 'office_barrier', 'approved': True,
                    'is_online': True, 'last_seen': get_indian_time(),
                    'department': department, 'location': location,
                    'name': parsed_name, 'photo_url': default_photo,
                    'profile': {'department': department, 'location': location,
                                'school': assigned_core.get('department',''), 'phone': '',
                                'name': parsed_name, 'photo_url': default_photo},
                    'created_at': get_indian_time()
                })
                db.pre_assigned_core.delete_one({'email': email})
                flash('✅ Registered as Core Team member! Please log in.', 'success')
            else:
                db.users.insert_one({
                    'email': email, 'password': hashed_pw, 'role': 'user',
                    'user_type': 'faculty', 'special_role': None, 'approved': False,
                    'is_online': True, 'last_seen': get_indian_time(),
                    'department': department, 'location': location,
                    'name': parsed_name, 'photo_url': default_photo,
                    'profile': {'department': department, 'location': location,
                                'school': '', 'phone': '',
                                'name': parsed_name, 'photo_url': default_photo},
                    'created_at': get_indian_time()
                })
                flash('✅ Registration complete! Awaiting admin approval.', 'info')
            return redirect(url_for('login'))
    otp_sent     = session.get('step', 1) >= 2
    otp_verified = session.get('step', 1) == 3
    return render_template('register.html', otp_sent=otp_sent, otp_verified=otp_verified, campuses=get_all_campuses())

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email is required', 'error')
            return redirect(url_for('forgot_password'))
        user = db.users.find_one({'email': email})
        if not user:
            flash('Email not registered.', 'error')
            return redirect(url_for('forgot_password'))
        otp    = str(random.randint(100000, 999999))
        now    = get_indian_time_aware()
        expiry = make_timezone_naive(now + timedelta(minutes=10))
        db.password_resets.update_one({'email': email},
            {'$set': {'otp': otp, 'expiry': expiry, 'attempts': 0,
                      'verified': False, 'created_at': make_timezone_naive(now)}},
            upsert=True)
        try:
            content_html = f"""
            Hello,<br><br>
            We received a request to reset your password for your OOA Microsite account.<br>
            Your One-Time Password (OTP) to proceed is:<br><br>
            <div style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#090e1a;text-align:center;padding:16px;background:#f3f4f6;border-radius:10px;margin:20px 0;">
              {otp}
            </div>
            This OTP is valid for the next 10 minutes only.<br><br>
            If you did not request a password reset, please ignore this email or contact support if you have concerns.
            """
            send_microsite_email(
                subject="🔐 Password Reset OTP - Jain University",
                recipients=[email],
                title="Password Reset Request",
                content_html=content_html,
                status_type="warning",
                status_text="Password Reset Initiated"
            )
            session['reset_email'] = email
            flash('OTP sent to your email.', 'success')
            return redirect(url_for('verify_reset_otp'))
        except Exception as e:
            logger.error(f"Reset OTP send error: {e}")
            flash('Error sending OTP. Please try again.', 'error')
    return render_template('forgot_password.html')

@app.route('/verify-reset-otp', methods=['GET', 'POST'])
def verify_reset_otp():
    if 'reset_email' not in session:
        flash('Please start the password reset process first.', 'error')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        otp   = request.form.get('otp')
        email = session.get('reset_email')
        record = db.password_resets.find_one({'email': email})
        if not record:
            flash('No reset request found.', 'error')
            return redirect(url_for('forgot_password'))
        attempts = record.get('attempts', 0)
        if attempts >= 3:
            flash('Too many failed attempts. Please request a new OTP.', 'error')
            db.password_resets.delete_one({'email': email})
            session.pop('reset_email', None)
            return redirect(url_for('forgot_password'))
        db.password_resets.update_one({'email': email}, {'$inc': {'attempts': 1}})
        expiry = record.get('expiry')
        if expiry:
            expiry_aware = IST.localize(expiry) if expiry.tzinfo is None else expiry
            if get_indian_time_aware() > expiry_aware:
                flash('OTP expired. Please request a new one.', 'error')
                db.password_resets.delete_one({'email': email})
                session.pop('reset_email', None)
                return redirect(url_for('forgot_password'))
        if record.get('otp') == otp:
            db.password_resets.update_one({'email': email}, {'$set': {'verified': True}})
            session['reset_verified'] = True
            flash('OTP verified. Set your new password.', 'success')
            return redirect(url_for('reset_password'))
        else:
            remaining = 3 - (attempts + 1)
            flash(f'Invalid OTP. {remaining} attempt(s) left.', 'error')
    return render_template('verify_otp.html')

@app.route('/resend-reset-otp')
def resend_reset_otp():
    if 'reset_email' not in session:
        flash('Please start the password reset process first.', 'error')
        return redirect(url_for('forgot_password'))
    email = session.get('reset_email')
    if not db.users.find_one({'email': email}):
        flash('Email not found.', 'error')
        session.pop('reset_email', None)
        return redirect(url_for('forgot_password'))
    otp    = str(random.randint(100000, 999999))
    now    = get_indian_time_aware()
    expiry = make_timezone_naive(now + timedelta(minutes=10))
    db.password_resets.update_one({'email': email},
        {'$set': {'otp': otp, 'expiry': expiry, 'attempts': 0,
                  'verified': False, 'created_at': make_timezone_naive(now)}},
        upsert=True)
    try:
        content_html = f"""
        Hello,<br><br>
        We received a request to resend your OTP for your OOA Microsite account password reset.<br>
        Your new One-Time Password (OTP) to proceed is:<br><br>
        <div style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#090e1a;text-align:center;padding:16px;background:#f3f4f6;border-radius:10px;margin:20px 0;">
          {otp}
        </div>
        This OTP is valid for the next 10 minutes only.<br><br>
        If you did not request this, please ignore this email.
        """
        send_microsite_email(
            subject="🔐 New Password Reset OTP - Jain University",
            recipients=[email],
            title="New Password Reset Request",
            content_html=content_html,
            status_type="warning",
            status_text="New Reset OTP Requested"
        )
        flash('New OTP sent.', 'success')
    except Exception as e:
        logger.error(f"Resend OTP error: {e}")
        flash('Error sending OTP.', 'error')
    return redirect(url_for('verify_reset_otp'))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_email' not in session or 'reset_verified' not in session:
        flash('Please complete OTP verification first.', 'error')
        return redirect(url_for('forgot_password'))
    email = session.get('reset_email')
    if request.method == 'POST':
        new_password     = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not new_password or not confirm_password:
            flash('Both fields are required', 'error')
            return redirect(url_for('reset_password'))
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password'))
        if len(new_password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return redirect(url_for('reset_password'))
        result = db.users.update_one({'email': email},
            {'$set': {'password': generate_password_hash(new_password), 'updated_at': get_indian_time()}})
        if result.modified_count > 0:
            user = db.users.find_one({'email': email})
            db.activity_logs.insert_one({
                'user_id': user['_id'] if user else None, 'user_email': email,
                'action': 'password_reset', 'details': 'Password reset via forgot password',
                'timestamp': get_indian_time(), 'ip_address': request.remote_addr
            })
            db.password_resets.delete_one({'email': email})
            session.pop('reset_email', None)
            session.pop('reset_verified', None)
            try:
                content_html = f"""
                Hello,<br><br>
                This email confirms that your password for the OOA Microsite has been successfully changed.<br><br>
                If you made this change, you can safely ignore this email. You can now log in using your new password.<br><br>
                <strong>Security Alert:</strong> If you did not authorize this change, please contact the Office of Academics immediately.
                """
                send_microsite_email(
                    subject="✅ Password Changed - Jain University",
                    recipients=[email],
                    title="Password Changed Successfully",
                    content_html=content_html,
                    cta_text="Log In Now",
                    cta_url="/login",
                    status_type="success",
                    status_text="Password Updated"
                )
            except:
                pass
            flash('✅ Password changed! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error updating password.', 'error')
    return render_template('reset_password.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not email.endswith('@jainuniversity.ac.in'):
            flash('Only @jainuniversity.ac.in emails allowed', 'error')
            return redirect(url_for('admin'))
        if db.users.find_one({'email': email}):
            flash('Email already registered', 'error')
            return redirect(url_for('admin'))
        db.users.insert_one({
            'email': email, 'password': generate_password_hash(password),
            'role': 'admin', 'user_type': 'admin', 'special_role': None,
            'approved': True, 'created_at': get_indian_time()
        })
        flash('✅ Admin registered. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('admin_register.html')

@app.route('/refresh_session')
def refresh_session():
    if 'email' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        user = db.users.find_one({'email': session['email']})
        if user:
            session['role']        = user['role']
            session['user_type']   = user.get('user_type', 'faculty')
            session['special_role']= user.get('special_role', None)
            session['approved']    = user.get('approved', False)
            session['user_id']     = str(user['_id'])
            return jsonify({'success': True, 'approved': session['approved'],
                            'special_role': session['special_role'],
                            'user_type': session['user_type']})
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  MAIN USER ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route("/about_jain")
def about_jain():
    try:
        today_str = get_today_ist_string()
        all_events_raw = get_cached_dashboard_data('all_events', fetch_formatted_events, ttl=15)
        today_events = []
        for ev in all_events_raw:
            ev_copy = dict(ev)
            event_date = ev_copy.get("event_date", "")
            end_date   = normalize_date(ev_copy.get("end_date", "")) if ev_copy.get("end_date") else ""
            
            if not event_date: continue
            # Add escaped fields for Javascript string literal safety
            ev_copy['event_name_js'] = ev_copy.get('event_name', '').replace("'", "\\'")
            ev_copy['venue_js'] = ev_copy.get('venue', '').replace("'", "\\'")
            
            if end_date and event_date <= today_str <= end_date:
                today_events.append(ev_copy)
            elif event_date == today_str:
                today_events.append(ev_copy)
    except Exception as e:
        today_events = []
        
    return render_template('about_jain.html', today_events=today_events, **_get_user_info())


@app.route("/home")
@login_required
def home():
    try:
        user      = db.users.find_one({"email": session["email"]})
        today_str = get_today_ist_string()
        
        user_type     = session.get("user_type", "faculty")
        special_role  = session.get("special_role", None)
        approved      = session.get("approved", False)
        can_upload    = approved and special_role in ["core","office_barrier","leader"]
        is_fac        = user_type == "faculty" and not special_role
        user_department = session.get("user_department", "")
        user_location   = session.get("user_location", "")
        if not user_department or not user_location:
            if user:
                profile = user.get("profile") or {}
                user_department = profile.get("department","") or user.get("department","")
                user_location   = profile.get("location","") or user.get("location","")
                session["user_department"] = user_department
                session["user_location"]   = user_location
        return render_template("home.html",
            records=[],
            monthly_records=[],
            newsletter_records=[],
            events=[], today_events=[],
            upcoming_events=[], all_events=[],
            today=today_str, public_files=[], user_logged_in=True,
            user_email=session.get("email",""), user_role=session.get("role",""),
            user_type=user_type, is_faculty=is_fac, can_upload=can_upload,
            approved=approved, special_role=special_role,
            user_department=user_department, user_location=user_location)
    except Exception as e:
        logger.error(f"Home route error: {e}", exc_info=True)
        flash("Error loading home page", "error")
        return redirect(url_for("login"))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/jainevents')
def jainevents():
    return redirect(url_for('home'))

@app.route('/monthlyengagement')
def monthlyengagement():
    events = list(db.monthly_engagement.find().sort('uploaded_at', -1))
    return render_template('monthly.html', monthly_records=events)

@app.route('/ugc')
def ugc():
    return render_template('ugc.html')

@app.route('/base_user.html')
def base_user():
    if 'role' not in session or session['role'] != 'user':
        flash('Please log in.', 'error')
        return redirect(url_for('login'))
    try:
        return render_template('base_user.html',
            notifications=get_user_notifications(),
            user_navbar=get_user_navbar(session['email']))
    except Exception as e:
        return render_template('base_user.html', notifications=[], user_navbar=[])

@app.route('/user')
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    return redirect(url_for('home'))

# ══════════════════════════════════════════════════════════════════════
#  CORE DASHBOARD
# ══════════════════════════════════════════════════════════════════════
@app.route('/core_dashboard')
@approval_required
def core_dashboard():
    if not is_core_member():
        flash('Access denied. Core team members only.', 'error')
        return redirect(url_for('home'))
    try:
        user = db.users.find_one({'email': session['email']})
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('home'))
        now            = get_indian_time_aware()
        now_naive      = make_timezone_naive(now)
        today_start_n  = make_timezone_naive(now.replace(hour=0,minute=0,second=0,microsecond=0))
        week_start_n   = make_timezone_naive((now - timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0))
        month_start_n  = make_timezone_naive(now.replace(day=1,hour=0,minute=0,second=0,microsecond=0))
        core_members = list(db.users.find({
            '$or':[{'user_type':'core'},{'special_role':'office_barrier'}],
            'approved': True}) or [])
        leaders = list(db.users.find({'special_role':'leader','approved':True}) or [])
        my_documents = list(db.office_documents.find({'user_id':user['_id']}).sort('submitted_at',-1) or [])
        faculty_docs = list(db.dept_repo_docs.find({'source': 'faculty'}).sort('uploaded_at', -1) or [])
        for fdoc in faculty_docs:
            fdoc['_id'] = str(fdoc['_id'])
            fuploader = db.users.find_one({'email': fdoc.get('uploaded_by')})
            if fuploader:
                fprofile = fuploader.get('profile') or {}
                fdoc['uploader_name'] = fuploader.get('name') or fprofile.get('name') or fdoc.get('uploaded_by').split('@')[0]
            else:
                fdoc['uploader_name'] = fdoc.get('uploaded_by').split('@')[0]
        total_docs     = len(my_documents)
        pending_count  = len([d for d in my_documents if d.get('status')=='pending'])
        approved_count = len([d for d in my_documents if d.get('status')=='approved'])
        revision_count = len([d for d in my_documents if d.get('status')=='revision'])
        rejected_count = len([d for d in my_documents if d.get('status')=='rejected'])
        docs_today     = db.office_documents.count_documents({'user_id':user['_id'],'submitted_at':{'$gte':today_start_n}})
        docs_this_week = db.office_documents.count_documents({'user_id':user['_id'],'submitted_at':{'$gte':week_start_n}})
        docs_this_month= db.office_documents.count_documents({'user_id':user['_id'],'submitted_at':{'$gte':month_start_n}})
        my_tasks = list(db.tasks.find({'assigned_to':user['_id']}).sort('created_at',-1) or [])
        for task in my_tasks:
            assigner = db.users.find_one({'_id': task['assigned_by']})
            task['assigned_by_name'] = assigner['email'].split('@')[0] if assigner else 'Unknown'
            task['progress']  = task.get('progress', 0)
            task['priority']  = task.get('priority', 'medium')
            task['status']    = task.get('status', 'pending')
            task['updates']   = task.get('updates', [])
            task['rework_comment'] = task.get('rework_comment', '')
            if task.get('due_date'):
                task['due_date_str'] = task['due_date'].strftime('%d %b %Y') if isinstance(task['due_date'], datetime) else str(task['due_date'])
            else:
                task['due_date_str'] = 'No due date'
        total_tasks        = len(my_tasks)
        pending_tasks      = len([t for t in my_tasks if t.get('status')=='pending'])
        in_progress_tasks  = len([t for t in my_tasks if t.get('status')=='in_progress'])
        completed_tasks    = len([t for t in my_tasks if t.get('status')=='completed'])
        high_priority_tasks= len([t for t in my_tasks if t.get('priority')=='high' and t.get('status')!='completed'])
        overdue_tasks      = len([t for t in my_tasks if t.get('due_date') and
                                   t.get('due_date') < now_naive and t.get('status') not in ['completed','accepted']])
        online_core = list(db.users.find({
            '$or':[{'user_type':'core'},{'special_role':'office_barrier'}],
            'approved': True, 'is_online': True}) or [])
        for member in core_members:
            if member.get('last_seen'):
                ls = member['last_seen']
                if isinstance(ls, datetime):
                    ls_aware = IST.localize(ls) if ls.tzinfo is None else ls
                    diff = now - ls_aware
                    if diff.days > 0:    member['last_seen_formatted'] = f"{diff.days}d ago"
                    elif diff.seconds//3600 > 0: member['last_seen_formatted'] = f"{diff.seconds//3600}h ago"
                    else: member['last_seen_formatted'] = f"{diff.seconds//60}m ago"
            else:
                member['last_seen_formatted'] = 'Never'
        recent_shares = []
        try:
            recent_shares = list(db.document_shares.find({
                '$or':[{'shared_by':user['_id']},{'shared_with':user['_id']}]
            }).sort('shared_at',-1).limit(10) or [])
            for share in recent_shares:
                sender = db.users.find_one({'_id': share['shared_by']})
                share['sender_name'] = sender['email'].split('@')[0] if sender else 'Unknown'
        except:
            recent_shares = []
        recent_activity = []
        for doc in my_documents[:5]:
            if doc.get('submitted_at'):
                recent_activity.append({'type':'document','title':doc['document_name'],
                    'time':doc['submitted_at'].strftime('%d %b, %I:%M %p'),
                    'status':doc.get('status','pending'),'icon':'file-upload','color':'blue'})
            if doc.get('reviewed_at'):
                recent_activity.append({'type':'document','title':doc['document_name'],
                    'time':doc['reviewed_at'].strftime('%d %b, %I:%M %p'),
                    'status':doc.get('status',''),'icon':'check-circle',
                    'color':'green' if doc['status']=='approved' else 'red'})
        for task in my_tasks[:5]:
            if task.get('created_at'):
                recent_activity.append({'type':'task','title':task['title'],
                    'time':task['created_at'].strftime('%d %b, %I:%M %p'),
                    'status':task.get('status','pending'),'icon':'tasks','color':'purple'})
        recent_activity.sort(key=lambda x: x['time'], reverse=True)
        return render_template('core_dashboard.html',
            user=user, core_members=core_members, leaders=leaders,
            my_documents=my_documents, my_tasks=my_tasks,
            faculty_docs=faculty_docs, faculty_docs_count=len(faculty_docs),
            pending_count=pending_count, approved_count=approved_count,
            revision_count=revision_count, rejected_count=rejected_count,
            total_docs=total_docs, docs_today=docs_today,
            docs_this_week=docs_this_week, docs_this_month=docs_this_month,
            total_tasks=total_tasks, pending_tasks=pending_tasks,
            in_progress_tasks=in_progress_tasks, completed_tasks=completed_tasks,
            high_priority_tasks=high_priority_tasks, overdue_tasks=overdue_tasks,
            recent_activity=recent_activity, online_core=online_core,
            recent_shares=recent_shares, chat_messages=[],
            now=get_indian_time())
    except Exception as e:
        logger.error(f"core_dashboard error: {e}", exc_info=True)
        flash('Error loading dashboard.', 'error')
        return render_template('core_dashboard.html',
            user={'email':session.get('email',''),'_id':'unknown'},
            core_members=[], leaders=[], my_documents=[], my_tasks=[],
            faculty_docs=[], faculty_docs_count=0,
            pending_count=0, approved_count=0, revision_count=0, rejected_count=0,
            total_docs=0, docs_today=0, docs_this_week=0, docs_this_month=0,
            total_tasks=0, pending_tasks=0, in_progress_tasks=0, completed_tasks=0,
            high_priority_tasks=0, overdue_tasks=0, recent_activity=[],
            online_core=[], recent_shares=[], chat_messages=[], now=get_indian_time())

@app.route('/upload_document', methods=['POST'])
@approval_required
def upload_document():
    if not is_core_member():
        return jsonify({'error': 'Access denied'}), 403
    try:
        user           = db.users.find_one({'email': session['email']})
        document_name  = request.form.get('document_name')
        description    = request.form.get('description')
        assigned_users = request.form.getlist('assigned_users')
        notify_users   = request.form.get('notify_users') == 'on'
        file           = request.files.get('file')
        file_url       = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
            name_part, ext_part = os.path.splitext(filename)
            unique_fn = f"{name_part}_{ts}{ext_part}"
            filepath  = os.path.join(app.config['UPLOAD_FOLDER'], unique_fn)
            file.save(filepath)
            file_url  = '/' + filepath.replace('\\', '/')
        if not assigned_users:
            all_users = (list(db.users.find({'special_role':'leader','approved':True})) +
                         list(db.users.find({'$or':[{'user_type':'core'},{'special_role':'office_barrier'}],'approved':True})))
            assigned_users = [str(u['_id']) for u in all_users]
        doc = {
            'user_id': user['_id'], 'user_email': session['email'],
            'document_name': document_name, 'description': description,
            'file_url': file_url,
            'assigned_reviewers': [ObjectId(uid) for uid in assigned_users],
            'status': 'pending', 'submitted_at': get_indian_time(),
            'reviewed_by': None, 'reviewed_at': None, 'comments': '', 'notified': False
        }
        result = db.office_documents.insert_one(doc)
        db.activity_logs.insert_one({
            'user_id': user['_id'], 'user_email': session['email'],
            'action': 'document_upload', 'details': f'Submitted: {document_name}',
            'timestamp': get_indian_time(), 'ip_address': request.remote_addr
        })
        if notify_users:
            for uid in assigned_users:
                reviewer = db.users.find_one({'_id': ObjectId(uid)})
                if reviewer and reviewer.get('email'):
                    try:
                        send_document_notification(user, reviewer,
                            {'document_name':document_name,'description':description,'_id':result.inserted_id},
                            description)
                    except Exception as e:
                        logger.error(f"Notify error: {e}")
            db.office_documents.update_one({'_id':result.inserted_id},{'$set':{'notified':True}})
        flash('✅ Document submitted successfully', 'success')
        return redirect(url_for('core_dashboard'))
    except Exception as e:
        logger.error(f"upload_document error: {e}")
        flash(f'Error submitting document: {str(e)[:100]}', 'error')
        return redirect(url_for('core_dashboard'))

# ══════════════════════════════════════════════════════════════════════
#  LEADER DASHBOARD
# ══════════════════════════════════════════════════════════════════════
@app.route('/leader_dashboard')
@approval_required
def leader_dashboard():
    if not is_leader():
        flash('Access denied. Leaders only.', 'error')
        return redirect(url_for('home'))
    try:
        user = db.users.find_one({'email': session['email']})
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('home'))
        my_assigned_documents = list(db.office_documents.find(
            {'assigned_reviewers': user['_id']}).sort('submitted_at',-1))
        now_aware = get_indian_time_aware()
        for doc in my_assigned_documents:
            if doc.get('status') == 'pending':
                sat = doc['submitted_at']
                sat_aware = IST.localize(sat) if sat.tzinfo is None else sat
                diff = now_aware - sat_aware
                doc['time_in_queue'] = f"{diff.days}d {diff.seconds//3600}h" if diff.days > 0 else f"{diff.seconds//3600}h"
            uploader = db.users.find_one({'_id': doc['user_id']})
            if uploader:
                doc['uploader_name']  = uploader['email'].split('@')[0]
                doc['uploader_email'] = uploader['email']
        shared_documents = []
        try:
            shared_documents = list(db.document_shares.find(
                {'shared_with': user['_id']}).sort('shared_at',-1))
            for share in shared_documents:
                sender = db.users.find_one({'_id': share['shared_by']})
                share['sender_name']  = sender['email'].split('@')[0] if sender else 'Unknown'
                share['sender_email'] = sender['email'] if sender else ''
                doc = db.office_documents.find_one({'_id': share['document_id']}) if share.get('document_id') else None
                share['file_url'] = doc.get('file_url') if doc else share.get('file_url')
        except Exception as e:
            logger.error(f"Shared docs error: {e}")
        assigned_tasks = []
        try:
            assigned_tasks = list(db.tasks.find({'assigned_by': user['_id']}).sort('created_at',-1))
            for task in assigned_tasks:
                assignee = db.users.find_one({'_id': task['assigned_to']})
                if assignee:
                    task['assigned_to_name'] = assignee['email'].split('@')[0]
                task['due_date_str'] = (task['due_date'].strftime('%d %b %Y')
                                        if isinstance(task.get('due_date'), datetime)
                                        else str(task.get('due_date','')))
        except Exception as e:
            logger.error(f"Assigned tasks error: {e}")
        core_members = list(db.users.find({
            '$or':[{'user_type':'core'},{'special_role':'office_barrier'}],'approved':True}))
        online_core = list(db.users.find({
            '$or':[{'user_type':'core'},{'special_role':'office_barrier'}],
            'approved':True,'is_online':True}))
        for member in core_members:
            member['doc_count'] = db.office_documents.count_documents({'user_id':member['_id']})
            if member.get('last_seen'):
                ls = member['last_seen']
                ls_aware = IST.localize(ls) if ls.tzinfo is None else ls
                diff = now_aware - ls_aware
                if diff.days > 0:   member['last_seen_formatted'] = f"{diff.days}d ago"
                elif diff.seconds//3600 > 0: member['last_seen_formatted'] = f"{diff.seconds//3600}h ago"
                else: member['last_seen_formatted'] = f"{diff.seconds//60}m ago"
            else:
                member['last_seen_formatted'] = "Never"
        leaders = list(db.users.find({'special_role':'leader','approved':True}))
        today_start_n = make_timezone_naive(now_aware.replace(hour=0,minute=0,second=0,microsecond=0))
        today_shared_count = db.document_shares.count_documents(
            {'shared_with':user['_id'],'shared_at':{'$gte':today_start_n}})
        pending_count = len([d for d in my_assigned_documents if d.get('status')=='pending'])
        faculty_docs = list(db.dept_repo_docs.find({'source': 'faculty'}).sort('uploaded_at', -1) or [])
        for fdoc in faculty_docs:
            fdoc['_id'] = str(fdoc['_id'])
            fuploader = db.users.find_one({'email': fdoc.get('uploaded_by')})
            if fuploader:
                fprofile = fuploader.get('profile') or {}
                fdoc['uploader_name'] = fuploader.get('name') or fprofile.get('name') or fdoc.get('uploaded_by').split('@')[0]
            else:
                fdoc['uploader_name'] = fdoc.get('uploaded_by').split('@')[0]
        return render_template('leader_dashboard.html',
            user=user, my_assigned_documents=my_assigned_documents,
            shared_documents=shared_documents, assigned_tasks=assigned_tasks,
            core_members=core_members, online_core=online_core, leaders=leaders,
            faculty_docs=faculty_docs, faculty_docs_count=len(faculty_docs),
            pending_count=pending_count, today_shared_count=today_shared_count,
            today_date=get_indian_time().strftime('%Y-%m-%d'), now=get_indian_time())
    except Exception as e:
        logger.error(f"leader_dashboard error: {e}", exc_info=True)
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('home'))

@app.route('/review_document/<document_id>', methods=['POST'])
@approval_required
def review_document(document_id):
    if not is_leader():
        return jsonify({'error': 'Access denied'}), 403
    try:
        user       = db.users.find_one({'email': session['email']})
        status     = request.form.get('status')
        comments   = request.form.get('comments', '')
        send_reply = request.form.get('send_reply') == 'on'
        db.office_documents.update_one({'_id': ObjectId(document_id)},
            {'$set': {'status': status, 'reviewed_by': user['_id'],
                      'reviewed_at': get_indian_time(), 'comments': comments}})
        doc      = db.office_documents.find_one({'_id': ObjectId(document_id)})
        uploader = db.users.find_one({'_id': doc['user_id']})
        if uploader and send_reply:
            try: send_review_reply(user, uploader, doc, comments, status)
            except Exception as e: logger.error(f"Review reply error: {e}")
        flash(f'✅ Document {status}', 'success')
        return redirect(url_for('leader_dashboard'))
    except Exception as e:
        logger.error(f"review_document error: {e}")
        flash(f'Error reviewing document: {str(e)[:100]}', 'error')
        return redirect(url_for('leader_dashboard'))

@app.route('/share_document_leader', methods=['POST'])
@approval_required
def share_document_leader():
    if not is_leader():
        return jsonify({'error': 'Access denied'}), 403
    try:
        user        = db.users.find_one({'email': session['email']})
        document_id = request.form.get('document_id')
        leader_ids  = request.form.getlist('leaders')
        core_ids    = request.form.getlist('core_members')
        message     = request.form.get('message', '').strip()
        file        = request.files.get('share_file')
        file_url    = None; file_name = None
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            n, e = os.path.splitext(filename)
            ufn  = f"share_{n}_{ts}{e}"
            fp   = os.path.join(app.config['UPLOAD_FOLDER'], ufn)
            file.save(fp)
            file_url  = '/' + fp.replace('\\', '/')
            file_name = filename
        recipient_ids = leader_ids + core_ids
        if not recipient_ids:
            flash('Please select at least one recipient', 'error')
            return redirect(url_for('leader_dashboard'))
        document_name = "Shared File"
        if document_id:
            document = db.office_documents.find_one({'_id': ObjectId(document_id)})
            if document:
                document_name = document['document_name']
                if not file_url: file_url = document.get('file_url')
        if not document_id and not file_url:
            flash('Please select a document or upload a file', 'error')
            return redirect(url_for('leader_dashboard'))
        share_data = {
            'document_id':     ObjectId(document_id) if document_id else None,
            'document_name':   document_name,
            'shared_by':       user['_id'],
            'shared_by_email': session['email'],
            'shared_with':     [ObjectId(rid) for rid in recipient_ids],
            'message':         message,
            'file_url':        file_url,
            'file_name':       file_name,
            'shared_at':       get_indian_time(),
            'status':          'sent'
        }
        result = db.document_shares.insert_one(share_data)
        for rid in recipient_ids:
            recipient = db.users.find_one({'_id': ObjectId(rid)})
            if recipient:
                send_document_notification(user, recipient,
                    {'document_name':document_name,'description':message,'_id':result.inserted_id}, message)
        flash('✅ Document shared successfully', 'success')
        return redirect(url_for('leader_dashboard'))
    except Exception as e:
        logger.error(f"share_document_leader error: {e}")
        flash(f'Error sharing document: {str(e)[:100]}', 'error')
        return redirect(url_for('leader_dashboard'))

# ══════════════════════════════════════════════════════════════════════
#  TASK ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route('/assign_task', methods=['POST'])
@approval_required
def assign_task():
    if not is_leader():
        return jsonify({'error': 'Access denied'}), 403
    try:
        user        = db.users.find_one({'email': session['email']})
        task_title  = request.form.get('task_title')
        description = request.form.get('description')
        due_date    = request.form.get('due_date')
        priority    = request.form.get('priority', 'medium')
        assigned_to = request.form.get('assigned_to')
        file        = request.files.get('task_file')
        file_url    = None; file_name = None
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            n, e = os.path.splitext(filename)
            ufn  = f"task_{n}_{ts}{e}"
            fp   = os.path.join(app.config['UPLOAD_FOLDER'], ufn)
            file.save(fp)
            file_url  = '/' + fp.replace('\\', '/')
            file_name = filename
        due_datetime = IST.localize(datetime.strptime(due_date, '%Y-%m-%d'))
        task = {
            'assigned_by':       user['_id'],
            'assigned_by_email': session['email'],
            'assigned_to':       ObjectId(assigned_to),
            'title':             task_title,
            'description':       description,
            'due_date':          make_timezone_naive(due_datetime),
            'priority':          priority,
            'status':            'pending',
            'progress':          0,
            'has_attachment':    file_url is not None,
            'attachment_url':    file_url,
            'attachment_name':   file_name,
            'updates':           [],
            'leader_comments':   [],
            'created_at':        get_indian_time(),
            'updated_at':        get_indian_time()
        }
        db.tasks.insert_one(task)
        db.activity_logs.insert_one({
            'user_id': user['_id'], 'user_email': session['email'],
            'action': 'task_assigned', 'details': f'Assigned task: {task_title}',
            'timestamp': get_indian_time(), 'ip_address': request.remote_addr
        })
        assigned_user = db.users.find_one({'_id': ObjectId(assigned_to)})
        if assigned_user:
            send_task_notification(user, assigned_user, task_title, due_date,
                                   " with attachment" if file_url else "",
                                   priority, description)
        flash('✅ Task assigned successfully', 'success')
        return redirect(url_for('leader_dashboard'))
    except Exception as e:
        logger.error(f"assign_task error: {e}")
        flash(f'Error assigning task: {str(e)[:100]}', 'error')
        return redirect(url_for('leader_dashboard'))

@app.route('/api/update_task_progress/<task_id>', methods=['POST'])
@login_required
def update_task_progress(task_id):
    try:
        if request.content_type and 'application/json' in request.content_type:
            data       = request.get_json(force=True) or {}
            progress   = int(data.get('progress', 0))
            status     = data.get('status', 'in_progress')
            comment    = data.get('comment', '')
            attachment = None
        else:
            progress   = int(request.form.get('progress', 0))
            status     = request.form.get('status', 'in_progress')
            comment    = request.form.get('comment', '')
            attachment = request.files.get('attachment')
        user = db.users.find_one({'email': session['email']})
        if not user: return jsonify({'success': False, 'error': 'User not found'}), 404
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task: return jsonify({'success': False, 'error': 'Task not found'}), 404
        if str(task['assigned_to']) != str(user['_id']):
            return jsonify({'success': False, 'error': 'Not assigned to this task'}), 403
        file_url = None; file_name = None
        if attachment and attachment.filename and allowed_file(attachment.filename):
            filename = secure_filename(attachment.filename)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            n, e = os.path.splitext(filename)
            ufn  = f"task_update_{n}_{ts}{e}"
            fp   = os.path.join(app.config['UPLOAD_FOLDER'], ufn)
            attachment.save(fp)
            file_url  = '/' + fp.replace('\\', '/')
            file_name = filename
        update_entry = {'progress': progress, 'status': status,
                        'comment': comment, 'timestamp': get_indian_time()}
        if file_url:
            update_entry['attachment_url']  = file_url
            update_entry['attachment_name'] = file_name
        set_data = {'progress': progress, 'status': status, 'updated_at': get_indian_time()}
        if file_url:
            set_data['latest_attachment_url']  = file_url
            set_data['latest_attachment_name'] = file_name
        db.tasks.update_one({'_id': ObjectId(task_id)},
            {'$set': set_data, '$push': {'updates': update_entry}})
        db.activity_logs.insert_one({
            'user_id': user['_id'], 'user_email': session['email'],
            'action': 'task_update',
            'details': f'Updated: {task["title"]} → {status} ({progress}%)',
            'timestamp': get_indian_time(), 'ip_address': request.remote_addr
        })
        if status == 'completed':
            assigner = db.users.find_one({'_id': task['assigned_by']})
            if assigner:
                try: send_completion_notification(assigner, user, task, comment, file_url)
                except Exception as e: logger.error(f"Completion notification error: {e}")
        return jsonify({'success': True,
                        'message': 'Task updated' + (' with attachment' if file_url else '')})
    except Exception as e:
        logger.error(f"update_task_progress error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/leader/accept_task/<task_id>', methods=['POST'])
@approval_required
def leader_accept_task(task_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        user = db.users.find_one({'email': session['email']})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task: return jsonify({'error': 'Task not found'}), 404
        if str(task['assigned_by']) != str(user['_id']): return jsonify({'error': 'Not authorized'}), 403
        db.tasks.update_one({'_id': ObjectId(task_id)},
            {'$set': {'status': 'accepted', 'accepted_at': get_indian_time(),
                      'accepted_by': user['_id'], 'updated_at': get_indian_time()}})
        assignee = db.users.find_one({'_id': task['assigned_to']})
        if assignee:
            try:
                subject = f"✅ Task Accepted: {task['title']}"
                title = "Task Accepted"
                subtitle = f"Accepted by: {user['email'].split('@')[0]}"
                content_html = f"Your task '<strong>{task['title']}</strong>' has been accepted by {user['email'].split('@')[0]}! Great work!"
                send_microsite_email(
                    subject=subject,
                    recipients=[assignee['email']],
                    title=title,
                    subtitle=subtitle,
                    content_html=content_html,
                    cta_text="View Dashboard",
                    cta_url="/core_dashboard",
                    status_type="success",
                    status_text="Task Accepted"
                )
            except Exception as e: logger.error(f"Accept task email error: {e}")
        return jsonify({'success': True, 'message': 'Task accepted successfully'})
    except Exception as e:
        logger.error(f"accept_task error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leader/request_rework/<task_id>', methods=['POST'])
@approval_required
def leader_request_rework(task_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        user = db.users.find_one({'email': session['email']})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task: return jsonify({'error': 'Task not found'}), 404
        if str(task['assigned_by']) != str(user['_id']): return jsonify({'error': 'Not authorized'}), 403
        data         = request.get_json(force=True) or {}
        comment      = data.get('comment', '').strip()
        new_due_date = data.get('new_due_date', '')
        if not comment: return jsonify({'error': 'Rework instructions are required'}), 400
        update_data = {
            'status': 'rework', 'rework_comment': comment,
            'rework_requested_at': get_indian_time(),
            'rework_by': user['_id'], 'progress': 0, 'updated_at': get_indian_time()
        }
        if new_due_date:
            new_date_obj = datetime.strptime(new_due_date, '%Y-%m-%d')
            if new_date_obj.date() < get_indian_time().date():
                return jsonify({'error': 'New due date cannot be in the past'}), 400
            update_data['due_date'] = make_timezone_naive(IST.localize(new_date_obj))
        update_entry = {'progress': 0, 'status': 'rework',
                        'comment': f'LEADER REWORK REQUEST: {comment}',
                        'timestamp': get_indian_time()}
        db.tasks.update_one({'_id': ObjectId(task_id)},
            {'$set': update_data, '$push': {'updates': update_entry}})
        assignee = db.users.find_one({'_id': task['assigned_to']})
        if assignee:
            try:
                subject = f"🔄 Rework Required: {task['title']}"
                title = "Rework Required"
                subtitle = f"Rework requested by: {user['email'].split('@')[0]}"
                due_info = f"<br><strong>New Due Date:</strong> {new_due_date}" if new_due_date else ""
                content_html = f"""
                <strong>Task Title:</strong> {task['title']}{due_info}<br><br>
                <strong>Instructions for Rework:</strong><br>
                {comment}
                """
                send_microsite_email(
                    subject=subject,
                    recipients=[assignee['email']],
                    title=title,
                    subtitle=subtitle,
                    content_html=content_html,
                    cta_text="View Dashboard",
                    cta_url="/core_dashboard",
                    status_type="rework",
                    status_text="Rework Requested"
                )
            except Exception as e: logger.error(f"Rework email error: {e}")
        return jsonify({'success': True, 'message': 'Rework requested successfully'})
    except Exception as e:
        logger.error(f"request_rework error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leader/reschedule_task/<task_id>', methods=['POST'])
@login_required
def leader_reschedule_task(task_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        user = db.users.find_one({'email': session['email']})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task: return jsonify({'error': 'Task not found'}), 404
        if str(task['assigned_by']) != str(user['_id']): return jsonify({'error': 'Not authorized'}), 403
        data         = request.get_json(force=True) or {}
        new_due_date = data.get('new_due_date', '')
        reason       = data.get('reason', '').strip()
        if not new_due_date: return jsonify({'error': 'New due date is required'}), 400
        new_date_obj = datetime.strptime(new_due_date, '%Y-%m-%d')
        if new_date_obj.date() < get_indian_time().date():
            return jsonify({'error': 'Date cannot be in the past'}), 400
        new_date_naive = make_timezone_naive(IST.localize(new_date_obj))
        update_entry = {
            'progress': task.get('progress', 0), 'status': task.get('status', 'pending'),
            'comment': f'Due date rescheduled to {new_due_date}' + (f'. Reason: {reason}' if reason else ''),
            'timestamp': get_indian_time()
        }
        db.tasks.update_one({'_id': ObjectId(task_id)},
            {'$set': {'due_date': new_date_naive, 'rescheduled_at': get_indian_time(),
                      'rescheduled_by': user['_id'], 'updated_at': get_indian_time()},
             '$push': {'updates': update_entry}})
        assignee = db.users.find_one({'_id': task['assigned_to']})
        if assignee:
            try:
                subject = f"📅 Task Rescheduled: {task['title']}"
                title = "Task Rescheduled"
                subtitle = f"Rescheduled by: {user['email'].split('@')[0]}"
                reason_html = f"<br><strong>Reason:</strong> {reason}" if reason else ""
                content_html = f"""
                Your task '<strong>{task['title']}</strong>' has been rescheduled.<br><br>
                <strong>New Due Date:</strong> {new_due_date}{reason_html}
                """
                send_microsite_email(
                    subject=subject,
                    recipients=[assignee['email']],
                    title=title,
                    subtitle=subtitle,
                    content_html=content_html,
                    cta_text="View Dashboard",
                    cta_url="/core_dashboard",
                    status_type="warning",
                    status_text="Task Rescheduled"
                )
            except Exception as e: logger.error(f"Reschedule email error: {e}")
        return jsonify({'success': True, 'message': 'Task rescheduled successfully'})
    except Exception as e:
        logger.error(f"reschedule_task error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leader/add_task_comment/<task_id>', methods=['POST'])
@approval_required
def leader_add_task_comment(task_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        user = db.users.find_one({'email': session['email']})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task: return jsonify({'error': 'Task not found'}), 404
        if str(task['assigned_by']) != str(user['_id']): return jsonify({'error': 'Not authorized'}), 403
        data    = request.get_json(force=True) or {}
        comment = data.get('comment', '').strip()
        if not comment: return jsonify({'error': 'Comment is required'}), 400
        comment_entry = {
            'comment': comment, 'commented_by': user['email'].split('@')[0],
            'timestamp': get_indian_time(), 'type': 'leader_comment'
        }
        db.tasks.update_one({'_id': ObjectId(task_id)},
            {'$push': {'leader_comments': comment_entry},
             '$set': {'updated_at': get_indian_time()}})
        assignee = db.users.find_one({'_id': task['assigned_to']})
        if assignee:
            try:
                subject = f"💬 New Comment: {task['title']}"
                title = "New Task Comment"
                subtitle = f"Commented by: {user['email'].split('@')[0]}"
                content_html = f"""
                You have a new comment on your task '<strong>{task['title']}</strong>':<br><br>
                <div style="background:#f3f4f6;border-left:4px solid #090e1a;padding:12px 16px;font-style:italic;color:#4b5563;border-radius:4px;">
                  "{comment}"
                </div>
                """
                send_microsite_email(
                    subject=subject,
                    recipients=[assignee['email']],
                    title=title,
                    subtitle=subtitle,
                    content_html=content_html,
                    cta_text="View Task",
                    cta_url="/core_dashboard",
                    status_type="info",
                    status_text="New Comment"
                )
            except Exception as e: logger.error(f"Comment email error: {e}")
        return jsonify({'success': True, 'message': 'Comment added'})
    except Exception as e:
        logger.error(f"add_task_comment error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leader/add_share_comment/<share_id>', methods=['POST'])
@approval_required
def leader_add_share_comment(share_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        user    = db.users.find_one({'email': session['email']})
        data    = request.get_json(force=True) or {}
        comment = data.get('comment', '').strip()
        if not comment: return jsonify({'error': 'Comment is required'}), 400
        db.document_shares.update_one(
            {'_id': ObjectId(share_id), 'shared_with': user['_id']},
            {'$set': {'leader_comment': comment,
                      'leader_comment_at': get_indian_time(),
                      'leader_comment_by': user['email']}})
        return jsonify({'success': True, 'message': 'Comment saved'})
    except Exception as e:
        logger.error(f"add_share_comment error: {e}")
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  ACTIVITY STATUS
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/activity/status')
@login_required
def get_activity_status():
    try:
        user = db.users.find_one({'email': session['email']})
        if not user: return jsonify({'error': 'User not found'}), 404
        now   = get_indian_time_aware()
        five_n= make_timezone_naive(now - timedelta(minutes=5))
        new_tasks    = db.tasks.count_documents({'assigned_to':user['_id'],'created_at':{'$gte':five_n},'status':'pending'})
        new_documents= db.document_shares.count_documents({'shared_with':user['_id'],'shared_at':{'$gte':five_n}})
        overdue_tasks= db.tasks.count_documents({'assigned_to':user['_id'],'due_date':{'$lt':five_n},'status':{'$ne':'completed'}})
        updated_tasks = 0
        if is_leader():
            updated_tasks = db.tasks.count_documents({'assigned_by':user['_id'],'updated_at':{'$gte':five_n},'status':{'$in':['in_progress','completed']}})
        unread_messages = db.direct_messages.count_documents({'receiver_id':user['_id'],'read':False})
        db.users.update_one({'_id':user['_id']},{'$set':{'last_seen':get_indian_time()}})
        return jsonify({'success':True,'new_tasks':new_tasks,'new_documents':new_documents,
                        'overdue_tasks':overdue_tasks,'updated_tasks':updated_tasks,
                        'unread_messages': unread_messages,
                        'timestamp':get_indian_time().strftime('%Y-%m-%d %H:%M:%S')})
    except Exception as e:
        logger.error(f"activity_status error: {e}")
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  ANALYTICS
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/core-member/analytics/<member_id>')
@approval_required
def core_member_analytics(member_id):
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        member    = db.users.find_one({'_id': ObjectId(member_id)})
        if not member: return jsonify({'error': 'Member not found'}), 404
        documents = list(db.office_documents.find({'user_id':member['_id']}).sort('submitted_at',-1))
        total     = len(documents)
        pending   = len([d for d in documents if d.get('status')=='pending'])
        approved  = len([d for d in documents if d.get('status')=='approved'])
        revision  = len([d for d in documents if d.get('status')=='revision'])
        rejected  = len([d for d in documents if d.get('status')=='rejected'])
        recent_activity = []
        for doc in documents[:5]:
            recent_activity.append({
                'description': f"Submitted: {doc['document_name']}",
                'time': doc['submitted_at'].strftime('%d %b %Y, %I:%M %p'),
                'icon': 'file-alt', 'color': 'blue'
            })
        docs_list = []
        for doc in documents:
            docs_list.append({
                'name': doc['document_name'],
                'submitted': doc['submitted_at'].strftime('%d %b %Y'),
                'status': doc['status'],
                'file_url': doc.get('file_url', '#')
            })
        last_seen = member['last_seen'].strftime('%d %b %Y, %I:%M %p') if member.get('last_seen') else 'Never'
        return jsonify({
            'email': member['email'], 'name': member['email'].split('@')[0],
            'is_online': member.get('is_online', False), 'last_seen': last_seen,
            'total_documents': total, 'pending': pending, 'approved': approved,
            'revision': revision, 'rejected': rejected,
            'recent_activity': recent_activity[:10], 'documents': docs_list
        })
    except Exception as e:
        logger.error(f"core_member_analytics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents/by-date')
@approval_required
def documents_by_date():
    if not is_leader(): return jsonify({'error': 'Access denied'}), 403
    try:
        date_str    = request.args.get('date')
        if not date_str: return jsonify({'error': 'Date required'}), 400
        filter_date = IST.localize(datetime.strptime(date_str, '%Y-%m-%d'))
        next_day    = filter_date + timedelta(days=1)
        documents   = list(db.office_documents.find({
            'submitted_at': {'$gte': make_timezone_naive(filter_date),
                             '$lt':  make_timezone_naive(next_day)}
        }))
        return jsonify({
            'total':    len(documents),
            'approved': len([d for d in documents if d.get('status')=='approved']),
            'pending':  len([d for d in documents if d.get('status')=='pending']),
            'revision': len([d for d in documents if d.get('status')=='revision']),
            'rejected': len([d for d in documents if d.get('status')=='rejected'])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  OFFICE DOCUMENTS
# ══════════════════════════════════════════════════════════════════════
@app.route('/office_documents')
def office_documents():
    if not is_core_or_leader():
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    try:
        documents = list(db.office_documents.find().sort('submitted_at', -1))
        for doc in documents:
            u = db.users.find_one({'_id': doc['user_id']})
            if u:
                doc['user_name'] = u['email'].split('@')[0]
                doc['user_type'] = u.get('user_type', 'N/A')
        online_users = list(db.users.find({'special_role':'office_barrier','is_online':True}))
        return render_template('office_documents.html', documents=documents, online_users=online_users)
    except Exception as e:
        logger.error(f"office_documents error: {e}")
        flash('Error loading documents', 'error')
        return redirect(url_for('home'))

@app.route('/activity_logs')
def activity_logs():
    if not is_core_or_leader():
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    try:
        logs = list(db.activity_logs.find().sort('timestamp',-1).limit(100))
        online_users = list(db.users.find({'is_online':True}, {'email':1,'user_type':1,'special_role':1}))
        return render_template('activity_logs.html', logs=logs, online_users=online_users)
    except Exception as e:
        logger.error(f"activity_logs error: {e}")
        flash('Error loading logs', 'error')
        return redirect(url_for('home'))

# ══════════════════════════════════════════════════════════════════════
#  CHAT API (Group / Core Team)
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/chat/messages')
@login_required
def get_chat_messages():
    try:
        user = db.users.find_one({'email': session['email']})
        messages = list(db.chat_messages.find({
            '$or':[{'sender_id':user['_id']},{'receiver_id':user['_id']},{'group_id':'core_team'}]
        }).sort('timestamp',-1).limit(100))
        formatted = []
        for msg in reversed(messages):
            sender = db.users.find_one({'_id': msg['sender_id']})
            ts = msg.get('timestamp')
            ts_str = ''
            if ts:
                ts_aware = IST.localize(ts) if ts.tzinfo is None else ts
                ts_str   = ts_aware.strftime('%I:%M %p')
            formatted.append({
                'id':           str(msg['_id']),
                'sender_id':    str(msg['sender_id']),
                'sender_name':  sender['email'].split('@')[0] if sender else 'Unknown',
                'sender_email': sender['email'] if sender else '',
                'content':      msg.get('content',''),
                'file_url':     msg.get('file_url'),
                'document_id':  str(msg['document_id']) if msg.get('document_id') else None,
                'timestamp':    ts_str,
                'is_me':        msg['sender_id'] == user['_id']
            })
        return jsonify({'success': True, 'messages': formatted})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    try:
        user        = db.users.find_one({'email': session['email']})
        data        = request.get_json(force=True) or {}
        content     = data.get('content','').strip()
        receiver_id = data.get('receiver_id')
        file_url    = data.get('file_url')
        document_id = data.get('document_id')
        if not content and not file_url and not document_id:
            return jsonify({'error': 'Message content, file, or document required'}), 400
        message = {
            'sender_id':   user['_id'],
            'receiver_id': ObjectId(receiver_id) if receiver_id else None,
            'group_id':    'core_team' if not receiver_id else None,
            'content':     content,
            'file_url':    file_url,
            'document_id': ObjectId(document_id) if document_id else None,
            'timestamp':   get_indian_time(),
            'read':        False
        }
        result = db.chat_messages.insert_one(message)
        if receiver_id:
            receiver = db.users.find_one({'_id': ObjectId(receiver_id)})
            if receiver and receiver.get('email'):
                send_chat_notification(user, receiver, content[:50])
        else:
            notify_group_chat(user, content[:50])
        return jsonify({'success': True, 'message_id': str(result.inserted_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  DIRECT MESSAGES API (Navbar messaging)
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/dm/send', methods=['POST'])
@login_required
def send_direct_message():
    """Send a direct message to a specific user."""
    try:
        sender      = db.users.find_one({'email': session['email']})
        data        = request.get_json(force=True) or {}
        receiver_id = data.get('receiver_id')
        content     = data.get('content', '').strip()
        if not content: return jsonify({'error': 'Message content required'}), 400
        receiver = db.users.find_one({'_id': ObjectId(receiver_id)}) if receiver_id else None
        msg = {
            'sender_id':   sender['_id'],
            'sender_email':session['email'],
            'receiver_id': ObjectId(receiver_id) if receiver_id else None,
            'content':     content,
            'timestamp':   get_indian_time(),
            'read':        False
        }
        db.direct_messages.insert_one(msg)
        if receiver:
            try: send_chat_notification(sender, receiver, content[:50])
            except: pass
        return jsonify({'success': True, 'message': 'Message sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dm/messages')
@login_required
def get_direct_messages():
    """Get direct messages for current user."""
    try:
        user = db.users.find_one({'email': session['email']})
        # mark received as read
        db.direct_messages.update_many(
            {'receiver_id': user['_id'], 'read': False},
            {'$set': {'read': True}}
        )
        messages = list(db.direct_messages.find({
            '$or': [{'sender_id': user['_id']}, {'receiver_id': user['_id']}]
        }).sort('timestamp', -1).limit(50))
        formatted = []
        for msg in reversed(messages):
            sender = db.users.find_one({'_id': msg['sender_id']})
            ts = msg.get('timestamp')
            ts_str = ts.strftime('%d %b, %I:%M %p') if ts else ''
            formatted.append({
                'id':           str(msg['_id']),
                'sender_name':  sender['email'].split('@')[0] if sender else 'Unknown',
                'sender_email': sender['email'] if sender else '',
                'content':      msg.get('content', ''),
                'timestamp':    ts_str,
                'is_me':        msg['sender_id'] == user['_id'],
                'read':         msg.get('read', True)
            })
        return jsonify({'success': True, 'messages': formatted})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dm/unread-count')
@login_required
def unread_dm_count():
    """Get unread DM count for badge."""
    try:
        user  = db.users.find_one({'email': session['email']})
        count = db.direct_messages.count_documents({'receiver_id': user['_id'], 'read': False})
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  GOOGLE OAUTH
# ══════════════════════════════════════════════════════════════════════
@app.route('/connect-drive')
@login_required
def connect_drive():
    try:
        session.pop('drive_creds', None); session.pop('drive_state', None)
        redirect_uri = ('https://office-academic.juooa.cloud/drive/callback'
                        if request.url_root.startswith('https://') else
                        'http://localhost:5000/drive/callback')
        flow = Flow.from_client_secrets_file('client_secret.json', scopes=DRIVE_SCOPES, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
        session['drive_state'] = state
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"connect_drive error: {e}")
        flash('Error initiating Drive connection.', 'error')
        return redirect(url_for('home'))

@app.route('/drive/callback')
def drive_callback():
    try:
        if session.get('drive_state') != request.args.get('state'):
            flash('Authorization failed: State mismatch', 'error')
            return redirect(url_for('home'))
        redirect_uri = ('https://office-academic.juooa.cloud/drive/callback'
                        if request.url_root.startswith('https://') else
                        'http://localhost:5000/drive/callback')
        flow = Flow.from_client_secrets_file('client_secret.json', scopes=DRIVE_SCOPES,
                                              redirect_uri=redirect_uri, state=session['drive_state'])
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        session['drive_creds'] = {
            'token': creds.token, 'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri, 'client_id': creds.client_id,
            'client_secret': creds.client_secret, 'scopes': DRIVE_SCOPES
        }
        session.pop('drive_state', None)
        flash('✅ Google Drive connected!', 'success')
        return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"drive_callback error: {e}")
        flash('Error connecting to Drive.', 'error')
        return redirect(url_for('home'))

@app.route('/connect-gmail')
@login_required
def connect_gmail():
    try:
        session.pop('gmail_creds', None); session.pop('gmail_state', None)
        redirect_uri = ('https://office-academic.juooa.cloud/gmail/callback'
                        if request.url_root.startswith('https://') else
                        'http://localhost:5000/gmail/callback')
        flow = Flow.from_client_secrets_file('client_secret.json', scopes=GMAIL_SCOPES, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='false', prompt='consent')
        session['gmail_state'] = state
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"connect_gmail error: {e}")
        flash('Error initiating Gmail connection.', 'error')
        return redirect(url_for('home'))

@app.route('/gmail/callback')
def gmail_callback():
    try:
        if session.get('gmail_state') != request.args.get('state'):
            flash('State mismatch. Authorization failed.', 'error')
            return redirect(url_for('home'))
        redirect_uri = ('https://office-academic.juooa.cloud/gmail/callback'
                        if request.url_root.startswith('https://') else
                        'http://localhost:5000/gmail/callback')
        flow = Flow.from_client_secrets_file('client_secret.json', scopes=GMAIL_SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        session['gmail_creds'] = {
            'token': creds.token, 'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri, 'client_id': creds.client_id,
            'client_secret': creds.client_secret, 'scopes': GMAIL_SCOPES
        }
        session.pop('gmail_state', None)
        flash('✅ Gmail connected!', 'success')
        return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"gmail_callback error: {e}")
        flash('Error connecting to Gmail.', 'error')
        return redirect(url_for('home'))

# ══════════════════════════════════════════════════════════════════════
#  DRIVE OPERATIONS
# ══════════════════════════════════════════════════════════════════════
@app.route('/drive/files')
@login_required
def drive_files():
    if 'drive_creds' not in session:
        flash('Please connect your Google Drive first.', 'error')
        return redirect(url_for('connect_drive'))
    try:
        service = get_drive_service()
        if not service:
            flash('Error connecting to Drive. Please reconnect.', 'error')
            return redirect(url_for('connect_drive'))
        results = service.files().list(
            q="trashed=false and mimeType='application/vnd.google-apps.folder'",
            pageSize=100, fields="files(id,name,mimeType,createdTime,webViewLink,iconLink)",
            orderBy="name").execute()
        folders = results.get('files', [])
        user_folders     = db.user_navbars.find_one({'user_email': session['email']})
        saved_folder_ids = [item['ref_id'] for item in user_folders['items']] if user_folders and 'items' in user_folders else []
        for folder in folders:
            if 'webViewLink' not in folder:
                folder['webViewLink'] = f"https://drive.google.com/drive/folders/{folder['id']}"
        return render_template('drive_files.html', folders=folders,
                               saved_folder_ids=saved_folder_ids, total_folders=len(folders),
                               notifications=get_user_notifications())
    except Exception as e:
        logger.error(f"drive_files error: {e}")
        flash('Error connecting to Google Drive', 'error')
        return redirect(url_for('home'))

@app.route('/api/drive/folder/<folder_id>')
@login_required
def get_drive_folder_contents(folder_id):
    if 'drive_creds' not in session: return jsonify({'error': 'Not authenticated'}), 401
    try:
        service = get_drive_service()
        if not service: return jsonify({'error': 'Drive service unavailable'}), 500
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=100, fields="files(id,name,mimeType,size,createdTime,webViewLink)").execute()
        return jsonify(results.get('files', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/drive/search')
@login_required
def search_drive_files():
    if 'drive_creds' not in session: return jsonify({'error': 'Not authenticated'}), 401
    try:
        query = request.args.get('q', '')
        if not query: return jsonify([])
        service = get_drive_service()
        if not service: return jsonify({'error': 'Drive service unavailable'}), 500
        results = service.files().list(
            q=f"name contains '{query}' and trashed=false",
            pageSize=20, fields="files(id,name,mimeType,webViewLink,iconLink)").execute()
        return jsonify(results.get('files', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/drive/upload', methods=['POST'])
@login_required
def drive_upload():
    if 'drive_creds' not in session: return jsonify({'error': 'Not authenticated'}), 401
    try:
        file        = request.files.get('file')
        folder_id   = request.form.get('folder_id', 'root')
        make_public = request.form.get('make_public', 'false') == 'true'
        if not file: return jsonify({'error': 'No file provided'}), 400
        service = get_drive_service()
        if not service: return jsonify({'error': 'Drive service unavailable'}), 500
        file_metadata = {'name': secure_filename(file.filename), 'parents': [folder_id]}
        file_content  = file.read()
        media         = MediaIoBaseUpload(BytesIO(file_content),
                                          mimetype=file.mimetype or 'application/octet-stream',
                                          resumable=True)
        file_obj = service.files().create(body=file_metadata, media_body=media,
                                          fields='id,name,webViewLink').execute()
        result = {
            'file_id':   file_obj['id'],
            'file_name': file_obj['name'],
            'web_link':  file_obj.get('webViewLink', f"https://drive.google.com/file/d/{file_obj['id']}/view")
        }
        if make_public:
            if make_file_public(service, file_obj['id']):
                result['public_link'] = f"https://drive.google.com/file/d/{file_obj['id']}/view"
                db.public_files.insert_one({
                    'file_id': file_obj['id'], 'name': file_obj['name'],
                    'uploader_email': session['email'], 'web_link': result['public_link'],
                    'uploaded_at': get_indian_time()
                })
        db.user_files.insert_one({
            'user_email': session['email'], 'file_name': file_obj['name'],
            'original_filename': file_obj['name'], 'drive_file_id': file_obj['id'],
            'drive_link': result['web_link'], 'is_public': make_public,
            'source': 'drive', 'uploaded_at': get_indian_time()
        })
        return jsonify(result)
    except Exception as e:
        logger.error(f"drive_upload error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/drive/create-folder', methods=['POST'])
@login_required
def drive_create_folder():
    if 'drive_creds' not in session: return jsonify({'error': 'Not authenticated'}), 401
    try:
        data        = request.get_json(force=True) or {}
        folder_name = data.get('folder_name')
        parent_id   = data.get('parent_id', 'root')
        if not folder_name: return jsonify({'error': 'Folder name required'}), 400
        service = get_drive_service()
        if not service: return jsonify({'error': 'Drive service unavailable'}), 500
        folder = service.files().create(body={
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }, fields='id,name').execute()
        return jsonify({'folder_id': folder['id'], 'folder_name': folder['name']})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ══════════════════════════════════════════════════════════════════════
#  FILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════
@app.route('/my_files')
@login_required
def my_files():
    try:
        return render_template('my_files.html',
            user_files=list(db.user_files.find({'user_email':session['email']}).sort('uploaded_at',-1)),
            drive_connected='drive_creds' in session,
            notifications=get_user_notifications())
    except Exception as e:
        logger.error(f"my_files error: {e}")
        flash('Error loading files', 'error')
        return redirect(url_for('home'))

@app.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    try:
        file        = request.files.get('file')
        file_name   = request.form.get('file_name', '')
        description = request.form.get('description', '')
        if not file: return jsonify({'error': 'No file provided', 'success': False}), 400
        if not allowed_file(file.filename): return jsonify({'error': 'File type not allowed', 'success': False}), 400
        filename = secure_filename(file.filename)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        n, e = os.path.splitext(filename)
        ufn  = f"{n}_{ts}{e}"
        fp   = os.path.join(app.config['UPLOAD_FOLDER'], ufn)
        file.save(fp)
        file_doc = {
            'user_email': session['email'], 'file_name': file_name or filename,
            'original_filename': filename, 'stored_filename': ufn,
            'description': description, 'file_path': fp,
            'file_size': os.path.getsize(fp),
            'file_type': e.lstrip('.').lower(), 'source': 'local',
            'uploaded_at': get_indian_time()
        }
        result = db.user_files.insert_one(file_doc)
        return jsonify({'success': True, 'message': 'File uploaded',
                        'file_id': str(result.inserted_id), 'file_name': file_doc['file_name']})
    except Exception as e:
        logger.error(f"upload_file error: {e}")
        return jsonify({'error': str(e), 'success': False}), 400

@app.route('/edit_file/<file_id>', methods=['POST'])
@login_required
def edit_file(file_id):
    try:
        data   = request.get_json(force=True) or {}
        result = db.user_files.update_one(
            {'_id':ObjectId(file_id),'user_email':session['email']},
            {'$set':{'file_name':data.get('file_name',''),'description':data.get('description',''),
                     'updated_at':get_indian_time()}})
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'File updated'})
        return jsonify({'error': 'File not found or unauthorized'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/delete_file/<file_id>', methods=['DELETE'])
@login_required
def delete_file(file_id):
    try:
        file_doc = db.user_files.find_one({'_id':ObjectId(file_id),'user_email':session['email']})
        if not file_doc: return jsonify({'error': 'File not found'}), 404
        if file_doc.get('source') == 'local' and file_doc.get('file_path') and os.path.exists(file_doc['file_path']):
            os.remove(file_doc['file_path'])
        elif file_doc.get('source') == 'drive' and file_doc.get('drive_file_id'):
            service = get_drive_service()
            if service: delete_drive_file(service, file_doc['drive_file_id'])
        db.user_files.delete_one({'_id': ObjectId(file_id)})
        db.public_files.delete_one({'file_id': file_doc.get('drive_file_id')})
        return jsonify({'success': True, 'message': 'File deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/download_file/<file_id>')
@login_required
def download_file(file_id):
    try:
        file_doc = db.user_files.find_one({'_id':ObjectId(file_id),'user_email':session['email']})
        if not file_doc or file_doc.get('source') != 'local':
            flash('File not found or not locally stored', 'error')
            return redirect(url_for('my_files'))
        return send_from_directory(os.path.dirname(file_doc['file_path']),
                                   os.path.basename(file_doc['file_path']), as_attachment=True)
    except Exception as e:
        logger.error(f"download_file error: {e}")
        flash('Error downloading file', 'error')
        return redirect(url_for('my_files'))

@app.route('/link_drive_file', methods=['POST'])
@login_required
def link_drive_file():
    try:
        data          = request.get_json(force=True) or {}
        drive_file_id = data.get('drive_file_id')
        if not drive_file_id: return jsonify({'error': 'Drive file ID required'}), 400
        service = get_drive_service()
        if not service: return jsonify({'error': 'Drive not connected'}), 400
        file_metadata = service.files().get(fileId=drive_file_id,
                                            fields='id,name,mimeType,size,webViewLink').execute()
        file_doc = {
            'user_email': session['email'], 'file_name': data.get('file_name') or file_metadata['name'],
            'original_filename': file_metadata['name'], 'description': data.get('description',''),
            'drive_file_id': drive_file_id, 'drive_link': file_metadata.get('webViewLink'),
            'file_type': file_metadata.get('mimeType',''), 'source': 'drive',
            'uploaded_at': get_indian_time()
        }
        result = db.user_files.insert_one(file_doc)
        return jsonify({'success': True, 'message': 'Drive file linked', 'file_id': str(result.inserted_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ══════════════════════════════════════════════════════════════════════
#  PUBLIC FILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════
@app.route('/manage_public_files')
@login_required
def manage_public_files():
    try:
        public_files    = []
        drive_connected = 'drive_creds' in session
        if drive_connected:
            try:
                service = get_drive_service()
                if service:
                    db_public_files = list(db.public_files.find({'uploader_email':session['email']}).sort('uploaded_at',-1))
                    for f in db_public_files:
                        try:
                            dm = service.files().get(fileId=f['file_id'], fields='id,name,mimeType,size,webViewLink').execute()
                            f['drive_metadata'] = dm
                        except:
                            f['drive_metadata'] = {'name': f.get('name','Unknown')}
                        public_files.append(f)
            except:
                drive_connected = False
        return render_template('manage_public_files.html', public_files=public_files,
                               drive_connected=drive_connected, notifications=get_user_notifications())
    except Exception as e:
        logger.error(f"manage_public_files error: {e}")
        return render_template('manage_public_files.html', public_files=[], drive_connected=False, notifications=[])

@app.route('/make_file_private/<file_id>', methods=['POST'])
@login_required
def make_file_private_api(file_id):
    try:
        service  = get_drive_service()
        if not service: return jsonify({'error': 'Drive not connected'}), 400
        file_doc = db.public_files.find_one({'file_id':file_id,'uploader_email':session['email']})
        if not file_doc: return jsonify({'error': 'File not found or unauthorized'}), 404
        if make_file_private(service, file_id):
            db.public_files.delete_one({'file_id': file_id})
            db.user_files.update_one({'drive_file_id':file_id,'user_email':session['email']},
                                     {'$set':{'is_public':False,'updated_at':get_indian_time()}})
            return jsonify({'success': True, 'message': 'File made private'})
        return jsonify({'error': 'Failed to make file private'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/delete_public_file/<file_id>', methods=['DELETE'])
@login_required
def delete_public_file(file_id):
    try:
        service  = get_drive_service()
        if not service: return jsonify({'error': 'Drive not connected'}), 400
        file_doc = db.public_files.find_one({'file_id':file_id,'uploader_email':session['email']})
        if not file_doc: return jsonify({'error': 'File not found or unauthorized'}), 404
        if delete_drive_file(service, file_id):
            db.public_files.delete_one({'file_id': file_id})
            db.user_files.delete_one({'drive_file_id':file_id,'user_email':session['email']})
            return jsonify({'success': True, 'message': 'Public file deleted'})
        return jsonify({'error': 'Failed to delete file'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ══════════════════════════════════════════════════════════════════════
#  REMINDERS & SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════════
@app.route('/set_reminder', methods=['POST'])
@login_required
def set_reminder():
    try:
        data          = request.get_json(force=True) or {}
        event_id      = data.get('event_id')
        reminder_date = data.get('reminder_date')
        reminder_time = data.get('reminder_time')
        if not all([event_id, reminder_date, reminder_time]):
            return jsonify({'error': 'Missing required fields', 'success': False}), 400
        event = db.events.find_one({'_id': ObjectId(event_id)})
        if not event: return jsonify({'error': 'Event not found', 'success': False}), 404
        user = db.users.find_one({'email': session['email']})
        if not user: return jsonify({'error': 'User not found', 'success': False}), 404
        if '-' in reminder_date and len(reminder_date.split('-')[0]) == 2:
            d, m, y = reminder_date.split('-')
            if len(y) == 4: reminder_date = f"{y}-{m}-{d}"
        if len(reminder_time.split(':')) == 2:
            reminder_time = f"{reminder_time}:00"
        reminder_datetime = IST.localize(datetime.strptime(f"{reminder_date} {reminder_time}", '%Y-%m-%d %H:%M:%S'))
        reminder_datetime_naive = make_timezone_naive(reminder_datetime)
        if reminder_datetime <= get_indian_time_aware():
            return jsonify({'error': 'Reminder time must be in the future', 'success': False}), 400
        existing = db.event_reminders.find_one({'user_id':user['_id'],'event_id':event['_id']})
        if existing:
            db.event_reminders.update_one({'_id':existing['_id']},
                {'$set':{'reminder_datetime':reminder_datetime_naive,'sent':False,'updated_at':get_indian_time()}})
            message = 'Reminder updated successfully'
        else:
            db.event_reminders.insert_one({
                'user_id': user['_id'], 'event_id': event['_id'],
                'reminder_datetime': reminder_datetime_naive, 'sent': False,
                'created_at': get_indian_time(), 'attempt_count': 0
            })
            message = 'Reminder set successfully'
        try:
            try:
                url_root = request.url_root.rstrip('/')
            except Exception:
                url_root = "https://juooa.cloud"
            user_name = user.get('name') or user['email'].split('@')[0].replace('.', ' ').title()
            event_date  = event.get('event_date', '')
            event_time  = event.get('event_time', 'All Day')
            venue       = event.get('venue', '—')
            sched_str   = reminder_datetime.strftime('%d %B %Y at %I:%M %p IST')
            is_update   = message == 'Reminder updated successfully'

            msg = Message(
                subject=f"{'🔄 Reminder Updated' if is_update else '✅ Reminder Confirmed'}: {event['event_name']}",
                sender=app.config['MAIL_USERNAME'],
                recipients=[user['email']]
            )
            try:
                with app.open_resource("static/images/jainu.png") as fp:
                    msg.attach("jainu.png", "image/png", fp.read(), headers=[['Content-ID', '<jain_logo>']])
            except Exception as logo_err:
                logger.error(f"Failed to attach logo in confirmation email: {logo_err}")

            msg.html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reminder Confirmed – {event['event_name']}</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f8;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f8;padding:48px 16px;">
  <tr><td align="center">

    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 48px rgba(9,14,26,0.14);">

      <!-- ═══ HEADER ═══ -->
      <tr>
        <td style="background:#ffffff;padding:0;border-bottom:1px solid #e5e7eb;">
          <!-- top gold bar -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="height:4px;background:linear-gradient(90deg,#d97706,#f59e0b,#fbbf24,#f59e0b,#d97706);"></td></tr>
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" style="padding:36px 48px 28px;">
            <tr>
              <td align="left" valign="middle" width="95">
                <img src="cid:jain_logo"
                     alt="Jain University"
                     width="84" height="84"
                     style="display:block;border-radius:12px;object-fit:contain;padding:4px;">
              </td>
              <td valign="middle" style="padding-left:20px;">
                <p style="margin:0 0 3px;color:#d97706;font-size:10px;font-weight:800;letter-spacing:3.5px;text-transform:uppercase;">Office of Academics</p>
                <h1 style="margin:0;color:#090e1a;font-size:20px;font-weight:700;letter-spacing:0.3px;line-height:1.3;">Jain (Deemed-to-be University)</h1>
                <p style="margin:4px 0 0;color:#5e718d;font-size:11px;letter-spacing:1px;">OOA Microsite · Academic Excellence</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- ═══ STATUS BANNER ═══ -->
      <tr>
        <td style="background:linear-gradient(90deg,{'#166534' if not is_update else '#1e3a5f'},{'#16a34a' if not is_update else '#2563eb'});padding:18px 48px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td valign="middle">
                <span style="font-size:28px;line-height:1;">{'✅' if not is_update else '🔄'}</span>
              </td>
              <td valign="middle" style="padding-left:14px;">
                <p style="margin:0;color:#ffffff;font-size:16px;font-weight:700;letter-spacing:0.3px;">
                  {'Reminder Confirmed!' if not is_update else 'Reminder Updated!'}
                </p>
                <p style="margin:3px 0 0;color:rgba(255,255,255,0.75);font-size:12px;">
                  You'll receive an email alert at your scheduled time
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- ═══ BODY ═══ -->
      <tr>
        <td style="padding:40px 48px 32px;">

          <p style="margin:0 0 24px;font-size:15.5px;color:#374151;line-height:1.6;">
            Hi <strong style="color:#090e1a;">{user_name}</strong>,<br>
            Your reminder for the event below has been {'updated' if is_update else 'successfully set'}.
            We'll email you at the scheduled time so you never miss it.
          </p>

          <!-- EVENT CARD -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:14px;overflow:hidden;border:1.5px solid #e5e7eb;margin-bottom:28px;">
            <!-- card header -->
            <tr>
              <td style="background:linear-gradient(135deg,#090e1a,#1a2a4a);padding:20px 28px;">
                <p style="margin:0 0 4px;color:#d97706;font-size:10px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;">Event Details</p>
                <h2 style="margin:0;color:#ffffff;font-size:19px;font-weight:700;line-height:1.35;">{event['event_name']}</h2>
              </td>
            </tr>
            <!-- card body -->
            <tr>
              <td style="background:#fafbfd;padding:24px 28px;">
                <table width="100%" cellpadding="0" cellspacing="8">
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;">
                      <table cellpadding="0" cellspacing="0"><tr>
                        <td style="width:36px;">
                          <div style="width:32px;height:32px;background:#fef3c7;border-radius:8px;text-align:center;line-height:32px;font-size:15px;">📅</div>
                        </td>
                        <td style="padding-left:12px;">
                          <p style="margin:0;font-size:10px;color:#9ca3af;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Date</p>
                          <p style="margin:3px 0 0;font-size:14px;color:#111827;font-weight:700;">{event_date}</p>
                        </td>
                      </tr></table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;">
                      <table cellpadding="0" cellspacing="0"><tr>
                        <td style="width:36px;">
                          <div style="width:32px;height:32px;background:#dbeafe;border-radius:8px;text-align:center;line-height:32px;font-size:15px;">🕐</div>
                        </td>
                        <td style="padding-left:12px;">
                          <p style="margin:0;font-size:10px;color:#9ca3af;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Time</p>
                          <p style="margin:3px 0 0;font-size:14px;color:#111827;font-weight:700;">{event_time}</p>
                        </td>
                      </tr></table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;">
                      <table cellpadding="0" cellspacing="0"><tr>
                        <td style="width:36px;">
                          <div style="width:32px;height:32px;background:#d1fae5;border-radius:8px;text-align:center;line-height:32px;font-size:15px;">📍</div>
                        </td>
                        <td style="padding-left:12px;">
                          <p style="margin:0;font-size:10px;color:#9ca3af;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Venue</p>
                          <p style="margin:3px 0 0;font-size:14px;color:#111827;font-weight:700;">{venue}</p>
                        </td>
                      </tr></table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>

          <!-- REMINDER TIME BOX -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:12px;border:1.5px solid #fcd34d;background:linear-gradient(135deg,#fffbeb,#fef9f0);margin-bottom:32px;">
            <tr>
              <td style="padding:18px 24px;">
                <table cellpadding="0" cellspacing="0" width="100%"><tr>
                  <td valign="top" style="font-size:22px;line-height:1;padding-right:14px;">⏰</td>
                  <td>
                    <p style="margin:0 0 3px;font-size:11px;color:#92400e;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;">Your Reminder Is Set For</p>
                    <p style="margin:0;font-size:16px;color:#78350f;font-weight:700;">{sched_str}</p>
                  </td>
                </tr></table>
              </td>
            </tr>
          </table>

          <!-- CTA BUTTON -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
            <tr>
              <td align="center">
                <a href="{url_root}/home"
                   style="display:inline-block;background:linear-gradient(135deg,#090e1a,#1a2a4a);color:#ffffff;
                          text-decoration:none;padding:15px 44px;border-radius:50px;font-size:14px;
                          font-weight:700;letter-spacing:0.5px;box-shadow:0 4px 16px rgba(9,14,26,0.3);">
                  Visit OOA Microsite &nbsp;→
                </a>
              </td>
            </tr>
          </table>

        </td>
      </tr>

      <!-- ═══ FOOTER ═══ -->
      <tr>
        <td style="background:#f8fafc;border-top:1px solid #e5e7eb;padding:24px 48px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center">
                <p style="margin:0 0 6px;font-size:12px;color:#9ca3af;line-height:1.6;">
                  This is an automated notification from the OOA Microsite.<br>
                  Jain (Deemed-to-be University) · Office of Academics
                </p>
                <p style="margin:0;font-size:12px;">
                  <a href="mailto:officeofacademics@juooa.cloud"
                     style="color:#d97706;text-decoration:none;font-weight:600;">
                    officeofacademics@juooa.cloud
                  </a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- bottom gold bar -->
      <tr>
        <td style="height:4px;background:linear-gradient(90deg,#d97706,#f59e0b,#fbbf24,#f59e0b,#d97706);"></td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""
            msg.body = (
                f"{'Reminder Updated' if is_update else 'Reminder Confirmed'}: {event['event_name']}\n\n"
                f"Event Date: {event_date}\n"
                f"Time: {event_time}\n"
                f"Venue: {venue}\n\n"
                f"Your reminder is scheduled for: {sched_str}\n\n"
                f"Visit: {url_root}/home\n\n"
                f"-- Office of Academics, Jain University"
            )
            mail.send(msg)
        except Exception as mail_err:
            logger.error(f"Reminder confirmation email failed: {mail_err}")

        return jsonify({'success': True, 'message': f"{message}! Confirmation email sent."})
    except Exception as e:
        logger.error(f"set_reminder error: {e}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}', 'success': False}), 500

# ── PROFILE ROUTE ──
@app.route('/profile', methods=['GET'])
@login_required
def user_profile():
    try:
        user = db.users.find_one({'email': session['email']})
        if not user:
            flash("User not found", "error")
            return redirect(url_for("home"))
            
        profile = user.get('profile', {}) or {}
        user_name = user.get('name') or profile.get('name') or parse_name_from_email(session['email'])
        user_department = user.get('department') or profile.get('department', '')
        user_location = user.get('location') or profile.get('location', '')
        user_photo = user.get('photo_url') or profile.get('photo_url') or f"https://ui-avatars.com/api/?name={user_name.replace(' ', '+')}&background=0A2A44&color=fff"
        
        # Fetch reminders set by the user
        reminders_cursor = db.event_reminders.find({'user_id': user['_id']})
        reminders = []
        for r in reminders_cursor:
            event = db.events.find_one({'_id': r['event_id']})
            if event:
                reminders.append({
                    'id': str(r['_id']),
                    'event_name': event.get('event_name'),
                    'event_date': event.get('event_date'),
                    'event_time': event.get('event_time', 'All Day'),
                    'venue': event.get('venue', '—'),
                    'reminder_datetime': r.get('reminder_datetime'),
                    'sent': r.get('sent', False)
                })
        
        # Fetch documents submitted by the user
        office_docs = list(db.office_documents.find({'user_email': session['email']}))
        dept_docs = list(db.dept_repo_docs.find({'uploaded_by': session['email']}))
        public_docs = list(db.public_files.find({'uploader_email': session['email']}))
        
        documents = []
        for doc in office_docs:
            documents.append({
                'name': doc.get('document_name', 'Unnamed Document'),
                'type': 'Office Document',
                'date': doc.get('submitted_at'),
                'status': doc.get('status', 'pending'),
                'url': doc.get('file_url') or '#'
            })
        for doc in dept_docs:
            doc_name = doc.get('title') or (doc.get('files')[0] if doc.get('files') else 'Unnamed Document')
            documents.append({
                'name': doc_name,
                'type': 'Department Repository Document',
                'date': doc.get('uploaded_at'),
                'status': 'Uploaded',
                'url': f"/uploads/{doc.get('files')[0]}" if doc.get('files') else '#'
            })
        for doc in public_docs:
            documents.append({
                'name': doc.get('name', 'Unnamed Document'),
                'type': 'Public/Drive File',
                'date': doc.get('uploaded_at'),
                'status': 'Uploaded',
                'url': doc.get('web_link') or '#'
            })
            
        # Sort documents by date (descending)
        def get_date(d):
            dt = d.get('date')
            if isinstance(dt, datetime):
                return dt
            return datetime.min
        documents.sort(key=get_date, reverse=True)
            
        return render_template('profile.html', 
                               user=user, 
                               user_name=user_name,
                               user_department=user_department,
                               user_location=user_location,
                               user_photo=user_photo,
                               reminders=reminders, 
                               documents=documents)
    except Exception as e:
        logger.error(f"Error rendering profile page: {e}", exc_info=True)
        flash("Error loading profile", "error")
        return redirect(url_for("home"))

# ── PROFILE CHANGE PASSWORD ──
@app.route('/profile/change_password', methods=['POST'])
@login_required
def profile_change_password():
    try:
        data = request.get_json(force=True) or {}
        old_pwd = data.get('old_password')
        new_pwd = data.get('new_password')
        confirm_pwd = data.get('confirm_password')
        
        if not all([old_pwd, new_pwd, confirm_pwd]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        if new_pwd != confirm_pwd:
            return jsonify({'success': False, 'message': 'New passwords do not match'}), 400
        if len(new_pwd) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400
            
        user = db.users.find_one({'email': session['email']})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
            
        # check password hash
        if not check_password_hash(user['password'], old_pwd):
            return jsonify({'success': False, 'message': 'Incorrect current password'}), 400
            
        # generate new hash
        new_hash = generate_password_hash(new_pwd)
        db.users.update_one({'email': session['email']}, {'$set': {'password': new_hash}})
        return jsonify({'success': True, 'message': 'Password updated successfully'})
    except Exception as e:
        logger.error(f"Error changing password: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Server error: {str(e)}"}), 500

# ── PROFILE UPLOAD PHOTO ──
@app.route('/profile/upload_photo', methods=['POST'])
@login_required
def profile_upload_photo():
    try:
        if 'photo' not in request.files:
            return jsonify({'success': False, 'message': 'No photo file provided'}), 400
        file = request.files['photo']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No photo selected'}), 400
            
        import uuid
        from werkzeug.utils import secure_filename
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            return jsonify({'success': False, 'message': 'Invalid file format. Allowed formats: JPG, JPEG, PNG, GIF, WEBP'}), 400
            
        filename = f"profile_{uuid.uuid4().hex[:12]}.{ext}"
        upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        photo_url = f"/uploads/{filename}"
        
        # Update user in DB
        db.users.update_one({'email': session['email']}, {'$set': {'photo_url': photo_url, 'profile.photo_url': photo_url}})
        return jsonify({'success': True, 'photo_url': photo_url, 'message': 'Profile picture updated'})
    except Exception as e:
        logger.error(f"Error uploading photo: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Server error: {str(e)}"}), 500

# ── PROFILE DELETE REMINDER ──
@app.route('/profile/delete_reminder/<reminder_id>', methods=['POST', 'DELETE'])
@login_required
def profile_delete_reminder(reminder_id):
    try:
        user = db.users.find_one({'email': session['email']})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        res = db.event_reminders.delete_one({'_id': ObjectId(reminder_id), 'user_id': user['_id']})
        if res.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Reminder cancelled successfully'})
        return jsonify({'success': False, 'message': 'Reminder not found or does not belong to you'}), 404
    except Exception as e:
        logger.error(f"Error deleting reminder: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Server error: {str(e)}"}), 500

@app.route('/subscribe_to_event', methods=['POST'])
@login_required
def subscribe_to_event():
    try:
        data     = request.get_json(force=True) or {}
        event_id = data.get('event_id')
        if not event_id: return jsonify({'error': 'Event ID required'}), 400
        event = db.events.find_one({'_id': ObjectId(event_id)})
        if not event: return jsonify({'error': 'Event not found'}), 404
        user = db.users.find_one({'email': session['email']})
        existing = db.event_subscriptions.find_one({'user_id':user['_id'],'event_id':event['_id']})
        if existing: return jsonify({'success': True, 'message': 'Already subscribed'})
        db.event_subscriptions.insert_one({
            'user_id': user['_id'], 'event_id': event['_id'],
            'event_name': event['event_name'], 'subscribed_at': get_indian_time()
        })
        return jsonify({'success': True, 'message': 'Successfully subscribed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/unsubscribe_from_event/<event_id>', methods=['DELETE'])
@login_required
def unsubscribe_from_event(event_id):
    try:
        user   = db.users.find_one({'email': session['email']})
        result = db.event_subscriptions.delete_one({'user_id':user['_id'],'event_id':ObjectId(event_id)})
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Unsubscribed'})
        return jsonify({'error': 'Subscription not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/my_reminders')
@login_required
def my_reminders():
    try:
        user = db.users.find_one({'email': session['email']})
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('home'))
        reminders = list(db.event_reminders.find({'user_id':user['_id']}).sort('reminder_datetime',1))
        for reminder in reminders:
            event = db.events.find_one({'_id': reminder['event_id']})
            if event: reminder['event'] = event
        return render_template('my_reminders.html', reminders=reminders,
                               notifications=get_user_notifications())
    except Exception as e:
        logger.error(f"my_reminders error: {e}")
        flash('Error loading reminders', 'error')
        return redirect(url_for('home'))

@app.route('/delete_reminder/<reminder_id>', methods=['DELETE'])
@login_required
def delete_reminder(reminder_id):
    try:
        user   = db.users.find_one({'email': session['email']})
        result = db.event_reminders.delete_one({'_id':ObjectId(reminder_id),'user_id':user['_id']})
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Reminder deleted'})
        return jsonify({'error': 'Reminder not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/subscribe', methods=['POST'])
def subscribe():
    try:
        data  = request.get_json(force=True) or {}
        email = data.get('email')
        if not email: return jsonify({"message": "Email is required"}), 400
        db.subscribers.update_one({"email": email},
            {"$set": {"school": data.get('school',''), "subscribed_at": datetime.now()}}, upsert=True)
        return jsonify({"message": "Subscribed successfully"}), 200
    except Exception as e:
        return jsonify({"message": "Subscription failed"}), 500

# ══════════════════════════════════════════════════════════════════════
#  USER PREFERENCES
# ══════════════════════════════════════════════════════════════════════
@app.route('/user_preferences', methods=['GET', 'POST'])
@login_required
def user_preferences():
    if request.method == 'POST':
        try:
            data = request.get_json(force=True) or {}
            db.user_preferences.update_one({'email': session['email']},
                {'$set': {'email_notifications': data.get('email_notifications', True),
                          'reminder_notifications': data.get('reminder_notifications', True),
                          'event_updates': data.get('event_updates', True),
                          'preferred_schools': data.get('preferred_schools', []),
                          'updated_at': get_indian_time()}}, upsert=True)
            return jsonify({'success': True, 'message': 'Preferences updated'})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    try:
        preferences = db.user_preferences.find_one({'email': session['email']}) or {
            'email_notifications': True, 'reminder_notifications': True,
            'event_updates': True, 'preferred_schools': []
        }
        return render_template('user_preferences.html', preferences=preferences,
                               notifications=get_user_notifications())
    except Exception as e:
        flash('Error loading preferences', 'error')
        return redirect(url_for('home'))

# ══════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════
@app.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('home'))
    search      = request.args.get('search', '').strip()
    type_filter = request.args.get('type_filter', '').strip()
    role_filter = request.args.get('role_filter', '').strip()
    dept_filter = request.args.get('dept_filter', '').strip()
    query = {}
    if search:      query['email'] = {'$regex': search, '$options': 'i'}
    if type_filter: query['user_type'] = type_filter
    if role_filter == 'none': query['special_role'] = {'$in': [None, '', 'none']}
    elif role_filter:         query['special_role'] = role_filter
    if dept_filter:
        query['$or'] = [
            {'department': {'$regex': dept_filter, '$options': 'i'}},
            {'profile.department': {'$regex': dept_filter, '$options': 'i'}},
        ]
    # Today's events for the ticker
    try:
        from app import get_today_ist_string, normalize_date
        _today = get_today_ist_string()
        today_events = []
        for _ev in list(db.events.find({})):
            _ed = normalize_date(_ev.get('event_date',''))
            _end = normalize_date(_ev.get('end_date','')) if _ev.get('end_date') else ''
            if _ed == _today or (_end and _ed <= _today <= _end):
                _ev['_id'] = str(_ev['_id'])
                today_events.append(_ev)
    except Exception:
        today_events = []
    users_raw = list(db.users.find(query).sort('created_at', -1))
    now = datetime.utcnow()
    users = []
    for u in users_raw:
        u['_id'] = str(u['_id'])
        last_seen  = u.get('last_seen')
        is_active  = bool(last_seen and isinstance(last_seen, datetime) and (now - last_seen).total_seconds() < 900)
        u['is_active_now'] = is_active
        profile = u.get('profile', {}) or {}
        u['dept_display']     = u.get('department') or profile.get('department') or '—'
        u['location_display'] = u.get('location')   or profile.get('location')   or '—'
        u['last_login_display'] = (u['last_login'].strftime('%d %b %Y, %H:%M')
                                   if isinstance(u.get('last_login'), datetime) else '—')
        u['last_seen_display']  = (last_seen.strftime('%d %b %Y, %H:%M')
                                   if isinstance(last_seen, datetime) else '—')
        u['changes_made']  = u.get('changes_made', 0)
        u['total_logins']  = u.get('total_logins', 0)
        if u.get('special_role') == 'leader':               u['display_type'] = 'Leader'
        elif u.get('special_role') == 'office_barrier' or u.get('user_type') == 'core': u['display_type'] = 'Core Team'
        else:                                                u['display_type'] = 'Faculty'
        users.append(u)
    all_departments = sorted(set(
        d for d in (db.users.distinct('department') + db.users.distinct('profile.department')) if d
    ))
    # Query campuses
    campuses_raw = list(db.campuses.find())
    get_all_campuses() # Ensure seeding occurs if empty
    if not campuses_raw:
        campuses_raw = list(db.campuses.find())
    campuses = []
    for c in campuses_raw:
        c['_id'] = str(c['_id'])
        campuses.append(c)

    return render_template(
        'admin_dashboard.html', users=users,
        total_users=db.users.count_documents({}),
        pending_users=db.users.count_documents({'approved':{'$ne':True}}),
        approved_users=db.users.count_documents({'approved':True}),
        active_now=sum(1 for u in users if u['is_active_now']),
        pre_assigned_leaders=list(db.pre_assigned_leaders.find().sort('assigned_at',-1)),
        pre_assigned_core=list(db.pre_assigned_core.find().sort('assigned_at',-1)),
        all_departments=all_departments, today_events=today_events,
        campuses=campuses, **_get_user_info()
    )

@app.route('/admin_impersonate/<user_id>', methods=['POST'])
def admin_impersonate(user_id):
    if session.get('role') != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('home'))
    
    try:
        from bson import ObjectId as ObjId
        user = db.users.find_one({'_id': ObjId(user_id)})
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Log the impersonation action
        db.activity_logs.insert_one({
            'user_id': user['_id'],
            'user_email': session['email'],
            'action': 'impersonate',
            'details': f"Admin {session['email']} impersonated user {user['email']}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        
        # Setup session for impersonated user
        session.clear()
        session['email'] = user['email']
        session['role'] = user['role']
        session['user_type'] = user.get('user_type', 'faculty')
        session['special_role'] = user.get('special_role', None)
        session['approved'] = user.get('approved', False)
        session['user_id'] = str(user['_id'])
        
        profile = user.get('profile', {}) or {}
        user_name = user.get('name') or profile.get('name') or parse_name_from_email(user['email'])
        user_photo = user.get('photo_url') or profile.get('photo_url') or f"https://ui-avatars.com/api/?name={user_name.replace(' ', '+')}&background=0A2A44&color=fff"
        
        session['user_name'] = user_name
        session['user_photo'] = user_photo
        session['user_department'] = user.get('department') or profile.get('department', '')
        session['user_location'] = user.get('location') or profile.get('location', '')
        session.permanent = True
        
        flash(f'Impersonating {user_name} ({user["email"]}).', 'success')
        return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"Error impersonating user: {e}")
        flash('Error impersonating user.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin_change_password/<user_id>', methods=['POST'])
def admin_change_password(user_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'})
    
    try:
        from bson import ObjectId as ObjId
        new_password = request.form.get('new_password')
        if not new_password:
            return jsonify({'success': False, 'message': 'Password cannot be empty'})
            
        user = db.users.find_one({'_id': ObjId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
            
        hashed_pw = generate_password_hash(new_password)
        db.users.update_one({'_id': user['_id']}, {'$set': {'password': hashed_pw}})
        
        # Log the action
        db.activity_logs.insert_one({
            'user_id': user['_id'],
            'user_email': session['email'],
            'action': 'admin_change_password',
            'details': f"Admin {session['email']} changed password for {user['email']}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        
        # Optionally send an email to the user
        try:
            content_html = f"""
            Hello {user.get('name', 'User')},<br><br>
            Your account password has been changed by an administrator.<br><br>
            If you did not request this change, please contact support immediately.
            """
            send_microsite_email(
                subject="Account Password Changed",
                recipients=[user['email']],
                title="Password Update",
                content_html=content_html,
                status_type="info",
                status_text="Security Notice"
            )
        except Exception as e:
            logger.error(f"Failed to send password change notification to {user['email']}: {e}")
            
        return jsonify({'success': True, 'message': 'Password updated successfully!'})
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        return jsonify({'success': False, 'message': 'Server error'})


@app.route('/admin/user-activity/<user_id>')
def admin_user_activity(user_id):
    """Return activity log, uploads, and docs for a specific user (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    try:
        from bson import ObjectId as ObjId
        uid = ObjId(user_id)
        user = db.users.find_one({'_id': uid})
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Activity logs (last 30)
        logs_raw = list(db.activity_logs.find({'user_id': uid}).sort('timestamp', -1).limit(30))
        logs = []
        for l in logs_raw:
            ts = l.get('timestamp')
            logs.append({
                'action': l.get('action', ''),
                'details': l.get('details', ''),
                'timestamp': ts.strftime('%d %b %Y, %I:%M %p') if isinstance(ts, datetime) else str(ts or ''),
                'ip': l.get('ip_address', '')
            })

        # Documents submitted by this user
        docs_raw = list(db.documents.find({'submitted_by': user['email']}).sort('submitted_at', -1).limit(20))
        docs = []
        for d in docs_raw:
            ts = d.get('submitted_at')
            docs.append({
                'name': d.get('document_name', d.get('title', 'Untitled')),
                'status': d.get('status', 'pending'),
                'timestamp': ts.strftime('%d %b %Y') if isinstance(ts, datetime) else str(ts or '')
            })

        # File uploads
        files_raw = list(db.user_files.find({'user_email': user['email']}).sort('uploaded_at', -1).limit(20))
        files = []
        for f in files_raw:
            ts = f.get('uploaded_at')
            files.append({
                'name': f.get('file_name', 'Unknown'),
                'size': f.get('file_size', 0),
                'timestamp': ts.strftime('%d %b %Y') if isinstance(ts, datetime) else str(ts or '')
            })

        # Event reminders set by user
        reminders_raw = list(db.event_reminders.find({'user_id': uid}).sort('reminder_datetime', -1).limit(10))
        reminders = []
        for r in reminders_raw:
            event = db.events.find_one({'_id': r.get('event_id')})
            rd = r.get('reminder_datetime')
            reminders.append({
                'event': event['event_name'] if event else 'Unknown Event',
                'event_date': event.get('event_date', '') if event else '',
                'reminder_time': rd.strftime('%d %b %Y, %I:%M %p') if isinstance(rd, datetime) else str(rd or ''),
                'sent': r.get('sent', False)
            })

        profile = user.get('profile', {}) or {}
        last_seen = user.get('last_seen')
        return jsonify({
            'success': True,
            'user': {
                'name': user.get('name', ''),
                'email': user['email'],
                'role': user.get('role', ''),
                'user_type': user.get('user_type', ''),
                'special_role': user.get('special_role', ''),
                'approved': user.get('approved', False),
                'department': user.get('department') or profile.get('department', ''),
                'location': user.get('location') or profile.get('location', ''),
                'last_seen': last_seen.strftime('%d %b %Y, %I:%M %p') if isinstance(last_seen, datetime) else '—',
                'photo_url': user.get('photo_url', ''),
                'created_at': user.get('created_at', datetime.utcnow()).strftime('%d %b %Y') if isinstance(user.get('created_at'), datetime) else '—'
            },
            'logs': logs,
            'docs': docs,
            'files': files,
            'reminders': reminders
        })
    except Exception as e:
        logger.error(f"admin_user_activity error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/users')
def view_users():
    if session.get('role') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))
    try:
        return render_template('admin_view_users.html', users=list(db.users.find()))
    except Exception as e:
        logger.error(f"view_users error: {e}")
        return render_template('admin_view_users.html', users=[])

@app.route('/update_user/<user_id>', methods=['POST'])
def update_user(user_id):
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    try:
        email        = request.form.get('email', '').strip()
        role         = request.form.get('role', 'user')
        user_type    = request.form.get('user_type', 'faculty')
        special_role = request.form.get('special_role', '') or None
        approved     = request.form.get('approved', 'false') == 'true'
        department   = request.form.get('department', '').strip()
        location     = request.form.get('location', '').strip()
        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('admin_dashboard'))
        if role not in ['user','admin']:           role = 'user'
        if user_type not in ['faculty','core']:    user_type = 'faculty'
        if special_role and special_role not in ['office_barrier','leader']: special_role = None
        if special_role == 'office_barrier': user_type = 'core'
        elif special_role == 'leader':       user_type = 'faculty'
        elif user_type == 'core':            special_role = 'office_barrier'
        update_fields = {
            'email': email, 'role': role, 'user_type': user_type,
            'special_role': special_role, 'approved': approved, 'updated_at': get_indian_time()
        }
        if department:
            update_fields['department'] = department
            update_fields['profile.department'] = department
        if location:
            update_fields['location'] = location
            update_fields['profile.location'] = location
        db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_fields})
        core_chat = db.chat_groups.find_one({'group_type': 'core_team'})
        if user_type == 'core' or special_role == 'office_barrier':
            if core_chat:
                db.chat_groups.update_one({'_id':core_chat['_id']},{'$addToSet':{'members':ObjectId(user_id)}})
            else:
                db.chat_groups.insert_one({'name':'Core Team Chat','group_type':'core_team',
                    'description':'Automatic group','created_at':get_indian_time(),
                    'members':[ObjectId(user_id)],'created_by':ObjectId(user_id)})
        else:
            if core_chat:
                db.chat_groups.update_one({'_id':core_chat['_id']},{'$pull':{'members':ObjectId(user_id)}})
        if approved:
            try:
                role_msg = ("You are now a Leader." if special_role=='leader' else
                            "You are now a Core Team member." if special_role=='office_barrier' else
                            "You now have full access.")
                subject = "✅ Account Updated - OOA Microsite"
                title = "Account Status Updated"
                content_html = f"""
                Hello,<br><br>
                Your account on the OOA Microsite has been updated by the administrator.<br><br>
                <strong>Update:</strong> {role_msg}<br><br>
                You can now access your updated role dashboard.
                """
                send_microsite_email(
                    subject=subject,
                    recipients=[email],
                    title=title,
                    content_html=content_html,
                    cta_text="Log In Now",
                    cta_url="/login",
                    status_type="success",
                    status_text="Account Updated"
                )
            except Exception as e:
                logger.error(f"Update email error: {e}")
        flash('✅ User updated successfully.', 'success')
    except Exception as e:
        logger.error(f"update_user error: {e}", exc_info=True)
        flash(f'Error: {str(e)[:100]}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_user/<user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_dashboard'))
        if user['email'] == session.get('email'):
            flash('Cannot delete your own account', 'error')
            return redirect(url_for('admin_dashboard'))
        user_email = user['email']
        db.users.delete_one({'_id': ObjectId(user_id)})
        db.user_files.delete_many({'user_email': user_email})
        db.event_reminders.delete_many({'user_id': ObjectId(user_id)})
        db.event_subscriptions.delete_many({'user_id': ObjectId(user_id)})
        db.office_documents.delete_many({'user_id': ObjectId(user_id)})
        db.chat_groups.update_many({'members':ObjectId(user_id)},{'$pull':{'members':ObjectId(user_id)}})
        db.user_preferences.delete_many({'email': user_email})
        db.user_navbars.delete_many({'user_email': user_email})
        db.activity_logs.delete_many({'user_id': ObjectId(user_id)})
        db.direct_messages.delete_many({'$or':[{'sender_id':ObjectId(user_id)},{'receiver_id':ObjectId(user_id)}]})
        flash(f'✅ User {user_email} deleted.', 'success')
    except Exception as e:
        logger.error(f"delete_user error: {e}")
        flash('Error deleting user', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/campuses', methods=['POST'])
def admin_add_campus():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Campus name is required'}), 400
        if db.campuses.find_one({'name': {'$regex': f'^{name}$', '$options': 'i'}}):
            return jsonify({'success': False, 'error': 'Campus already exists'}), 400
        
        db.campuses.insert_one({'name': name})
        db.activity_logs.insert_one({
            'user_id': ObjectId(session['user_id']) if 'user_id' in session else None,
            'user_email': session['email'],
            'action': 'add_campus',
            'details': f"Admin added campus: {name}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        return jsonify({'success': True, 'message': 'Campus added successfully'})
    except Exception as e:
        logger.error(f"Error adding campus: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/campuses/edit/<campus_id>', methods=['POST'])
def admin_edit_campus(campus_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Campus name is required'}), 400
        
        existing = db.campuses.find_one({'name': {'$regex': f'^{name}$', '$options': 'i'}})
        if existing and str(existing['_id']) != campus_id:
            return jsonify({'success': False, 'error': 'Campus name already exists'}), 400
        
        db.campuses.update_one({'_id': ObjectId(campus_id)}, {'$set': {'name': name}})
        db.activity_logs.insert_one({
            'user_id': ObjectId(session['user_id']) if 'user_id' in session else None,
            'user_email': session['email'],
            'action': 'edit_campus',
            'details': f"Admin edited campus ID {campus_id} to: {name}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        return jsonify({'success': True, 'message': 'Campus updated successfully'})
    except Exception as e:
        logger.error(f"Error editing campus: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/campuses/delete/<campus_id>', methods=['DELETE', 'POST'])
def admin_delete_campus(campus_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    try:
        campus = db.campuses.find_one({'_id': ObjectId(campus_id)})
        if not campus:
            return jsonify({'success': False, 'error': 'Campus not found'}), 404
        
        db.campuses.delete_one({'_id': ObjectId(campus_id)})
        db.activity_logs.insert_one({
            'user_id': ObjectId(session['user_id']) if 'user_id' in session else None,
            'user_email': session['email'],
            'action': 'delete_campus',
            'details': f"Admin deleted campus: {campus.get('name')}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        return jsonify({'success': True, 'message': 'Campus deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting campus: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/pre_assign_leader', methods=['POST'])
def pre_assign_leader():
    if session.get('role') != 'admin': return jsonify({'error': 'Access denied'}), 403
    try:
        data   = request.get_json(force=True) or {}
        email  = data.get('email')
        school = data.get('school', '')
        if not email or not email.endswith('@jainuniversity.ac.in'):
            return jsonify({'error': 'Valid @jainuniversity.ac.in email required'}), 400
        if db.users.find_one({'email': email}):
            return jsonify({'error': 'User already registered'}), 400
        if db.pre_assigned_leaders.find_one({'email': email}):
            return jsonify({'message': 'Already pre-assigned'}), 200
        db.pre_assigned_leaders.insert_one({'email':email,'school':school,
            'assigned_by':session['email'],'assigned_at':get_indian_time()})
        try:
            content_html = f"""
            Hello,<br><br>
            You have been assigned as a <strong>Leader</strong> on the OOA Microsite.<br><br>
            Please use this email address ({email}) to register on the platform and set up your password.<br><br>
            <strong>Registration Link:</strong> <a href="{request.url_root}register" style="color:#d97706;font-weight:bold;text-decoration:none;">Click here to register</a>
            """
            send_microsite_email(
                subject="🎓 You've been assigned as Leader - Jain University",
                recipients=[email],
                title="Leader Role Assignment",
                content_html=content_html,
                cta_text="Register Now",
                cta_url="/register",
                status_type="info",
                status_text="Invitation Sent"
            )
        except Exception as e:
            logger.error(f"Pre-assign leader email error: {e}")
        return jsonify({'success': True, 'message': 'Leader assigned successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/pre_assign_core', methods=['POST'])
def pre_assign_core():
    if session.get('role') != 'admin': return jsonify({'error': 'Access denied'}), 403
    try:
        data       = request.get_json(force=True) or {}
        email      = data.get('email')
        department = data.get('department', '')
        if not email or not email.endswith('@jainuniversity.ac.in'):
            return jsonify({'error': 'Valid @jainuniversity.ac.in email required'}), 400
        if db.users.find_one({'email': email}):
            return jsonify({'error': 'User already registered'}), 400
        if db.pre_assigned_core.find_one({'email': email}):
            return jsonify({'message': 'Already pre-assigned'}), 200
        db.pre_assigned_core.insert_one({'email':email,'department':department,
            'assigned_by':session['email'],'assigned_at':get_indian_time()})
        try:
            content_html = f"""
            Hello,<br><br>
            You have been assigned as a <strong>Core Team Member</strong> on the OOA Microsite.<br><br>
            Please use this email address ({email}) to register on the platform and set up your password.<br><br>
            <strong>Registration Link:</strong> <a href="{request.url_root}register" style="color:#d97706;font-weight:bold;text-decoration:none;">Click here to register</a>
            """
            send_microsite_email(
                subject="🔷 You've been assigned as Core Team Member - Jain University",
                recipients=[email],
                title="Core Team Role Assignment",
                content_html=content_html,
                cta_text="Register Now",
                cta_url="/register",
                status_type="info",
                status_text="Invitation Sent"
            )
        except Exception as e:
            logger.error(f"Pre-assign core email error: {e}")
        return jsonify({'success': True, 'message': 'Core member assigned'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/remove_pre_assigned/<type>/<email>', methods=['DELETE'])
def remove_pre_assigned(type, email):
    if session.get('role') != 'admin': return jsonify({'error': 'Access denied'}), 403
    try:
        if type == 'leader':  db.pre_assigned_leaders.delete_one({'email': email})
        elif type == 'core':  db.pre_assigned_core.delete_one({'email': email})
        else: return jsonify({'error': 'Invalid type'}), 400
        return jsonify({'success': True, 'message': 'Removed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ══════════════════════════════════════════════════════════════════════
#  EVENTS MANAGEMENT
# ══════════════════════════════════════════════════════════════════════
@app.route("/admin/events")
def admin_events():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        events = list(db.events.find().sort('event_date', -1))
        for e in events: e["_id"] = str(e["_id"])
        return render_template("admin_events.html", events=events)
    except Exception as e:
        return render_template("admin_events.html", events=[])

@app.route("/add_event", methods=["POST"])
def add_event():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        data       = request.form.to_dict()
        image_file = request.files.get("image")
        pdf_file   = request.files.get("pdf")
        image_path = None; pdf_path = None
        if image_file and image_file.filename:
            fn = secure_filename(image_file.filename)
            ip = os.path.join(app.config["UPLOAD_FOLDER"], fn)
            image_file.save(ip)
            image_path = "/" + ip.replace("\\", "/")
        if pdf_file and pdf_file.filename:
            fn = secure_filename(pdf_file.filename)
            pp = os.path.join(app.config["UPLOAD_FOLDER"], fn)
            pdf_file.save(pp)
            pdf_path = "/" + pp.replace("\\", "/")
        db.events.insert_one({
            "event_name": data.get("event_name"), "description": data.get("description"),
            "school": data.get("school"), "department": data.get("department"),
            "event_action": data.get("event_action"), "event_type": data.get("event_type"),
            "venue": data.get("venue"), "event_date": data.get("event_date"),
            "end_date": data.get("end_date"), "event_time": data.get("event_time","All Day"),
            "image": image_path, "pdf": pdf_path, "created_at": get_indian_time()
        })
        flash('✅ Event added!', 'success')
    except Exception as e:
        logger.error(f"add_event error: {e}")
        flash('Error adding event', 'error')
    return redirect(url_for('admin_events'))

@app.route("/delete_event/<event_id>")
def delete_event(event_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        db.events.delete_one({"_id": ObjectId(event_id)})
        flash('✅ Event deleted!', 'success')
    except:
        flash('Error deleting event', 'error')
    return redirect(url_for('admin_events'))

@app.route("/edit_event/<event_id>", methods=["GET"])
def edit_event(event_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        event = db.events.find_one({"_id": ObjectId(event_id)})
        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('admin_events'))
        event["_id"] = str(event["_id"])
        return render_template("edit_event.html", event=event)
    except:
        flash('Error loading event', 'error')
        return redirect(url_for('admin_events'))

@app.route("/update_event/<event_id>", methods=["POST"])
def update_event(event_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        data       = request.form.to_dict()
        image_file = request.files.get("image")
        pdf_file   = request.files.get("pdf")
        update_data = {
            "event_name": data.get("event_name"), "description": data.get("description"),
            "school": data.get("school"), "department": data.get("department"),
            "event_action": data.get("event_action"), "event_type": data.get("event_type"),
            "venue": data.get("venue"), "event_date": data.get("event_date"),
            "end_date": data.get("end_date"), "event_time": data.get("event_time","All Day"),
            "updated_at": get_indian_time()
        }
        if image_file and image_file.filename:
            fn = secure_filename(image_file.filename)
            ip = os.path.join(app.config["UPLOAD_FOLDER"], fn)
            image_file.save(ip)
            update_data["image"] = "/" + ip.replace("\\", "/")
        if pdf_file and pdf_file.filename:
            fn = secure_filename(pdf_file.filename)
            pp = os.path.join(app.config["UPLOAD_FOLDER"], fn)
            pdf_file.save(pp)
            update_data["pdf"] = "/" + pp.replace("\\", "/")
        db.events.update_one({"_id": ObjectId(event_id)}, {"$set": update_data})
        flash('✅ Event updated!', 'success')
    except:
        flash('Error updating event', 'error')
    return redirect(url_for('admin_events'))

# ══════════════════════════════════════════════════════════════════════
#  ERP PORTAL (Semester Readiness & Closure) — integrated blueprint
# ══════════════════════════════════════════════════════════════════════
from erp_portal import erp_bp
app.register_blueprint(erp_bp, url_prefix='/erp')
logger.info("✅ ERP portal (readiness/closure) mounted at /erp")

# ── Academic Calendar 2026–27 (self-contained page, served in-app) ──
@app.route('/calendar')
def academic_calendar():
    return render_template('academic_calendar.html')

# ══════════════════════════════════════════════════════════════════════
#  ERP / EXTERNAL PORTAL LINKS  (Academic Calendar · Readiness · Closure)
# ══════════════════════════════════════════════════════════════════════
ERP_READINESS_URL = os.getenv("ERP_READINESS_URL", "/erp/readiness")
ERP_CLOSURE_URL   = os.getenv("ERP_CLOSURE_URL",   "/erp/closure")
ACADEMIC_CALENDAR_URL = os.getenv("ACADEMIC_CALENDAR_URL", "/calendar")

@app.context_processor
def inject_erp_links():
    return dict(
        erp_readiness_url=ERP_READINESS_URL,
        erp_closure_url=ERP_CLOSURE_URL,
        academic_calendar_url=ACADEMIC_CALENDAR_URL
    )

# ══════════════════════════════════════════════════════════════════════
#  CAMPUS GALLERY  (image tiles: title · description · date happened)
#  Admins & department leaders can add moments; each moment is mirrored
#  into db.events so it appears in the events feed and supports the
#  existing email-reminder system directly.
# ══════════════════════════════════════════════════════════════════════
GALLERY_IMG_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def can_manage_gallery():
    return session.get('role') == 'admin' or session.get('special_role') == 'leader'

def _gallery_departments():
    """Union of known department names for the add-form dropdown."""
    try:
        depts = set()
        for src in (db.campus_gallery.distinct('department'),
                    db.events.distinct('department'),
                    db.users.distinct('profile.department'),
                    db.users.distinct('department')):
            for d in src:
                if d and isinstance(d, str) and d.strip():
                    depts.add(d.strip())
        return sorted(depts)
    except Exception:
        return []

@app.route('/campus')
@login_required
def campus():
    return render_template('campus.html',
        user_logged_in=True,
        user_email=session.get('email', ''),
        user_role=session.get('role', ''),
        special_role=session.get('special_role'),
        can_manage=can_manage_gallery(),
        user_department=session.get('user_department', ''))

@app.route('/api/campus_gallery')
@login_required
def api_campus_gallery():
    try:
        dept = (request.args.get('department') or '').strip()

        def _fetch():
            return [serialize_doc(d) for d in
                    db.campus_gallery.find({}).sort([('date_happened', -1), ('created_at', -1)]).limit(200)]

        items = get_cached_dashboard_data('campus_gallery', _fetch, ttl=10)
        if dept:
            items = [i for i in items if (i.get('department') or '') == dept]

        try:
            campuses = get_cached_dashboard_data(
                'campuses_list', lambda: sorted([c['name'] for c in db.campuses.find({}, {'name': 1}) if c.get('name')]), ttl=60)
        except Exception:
            campuses = []

        return jsonify({
            'success': True,
            'items': items,
            'departments': get_cached_dashboard_data('gallery_departments', _gallery_departments, ttl=60),
            'campuses': campuses,
            'can_manage': can_manage_gallery()
        })
    except Exception as e:
        logger.error(f"api_campus_gallery error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'items': []}), 500

@app.route('/api/campus_gallery/add', methods=['POST'])
@login_required
def api_campus_gallery_add():
    if not can_manage_gallery():
        return jsonify({'success': False, 'error': 'Only admins and department leaders can add campus moments'}), 403
    try:
        title         = (request.form.get('title') or '').strip()
        description   = (request.form.get('description') or '').strip()
        date_happened = normalize_date((request.form.get('date_happened') or '').strip())
        department    = (request.form.get('department') or '').strip()
        campus_name   = (request.form.get('campus') or '').strip()
        image_file    = request.files.get('image')

        if not title:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        if not date_happened:
            return jsonify({'success': False, 'error': 'Date is required'}), 400
        if not image_file or not image_file.filename:
            return jsonify({'success': False, 'error': 'Image is required'}), 400

        ext = image_file.filename.rsplit('.', 1)[-1].lower() if '.' in image_file.filename else ''
        if ext not in GALLERY_IMG_EXT:
            return jsonify({'success': False, 'error': 'Image must be PNG / JPG / GIF / WEBP'}), 400

        fn = secure_filename(image_file.filename)
        fn = f"campus_{int(time.time())}_{fn}"
        ip = os.path.join(app.config['UPLOAD_FOLDER'], fn)
        image_file.save(ip)
        image_path = '/' + ip.replace('\\', '/')

        # Mirror into events so it shows in the events feed & supports reminders
        event_doc = {
            'event_name': title,
            'description': description,
            'school': '', 'department': department,
            'event_action': 'campus_gallery',
            'event_type': 'Campus Highlight',
            'venue': campus_name or 'Campus',
            'event_date': date_happened, 'end_date': '',
            'event_time': 'All Day',
            'image': image_path, 'pdf': None,
            'created_at': get_indian_time()
        }
        event_id = db.events.insert_one(event_doc).inserted_id

        gallery_doc = {
            'title': title,
            'description': description,
            'date_happened': date_happened,
            'department': department,
            'campus': campus_name,
            'image': image_path,
            'event_id': event_id,
            'added_by': session.get('email', ''),
            'added_by_role': 'admin' if session.get('role') == 'admin' else 'leader',
            'created_at': get_indian_time()
        }
        gid = db.campus_gallery.insert_one(gallery_doc).inserted_id

        # bust caches so it appears immediately
        for k in ('campus_gallery', 'campus_gallery_home', 'all_events', 'gallery_departments'):
            GLOBAL_DASHBOARD_CACHE.pop(k, None)

        db.activity_logs.insert_one({
            'user_email': session.get('email', ''),
            'action': 'add_campus_moment',
            'details': f"Added campus moment: {title} ({department or 'no dept'})",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        return jsonify({'success': True, 'id': str(gid), 'event_id': str(event_id),
                        'message': 'Campus moment added'})
    except Exception as e:
        logger.error(f"api_campus_gallery_add error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/campus_gallery/<item_id>', methods=['DELETE'])
@login_required
def api_campus_gallery_delete(item_id):
    try:
        item = db.campus_gallery.find_one({'_id': ObjectId(item_id)})
        if not item:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        is_owner = item.get('added_by') == session.get('email')
        if not (session.get('role') == 'admin' or (can_manage_gallery() and is_owner)):
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        db.campus_gallery.delete_one({'_id': item['_id']})
        if item.get('event_id'):
            db.events.delete_one({'_id': item['event_id']})
            db.event_reminders.delete_many({'event_id': item['event_id']})

        for k in ('campus_gallery', 'campus_gallery_home', 'all_events'):
            GLOBAL_DASHBOARD_CACHE.pop(k, None)

        db.activity_logs.insert_one({
            'user_email': session.get('email', ''),
            'action': 'delete_campus_moment',
            'details': f"Deleted campus moment: {item.get('title')}",
            'timestamp': get_indian_time(),
            'ip_address': request.remote_addr
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"api_campus_gallery_delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  UGC / MONTHLY ENGAGEMENT / NEWSLETTER
# ══════════════════════════════════════════════════════════════════════
@app.route('/edit_ugc', methods=['GET', 'POST'])
def edit_ugc():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            text_data           = request.form.get('text_data')
            external_link       = request.form.get('external_link')
            selected_categories = request.form.getlist('categories')
            uploaded_files      = []
            for file in request.files.getlist('files'):
                if file and allowed_file(file.filename):
                    fn = secure_filename(file.filename)
                    fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                    file.save(fp)
                    uploaded_files.append(fn)
            db.ugc_data.insert_one({
                "admin_email": session['email'], "uploaded_at": get_indian_time(),
                "categories": selected_categories, "text_data": text_data,
                "external_link": external_link, "files": uploaded_files
            })
            flash('✅ UGC data uploaded.', 'success')
            return redirect(url_for('edit_ugc'))
        except Exception as e:
            flash('Error uploading data', 'error')
    try:
        return render_template('edit_ugc.html', records=list(db.ugc_data.find().sort('uploaded_at',-1)))
    except:
        return render_template('edit_ugc.html', records=[])

@app.route('/edit_ugc_record/<record_id>', methods=['GET', 'POST'])
def edit_ugc_record(record_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        record = db.ugc_data.find_one({'_id': ObjectId(record_id)})
        if not record:
            flash('Record not found', 'error')
            return redirect(url_for('edit_ugc'))
        if request.method == 'POST':
            text_data           = request.form.get('text_data')
            external_link       = request.form.get('external_link')
            selected_categories = request.form.getlist('categories')
            updated_files       = record.get('files', [])
            for file in request.files.getlist('files'):
                if file and allowed_file(file.filename):
                    fn = secure_filename(file.filename)
                    fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                    file.save(fp)
                    updated_files.append(fn)
            db.ugc_data.update_one({'_id':ObjectId(record_id)},
                {'$set':{'text_data':text_data,'external_link':external_link,
                          'categories':selected_categories,'files':updated_files}})
            flash('✅ UGC record updated.', 'success')
            return redirect(url_for('edit_ugc'))
        return render_template('edit_ugc_record.html', record=record)
    except Exception as e:
        flash('Error processing request', 'error')
        return redirect(url_for('edit_ugc'))

@app.route('/delete_ugc/<record_id>', methods=['GET'])
def delete_ugc(record_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        db.ugc_data.delete_one({'_id': ObjectId(record_id)})
        flash('✅ UGC record deleted.', 'success')
    except:
        flash('Error deleting record', 'error')
    return redirect(url_for('edit_ugc'))

@app.route('/edit_monthly', methods=['GET', 'POST'])
def edit_monthly():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            heading     = request.form.get('heading','').strip()
            description = request.form.get('description','').strip()
            school      = request.form.get('school','')
            department  = request.form.get('department','')
            tags        = request.form.getlist('tags')
            uploaded_files = []
            for file in [request.files.get('image_file'), request.files.get('pdf_file')]:
                if file and file.filename and allowed_file(file.filename):
                    fn = secure_filename(file.filename)
                    fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                    file.save(fp)
                    uploaded_files.append(fn)
            db.monthly_engagement.insert_one({
                "admin_email": session.get('email'), "uploaded_at": get_indian_time(),
                "heading": heading, "description": description, "school": school,
                "department": department, "tags": tags, "files": uploaded_files
            })
            flash('✅ Monthly engagement uploaded.', 'success')
            return redirect(url_for('edit_monthly'))
        except:
            flash('Error uploading data', 'error')
    try:
        return render_template('edit_monthly.html', records=list(db.monthly_engagement.find().sort('uploaded_at',-1)))
    except:
        return render_template('edit_monthly.html', records=[])

@app.route('/edit_record/<record_id>', methods=['GET', 'POST'])
def edit_record(record_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        record = db.monthly_engagement.find_one({'_id': ObjectId(record_id)})
        if not record:
            flash('Record not found', 'error')
            return redirect(url_for('edit_monthly'))
        if request.method == 'POST':
            updated = {}
            for field in ['heading','description','school','department']:
                if field in request.form:
                    updated[field] = request.form.get(field,'').strip()
            if 'tags' in request.form:
                updated['tags'] = request.form.getlist('tags')
            if updated:
                db.monthly_engagement.update_one({'_id':ObjectId(record_id)},{'$set':updated})
                flash('✅ Record updated.', 'success')
            return redirect(url_for('edit_monthly'))
        return render_template('edit_record.html', record=record)
    except:
        flash('Error processing request', 'error')
        return redirect(url_for('edit_monthly'))

@app.route('/delete_record/<record_id>', methods=['POST'])
def delete_record(record_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        record = db.monthly_engagement.find_one({'_id': ObjectId(record_id)})
        if record and 'files' in record:
            for fn in record['files']:
                fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                if os.path.exists(fp): os.remove(fp)
        db.monthly_engagement.delete_one({'_id': ObjectId(record_id)})
        flash('✅ Record deleted.', 'success')
    except:
        flash('Error deleting record', 'error')
    return redirect(url_for('edit_monthly'))

@app.route('/usernewsletters')
def usernewsletters():
    try:
        return render_template('user_newsletters.html', records=list(db.newsletters.find().sort('uploaded_at',-1)))
    except:
        return render_template('user_newsletters.html', records=[])

@app.route('/newsletter', methods=['GET', 'POST'])
def newsletter():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            title               = request.form.get('title')
            description         = request.form.get('description')
            tags                = request.form.getlist('tags')
            image_file          = request.files.get('image')
            recipient_email_raw = request.form.get('recipient_email','').strip()
            email_list = []
            def is_valid_email(e):
                return re.match(r"[^@]+@[^@]+\.[^@]+", e)
            try:
                parsed = json.loads(recipient_email_raw)
                email_list = [e['value'].strip() for e in parsed if 'value' in e and is_valid_email(e['value'].strip())]
            except:
                email_list = [e.strip() for e in recipient_email_raw.split(',') if is_valid_email(e.strip())]
            if not email_list:
                flash("❌ No valid email addresses.", "error")
                return redirect(url_for('newsletter'))
            image_filename = None
            if image_file and allowed_file(image_file.filename):
                image_filename = secure_filename(image_file.filename)
                image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            db.newsletters.insert_one({
                "admin_email": session['email'], "uploaded_at": get_indian_time(),
                "title": title, "description": description, "tags": tags,
                "image": image_filename, "recipients": email_list
            })
            send_newsletter_email(title, description, image_filename, email_list)
            flash('✅ Newsletter sent.', 'success')
            return redirect(url_for('newsletter'))
        except Exception as e:
            logger.error(f"newsletter POST error: {e}")
            flash('Error creating newsletter', 'error')
    try:
        return render_template('admin_newsletter.html', records=list(db.newsletters.find().sort('uploaded_at',-1)))
    except:
        return render_template('admin_newsletter.html', records=[])

@app.route('/edit_newsletter/<id>', methods=['GET'])
def edit_newsletter(id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        record = db.newsletters.find_one({'_id': ObjectId(id)})
        if not record:
            flash('Newsletter not found.', 'error')
            return redirect(url_for('newsletter'))
        return render_template('edit_newsletter.html', record=record)
    except:
        flash('Error loading newsletter', 'error')
        return redirect(url_for('newsletter'))

@app.route('/update_newsletter/<id>', methods=['POST'])
def update_newsletter(id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        record = db.newsletters.find_one({'_id': ObjectId(id)})
        if not record:
            flash('Newsletter not found.', 'error')
            return redirect(url_for('newsletter'))
        title      = request.form.get('title')
        description= request.form.get('description')
        tags       = request.form.getlist('tags')
        recipients = [e.strip() for e in request.form.get('recipient_email','').split(',') if e.strip()]
        image_file = request.files.get('image')
        image_filename = record.get('image')
        if image_file and image_file.filename:
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        db.newsletters.update_one({'_id':ObjectId(id)},
            {'$set':{'title':title,'description':description,'tags':tags,
                     'recipients':recipients,'image':image_filename,'updated_at':get_indian_time()}})
        flash('✅ Newsletter updated!', 'success')
        return redirect(url_for('newsletter'))
    except:
        flash('Error updating newsletter', 'error')
        return redirect(url_for('newsletter'))

@app.route('/newsletter/delete/<id>')
def delete_newsletter(id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    try:
        db.newsletters.delete_one({"_id": ObjectId(id)})
        flash("✅ Newsletter deleted.", 'success')
    except:
        flash('Error deleting newsletter', 'error')
    return redirect(url_for('newsletter'))

@app.route('/subscribe_newsletter', methods=['POST'])
def subscribe_newsletter():
    try:
        email = request.form.get('email')
        if not email:
            flash("Email is required.", "error")
            return redirect(request.referrer or url_for('jainevents'))
        if db.subscribers.find_one({'email': email}):
            flash("You are already subscribed!", "info")
        else:
            db.subscribers.insert_one({'email': email, 'subscribed_at': get_indian_time()})
            try:
                subject = "🎉 Subscribed to Jain University Newsletter"
                title = "Newsletter Subscription"
                content_html = """
                Hello,<br><br>
                Thank you for subscribing to the Jain University newsletter!<br>
                You will now receive the latest updates, event announcements, and newsletters directly to your inbox.<br><br>
                Stay tuned for our upcoming editions!
                """
                send_microsite_email(
                    subject=subject,
                    recipients=[email],
                    title=title,
                    content_html=content_html,
                    status_type="success",
                    status_text="Subscription Active"
                )
                flash("✅ Subscribed successfully!", "success")
            except:
                flash("Subscribed, but confirmation email failed.", "warning")
        return redirect(request.referrer or url_for('jainevents'))
    except:
        flash('Error processing subscription', 'error')
        return redirect(request.referrer or url_for('jainevents'))

@app.route('/newsletter_view/<newsletter_id>')
def newsletter_view(newsletter_id):
    try:
        news = db.newsletters.find_one({'_id': ObjectId(newsletter_id)})
        if not news:
            flash('Newsletter not found', 'error')
            return redirect(url_for('newsletter_page'))
        news['_id'] = str(news['_id'])
        news['formatted_date'] = news['uploaded_at'].strftime('%B %d, %Y') if isinstance(news.get('uploaded_at'), datetime) else str(news.get('uploaded_at',''))
        return render_template('newsletter_detail.html', news=news,
                               user_logged_in='email' in session,
                               user_email=session.get('email'),
                               user_navbar=get_user_navbar(session.get('email','')) if session.get('email') else [])
    except Exception as e:
        logger.error(f"newsletter_view error: {e}", exc_info=True)
        flash('Error loading newsletter', 'error')
        return redirect(url_for('newsletter_page'))

@app.route('/newsletters')
def newsletter_page():
    try:
        records = list(db.newsletters.find().sort('uploaded_at', -1))
        for article in records:
            article['_id'] = str(article['_id'])
            article['formatted_date'] = article['uploaded_at'].strftime('%B %d, %Y') if isinstance(article.get('uploaded_at'), datetime) else str(article.get('uploaded_at',''))
        return render_template('newsletter_page.html', records=records,
                               user_logged_in='email' in session,
                               user_email=session.get('email'),
                               user_navbar=get_user_navbar(session.get('email','')) if session.get('email') else [])
    except Exception as e:
        logger.error(f"newsletter_page error: {e}", exc_info=True)
        return render_template('newsletter_page.html', records=[], user_logged_in='email' in session, user_email=session.get('email'))

# ══════════════════════════════════════════════════════════════════════
#  API ENDPOINTS — EVENTS
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/events')
def get_events():
    try:
        current_date = datetime.now().strftime('%Y-%m-%d')
        events = list(db.events.find(
            {"$or":[{"event_date":{"$gte":current_date}},{"end_date":{"$gte":current_date}}]}
        ).sort("event_date", 1))
        return jsonify([{
            'id': str(e['_id']), 'event_name': e.get('event_name',''),
            'event_date': e.get('event_date',''), 'end_date': e.get('end_date',''),
            'event_time': e.get('event_time','All Day'), 'venue': e.get('venue','TBA'),
            'description': e.get('description',''), 'event_type': e.get('event_type',''),
            'school': e.get('school',''), 'department': e.get('department',''),
            'image': e.get('image',''), 'pdf': e.get('pdf','')
        } for e in events])
    except:
        return jsonify([])

@app.route('/api/events/<event_id>')
def get_event(event_id):
    try:
        event = db.events.find_one({"_id": ObjectId(event_id)})
        if not event: return jsonify({'error': 'Event not found'}), 404
        return jsonify({'id': str(event['_id']), 'event_name': event.get('event_name',''),
                        'event_date': event.get('event_date',''), 'end_date': event.get('end_date',''),
                        'event_time': event.get('event_time','All Day'), 'venue': event.get('venue','TBA'),
                        'description': event.get('description',''), 'event_type': event.get('event_type',''),
                        'school': event.get('school',''), 'department': event.get('department',''),
                        'image': event.get('image',''), 'pdf': event.get('pdf','')})
    except:
        return jsonify({'error': 'Event not found'}), 404

@app.route("/api/events/today")
def get_today_events():
    try:
        today = get_today_ist_string()
        events_data = []
        for event in list(db.events.find({})):
            event_date = normalize_date(event.get("event_date",""))
            end_date   = normalize_date(event.get("end_date","")) if event.get("end_date") else ""
            if event_date == today or (end_date and event_date <= today <= end_date):
                events_data.append({
                    "id": str(event["_id"]), "event_name": event.get("event_name",""),
                    "event_date": event_date, "event_time": event.get("event_time","All Day"),
                    "venue": event.get("venue","TBA")
                })
        return jsonify(events_data)
    except:
        return jsonify([])

@app.route('/api/events/filter')
def filter_events():
    try:
        query = {}
        department = request.args.get('department')
        school     = request.args.get('school')
        start_date = request.args.get('start_date')
        end_date   = request.args.get('end_date')
        event_type = request.args.get('event_type')
        if department: query['department'] = department
        if school:     query['school']     = school
        if event_type: query['event_type'] = event_type
        if start_date and end_date: query['event_date'] = {'$gte':start_date,'$lte':end_date}
        elif start_date:            query['event_date'] = {'$gte':start_date}
        elif end_date:              query['event_date'] = {'$lte':end_date}
        events = list(db.events.find(query).sort('event_date', 1))
        return jsonify([{'id':str(e['_id']),'event_name':e.get('event_name',''),
                         'event_date':e.get('event_date',''),'end_date':e.get('end_date',''),
                         'event_time':e.get('event_time','All Day'),'venue':e.get('venue',''),
                         'description':e.get('description',''),'event_type':e.get('event_type',''),
                         'school':e.get('school',''),'department':e.get('department',''),
                         'image':e.get('image',''),'pdf':e.get('pdf','')} for e in events])
    except:
        return jsonify([])

@app.route('/api/departments')
def get_departments():
    try: return jsonify(sorted([d for d in db.events.distinct('department') if d]))
    except: return jsonify([])

@app.route('/api/schools')
def get_schools():
    try: return jsonify(sorted([s for s in db.events.distinct('school') if s]))
    except: return jsonify([])

# ══════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS API
# ══════════════════════════════════════════════════════════════════════
@app.route('/api/notifications')
@login_required
def api_notifications():
    try:
        notifications = get_user_notifications()
        return jsonify({'success': True, 'notifications': notifications, 'count': len(notifications)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/mark_notification_read/<notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    return jsonify({'success': True})

# ══════════════════════════════════════════════════════════════════════
#  DEPARTMENT REPOSITORY
# ══════════════════════════════════════════════════════════════════════
@app.route('/dept_repo')
@login_required
def dept_repo():
    ui = _get_user_info()
    if not ui['approved']:
        flash('Your account is pending approval.', 'warning')
        return redirect(url_for('home'))
    _track_activity()
    today_str   = date.today().isoformat()
    user_dept   = session.get('user_department', '')
    docs        = list(db.dept_repo_docs.find({'departments':user_dept}).sort('uploaded_at',-1)) if user_dept else []
    for d in docs: d['_id'] = str(d['_id'])
    recent_count  = sum(1 for d in docs if isinstance(d.get('uploaded_at'), datetime) and (datetime.utcnow()-d['uploaded_at']).days<=30)
    faculty_count = sum(1 for d in docs if d.get('source') == 'faculty')
    return render_template('dept_repo.html', docs=docs, today_str=today_str,
                           recent_count=recent_count, faculty_count=faculty_count, **ui)

@app.route('/university_repo')
@login_required
def university_repo():
    ui = _get_user_info()
    if not ui['approved']:
        flash('Your account is pending approval.', 'warning')
        return redirect(url_for('home'))
    _track_activity()
    today_str = date.today().isoformat()
    user_dept = session.get('user_department', '')
    
    # Filter documents uploaded by core/leader that target this department or "All Departments"
    # and have not expired (or end_date is not set)
    query = {
        '$and': [
            {'$or': [
                {'departments': user_dept},
                {'departments': 'All Departments'},
                {'departments': 'All'}
            ]},
            {'source': {'$ne': 'faculty'}},
            {'$or': [
                {'end_date': {'$exists': False}},
                {'end_date': None},
                {'end_date': ''},
                {'end_date': {'$gte': today_str}}
            ]}
        ]
    }
    docs = list(db.dept_repo_docs.find(query).sort('uploaded_at', -1))
    for d in docs:
        d['_id'] = str(d['_id'])
        
    recent_count = sum(1 for d in docs if isinstance(d.get('uploaded_at'), datetime) and (datetime.utcnow() - d['uploaded_at']).days <= 30)
    
    return render_template('university_repo.html', docs=docs, today_str=today_str,
                           recent_count=recent_count, **ui)

@app.route('/view_doc/<doc_id>')
@login_required
def view_doc(doc_id):
    ui = _get_user_info()
    if not ui['approved']:
        flash('Your account is pending approval.', 'warning')
        return redirect(url_for('home'))
        
    try:
        doc = db.dept_repo_docs.find_one({'_id': ObjectId(doc_id)})
        if not doc:
            flash('Document not found.', 'error')
            return redirect(url_for('home'))
            
        filename = doc['files'][0] if doc.get('files') else None
        if not filename:
            flash('No file attached to this document.', 'error')
            return redirect(url_for('home'))
            
        file_url = url_for('uploaded_file', filename=filename)
        return render_template('view_doc.html', file_url=file_url, doc=doc, **ui)
    except Exception as e:
        logger.error(f"Error in view_doc: {e}", exc_info=True)
        flash('Invalid document ID or system error.', 'error')
        return redirect(url_for('home'))

@app.route('/faculty_upload', methods=['POST'])
@login_required
def faculty_upload():
    if not session.get('approved'): return jsonify({'success':False,'error':'Account not approved'}), 403
    user = db.users.find_one({'email': session['email']})
    if not user: return jsonify({'success':False,'error':'User not found'}), 404
    title       = request.form.get('title','').strip()
    description = request.form.get('description','').strip()
    doc_date    = request.form.get('doc_date','').strip()
    uploaded_files = []
    file = request.files.get('file')
    if file and file.filename:
        if not allowed_file(file.filename):
            flash('File type not allowed.', 'error')
            return redirect(url_for('dept_repo'))
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        ufn  = f"{base}_{int(datetime.utcnow().timestamp())}{ext}"
        fp   = os.path.join(app.config.get('UPLOAD_FOLDER','static/uploads'), ufn)
        file.save(fp)
        uploaded_files.append(ufn)
    user_dept = session.get('user_department', (user.get('profile',{}) or {}).get('department',''))
    db.dept_repo_docs.insert_one({
        'title': title or None, 'description': description or None,
        'departments': [user_dept] if user_dept else [],
        'doc_date': doc_date or None, 'files': uploaded_files,
        'uploaded_by': session['email'], 'uploaded_by_dept': user_dept,
        'source': 'faculty', 'uploaded_at': datetime.utcnow()
    })
    flash('✅ Document submitted and visible to the core team.', 'success')
    return redirect(url_for('dept_repo'))

@app.route('/core_repo')
@_core_or_leader_required
def core_repo():
    ui        = _get_user_info()
    today_str = date.today().isoformat()
    _track_activity()
    repo_docs = list(db.dept_repo_docs.find({}).sort('uploaded_at',-1))
    for d in repo_docs: d['_id'] = str(d['_id'])
    faculty_submissions = [d for d in repo_docs if d.get('source') == 'faculty']
    core_uploads        = [d for d in repo_docs if d.get('source') != 'faculty']
    seen, all_depts_with_docs = set(), []
    for d in repo_docs:
        for dept in (d.get('departments') or []):
            if dept not in seen:
                seen.add(dept)
                all_depts_with_docs.append(dept)
    return render_template('core_repo.html', repo_docs=repo_docs,
                           faculty_submissions=faculty_submissions, core_uploads=core_uploads,
                           today_str=today_str, all_depts_with_docs=all_depts_with_docs,
                           faculty_count=len(faculty_submissions), **ui)

@app.route('/core_repo_upload', methods=['POST'])
@_core_or_leader_required
def core_repo_upload():
    title       = request.form.get('title','').strip()
    description = request.form.get('description','').strip()
    doc_date    = request.form.get('doc_date','').strip()
    end_date    = request.form.get('end_date','').strip()
    departments = request.form.getlist('departments')
    if not departments:
        flash('Please select at least one department.', 'error')
        return redirect(url_for('core_repo'))
    security_level = request.form.get('security_level', 'view_only').strip()
    uploaded_files = []
    file = request.files.get('file')
    if file and file.filename:
        if not _allowed(file.filename):
            flash('File type not allowed.', 'error')
            return redirect(url_for('core_repo'))
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        ufn  = f"{base}_{int(datetime.utcnow().timestamp())}{ext}"
        fp   = os.path.join(app.config.get('UPLOAD_FOLDER','uploads'), ufn)
        file.save(fp)
        uploaded_files.append(ufn)
    db.dept_repo_docs.insert_one({
        'title': title or None, 'description': description or None,
        'departments': departments, 'doc_date': doc_date or None,
        'end_date': end_date or None, 'files': uploaded_files,
        'uploaded_by': session.get('email',''), 'source': 'core',
        'security_level': security_level,
        'uploaded_at': datetime.utcnow()
    })
    dept_label = ', '.join(d.replace('Department of ','') for d in departments[:3])
    if len(departments) > 3: dept_label += f' +{len(departments)-3} more'
    _track_activity(f"Core upload: {title or 'Untitled'} → {dept_label}")
    flash(f'✅ Document uploaded to: {dept_label}', 'success')
    return redirect(url_for('core_repo'))

@app.route('/core_repo_delete', methods=['POST'])
@_core_or_leader_required
def core_repo_delete():
    data   = request.get_json(force=True) or {}
    doc_id = data.get('doc_id')
    if not doc_id: return jsonify({'success': False, 'error': 'Missing document ID'})
    try:
        doc    = db.dept_repo_docs.find_one({'_id': ObjectId(doc_id)})
        result = db.dept_repo_docs.delete_one({'_id': ObjectId(doc_id)})
        if result.deleted_count:
            _track_activity(f"Deleted doc: {doc.get('title','Untitled') if doc else doc_id}")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Document not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ══════════════════════════════════════════════════════════════════════
#  UTILITY / DEBUG ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route('/init_core_chat')
@login_required
def init_core_chat():
    if session.get('role') != 'admin': return jsonify({'error': 'Access denied'}), 403
    try:
        existing = db.chat_groups.find_one({'group_type': 'core_team'})
        if existing:
            return jsonify({'message': 'Core team chat already exists', 'group_id': str(existing['_id'])})
        core_members = list(db.users.find({'$or':[{'user_type':'core'},{'special_role':'office_barrier'}],'approved':True}))
        group_id = db.chat_groups.insert_one({
            'name': 'Core Team Chat', 'group_type': 'core_team',
            'description': 'Automatic chat group', 'created_at': get_indian_time(),
            'created_by': None, 'members': [m['_id'] for m in core_members]
        }).inserted_id
        return jsonify({'success': True, 'message': 'Core team chat created',
                        'group_id': str(group_id), 'members_added': len(core_members)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/my-session')
@login_required
def debug_my_session():
    try:
        user = db.users.find_one({'email': session['email']})
        if not user: return jsonify({'error': 'User not found'}), 404
        return jsonify({
            'session':  {'email':session.get('email'),'role':session.get('role'),
                         'user_type':session.get('user_type'),'special_role':session.get('special_role'),
                         'approved':session.get('approved')},
            'database': {'email':user.get('email'),'role':user.get('role'),
                         'user_type':user.get('user_type'),'special_role':user.get('special_role'),
                         'approved':user.get('approved')},
            'is_leader':     is_leader(),
            'is_core_member':is_core_member()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/check-collections')
@login_required
def debug_check_collections():
    try:
        return jsonify({
            'collections':  db.list_collection_names(),
            'users_count':  db.users.count_documents({}),
            'leaders_count':db.users.count_documents({'special_role':'leader'}),
            'core_count':   db.users.count_documents({'$or':[{'user_type':'core'},{'special_role':'office_barrier'}]}),
            'tasks_count':  db.tasks.count_documents({}),
            'docs_count':   db.office_documents.count_documents({}),
            'dm_count':     db.direct_messages.count_documents({})
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/users')
def debug_users():
    if session.get('role') != 'admin': return jsonify({'error': 'Admin access required'}), 403
    try:
        users = list(db.users.find({}))
        return jsonify({'total_users': len(users), 'users': [
            {'id':str(u.get('_id')),'email':u.get('email'),'role':u.get('role'),
             'user_type':u.get('user_type'),'special_role':u.get('special_role'),'approved':u.get('approved',False)}
            for u in users
        ]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/setup/admin')
def setup_admin():
    try:
        admin_exists = db.users.find_one({'role': 'admin'})
        if admin_exists:
            return jsonify({'message': 'Admin already exists', 'admin_email': admin_exists.get('email')})
        admin_email    = 'admin@jainuniversity.ac.in'
        admin_password = 'admin123'
        db.users.insert_one({
            'email': admin_email, 'password': generate_password_hash(admin_password),
            'role': 'admin', 'user_type': 'admin', 'special_role': None, 'approved': True,
            'is_online': True, 'last_seen': get_indian_time(), 'created_at': get_indian_time()
        })
        return jsonify({'message': 'Admin created!', 'email': admin_email, 'password': admin_password,
                        'note': 'Change the password immediately after login!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/debug/events")
def debug_events():
    try:
        today_str = get_today_ist_string()
        events    = list(db.events.find({}).limit(15))
        samples   = []
        for ev in events:
            raw  = ev.get("event_date","NO_DATE")
            norm = normalize_date(str(raw))
            samples.append({'name':ev.get("event_name",""),'raw_date':str(raw),'normalized':norm,
                            'is_today':norm==today_str,'is_future':norm>today_str if norm else False})
        return jsonify({'today_ist':today_str,'total_events':db.events.count_documents({}),'event_samples':samples})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  CRON / TEST EMAIL
# ══════════════════════════════════════════════════════════════════════
@app.route('/cron/send-reminders')
def cron_send_reminders():
    api_key = request.args.get('key')
    if api_key != os.environ.get('CRON_API_KEY', 'your-secret-key-here'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        with app.app_context():
            send_event_reminders()
        return jsonify({'success': True, 'message': 'Reminders sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/test-email')
def test_email():
    try:
        msg = Message(subject="Test Email", sender=app.config['MAIL_USERNAME'],
                      recipients=[app.config['MAIL_USERNAME']])
        msg.body = "Test email from reminder system."
        mail.send(msg)
        return jsonify({"success": True, "message": "Test email sent"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
#  FILE SERVING
# ══════════════════════════════════════════════════════════════════════
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        logger.error(f"File serve error {filename}: {e}")
        return "File not found", 404

# ══════════════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════════
@app.errorhandler(401)
def unauthorized(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    return redirect(url_for('login'))

@app.errorhandler(403)
def forbidden(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return redirect(url_for('home'))

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'File too large. Maximum size is 50MB.'}), 413
    flash('File too large. Maximum size is 50MB.', 'error')
    return redirect(request.referrer or url_for('home'))

# ══════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    create_indexes()
    is_local = os.environ.get('FLASK_ENV', 'production') == 'development'
    if is_local:
        scheduler = BackgroundScheduler(timezone=IST)
        @scheduler.scheduled_job('interval', seconds=30, id='reminder_check')
        def scheduled_reminders():
            with app.app_context():
                try:
                    send_event_reminders()
                except Exception as e:
                    logger.error(f"[SCHEDULER ERROR] {e}")
        scheduler.start()
        logger.info("✅ Scheduler started (DEV)")
    else:
        logger.info("⚠️ Production — use /cron/send-reminders instead of APScheduler")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=is_local, use_reloader=False)