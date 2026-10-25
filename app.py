"""
VisaHoBe - All-in-One Visa Agency OS
Your Dream Abroad Starts Here
One file backend. Port 5001. 100% free stack. Ready to deploy.
"""
import json, os, re, io, csv, time, smtplib, asyncio, threading
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, send_from_directory, render_template, Response
from flask_cors import CORS

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import edge_tts
    EDGE_TTS_OK = True
except Exception:
    EDGE_TTS_OK = False

app = Flask(__name__, template_folder="templates")
CORS(app)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
AUDIO_DIR = os.path.join(BASE, "static", "audio")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Dual-mode storage: Supabase (cloud) when SUPABASE_URL+SUPABASE_SERVICE_KEY set,
# otherwise data/*.json files (unchanged local behaviour).
from storage import (load, save, data_exists, last_updated, CLOUD_MODE)


if not CLOUD_MODE:
    JSON_FILES = ["candidates", "leads", "jobs", "transactions", "agencies",
                  "settings", "conversations"]
    for f in JSON_FILES:
        p = os.path.join(DATA_DIR, f + ".json")
        if not os.path.exists(p):
            with open(p, "w") as fh:
                json.dump([], fh)
    # settings starts as dict
    SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
    try:
        if isinstance(json.load(open(SETTINGS_PATH)), list) and not json.load(open(SETTINGS_PATH)):
            json.dump({}, open(SETTINGS_PATH, "w"))
    except Exception:
        json.dump({}, open(SETTINGS_PATH, "w"))

# ------------------------- helpers -------------------------


def kb():
    return load("knowledge_base") if data_exists("knowledge_base") else {
        "agency_name": "VisaHoBe", "countries": {}, "faqs": {},
        "sample_agencies": []}

def get_setting(key, default=""):
    s = load("settings")
    return s.get(key) or os.environ.get(key.upper(), default)

def is_connected(service):
    s = load("settings")
    return bool(s.get({
        "gemini": "gemini_key", "gmail": "gmail_app_password",
        "fb": "fb_page_token", "whatsapp": "whatsapp_token"}.get(service, "")))

def text_to_voice_realistic(text, voice="bn-BD-NabanitaNeural"):
    """FREE unlimited human-like voice via Microsoft Edge TTS. No API key."""
    if not EDGE_TTS_OK:
        return None
    ts = int(time.time() * 1000)
    fn = f"voice_{ts}.mp3"
    path = os.path.join(AUDIO_DIR, fn)
    try:
        asyncio.run(edge_tts.Communicate(text, voice).save(path))
        return f"/static/audio/{fn}"
    except Exception:
        return None

def gemini_reply(message):
    key = get_setting("gemini_key")
    if not key:
        return None
    try:
        k = kb()
        sys_prompt = (f"You are {k.get('agency_name','VisaHoBe')} visa agency assistant. "
                      f"Answer briefly about work permit visas for Canada, Romania, Poland. "
                      f"Use this data: {json.dumps(k.get('countries',{}))}")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
            json={"contents": [{"role": "user", "parts": [{"text": sys_prompt + "\n\nUser: " + message}]}],
                  "generationConfig": {"maxOutputTokens": 400}},
            timeout=20)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    return None

def knowledge_reply(message):
    k = kb()
    m = message.lower()
    faqs = k.get("faqs", {})
    # greeting
    if any(w in m for w in ["salam", "hello", "hi ", "assalam", "আসসালাম"]):
        return faqs.get("greeting", "Wa Alaikum Salam! VisaHoBe theke bolchi. Kon deshe jete chan?")
    for key, val in faqs.items():
        if key in m or (key == "cost" and any(w in m for w in ["cost", "price", "charge", "taka", "দাম", "কত"])):
            return val
    # country info
    for country, info in k.get("countries", {}).items():
        if country.lower() in m:
            return (f"{country}: Salary {info.get('salary')}, Service charge {info.get('service_charge')}, "
                    f"Processing {info.get('processing')}"
                    + (f", Accommodation {info.get('accommodation')}" if info.get("accommodation") else "")
                    + ". Documents: " + ", ".join(info.get("documents", [])) + " - VisaHoBe")
    return ("I can help with: work permit visas for Canada, Romania, Poland; finding agencies; "
            "adding candidates; job posting; profit tracking. Ask me anything! - VisaHoBe")

def parse_candidate(message):
    """Extract candidate fields from free text."""
    def grab(field, names):
        for n in names:
            # capture lazily until comma/semicolon/newline or the next "Key:" token
            m = re.search(n + r"\s*[:\-]\s*([^\n,;]+?)(?=\s+[A-Za-z]+\s*:|\s*$|[,;\n])", message, re.I)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""
    return {
        "name": grab("name", ["name", "nam", "নাম"]),
        "phone": grab("phone", ["phone", "mobile", "contact"]),
        "passport": grab("passport", ["passport", "pp"]),
        "age": grab("age", ["age"]),
        "country": grab("country", ["country", "deshe", "destination"]),
        "job": grab("job", ["job", "position", "post"]),
        "payment": grab("payment", ["payment", "paid", "advance"]),
        "notes": grab("notes", ["note", "notes"]),
        "status": grab("status", ["status"]) or "New",
    }

def add_candidate(data):
    cands = load("candidates")
    cand = {
        "id": str(int(time.time() * 1000))[-9:],
        **{k: v for k, v in data.items() if v},
        "status": data.get("status") or "New",
        "created": datetime.now().isoformat(),
    }
    cands.append(cand)
    save("candidates", cands)
    return cand

def add_lead(name, phone, interest, source, status="New"):
    leads = load("leads")
    lead = {
        "id": str(int(time.time() * 1000))[-9:],
        "name": name or "Unknown", "phone": phone or "", "interest": interest or "",
        "source": source or "Website", "status": status,
        "next_follow": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
        "last_contact": datetime.now().strftime("%Y-%m-%d"),
    }
    leads.append(lead)
    save("leads", leads)
    return lead

def stats():
    c, l, j, t = load("candidates"), load("leads"), load("jobs"), load("transactions")
    income = sum(x.get("amount", 0) for x in t if x.get("type", "").startswith("Income"))
    expense = sum(x.get("amount", 0) for x in t if x.get("type", "").startswith("Expense"))
    return {"candidates": len(c), "leads": len(l), "jobs": len(j),
            "income": income, "expense": expense, "profit": income - expense,
            "whatsapp_connected": is_connected("whatsapp"),
            "real_time_status": True}

def ai_parse_command(message):
    """The brain: parse Bangla/English natural language into intents."""
    m = message.lower()
    k = kb()

    if any(w in m for w in ["agency", "agencies", "এজেন্সি", "find-agenc", "trusted"]):
        return {"intent": "find_agencies"}
    if any(w in m for w in ["add candidate", "candidate add", "নতুন প্রার্থী", "add_candidate"]) or \
       (re.search(r"name\s*:", m) and re.search(r"phone\s*:", m)):
        return {"intent": "add_candidate", "data": parse_candidate(message)}
    if any(w in m for w in ["job post", "post job", "post_job", "নতুন জব"]):
        return {"intent": "post_job", "data": parse_job(message)}
    if "lead" in m:
        return {"intent": "show_leads"}
    if "candidate" in m or "প্রার্থী" in m:
        return {"intent": "show_candidates"}
    if any(w in m for w in ["profit", "income", "লাভ", "হিসাব"]):
        return {"intent": "show_profit"}
    if any(w in m for w in ["voice", "ভয়েস", "bala", "balbo", "bolbo"]):
        return {"intent": "generate_voice", "text": message}
    if "email" in m or "ইমেইল" in m:
        return {"intent": "send_email"}
    if any(w in m for w in ["create post", "post design", "design post", "fb post", "facebook post"]):
        return {"intent": "create_post"}
    if any(w in m for w in ["reel", "video script", "script"]):
        return {"intent": "generate_video_script", "topic": message}
    return {"intent": "knowledge"}

def parse_job(message):
    def grab(n, alt=None):
        m = re.search(n + r"\s*[:\-]\s*([^\n;]+)", message, re.I)
        if m: return m.group(1).strip()
        if alt:
            m2 = re.search(alt, message, re.I)
            if m2: return m2.group(1).strip()
        return ""
    return {"title": grab("title") or "New Position", "country": grab("country"),
            "salary": grab("salary"), "vacancy": grab("vacancy"),
            "deadline": grab("deadline"), "type": grab("type") or "Full Time",
            "description": grab("description") or message[:300]}

# ------------------------- pages -------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/jobs")
def jobs_page():
    return render_template("jobs.html")

# ------------------------- 1. dashboard -------------------------

@app.route("/api/stats")
def api_stats():
    s = stats()
    c, l, j = load("candidates"), load("leads"), load("jobs")
    s["recent_candidates"] = c[-3:]
    s["recent_leads"] = l[-3:]
    s["recent_jobs"] = j[-3:]
    return jsonify(s)

# ------------------------- 2. chat parser -------------------------

@app.route("/api/minimal/chat", methods=["POST"])
def minimal_chat():
    body = request.get_json(force=True)
    message = body.get("message", "")
    result = ai_parse_command(message)
    intent = result["intent"]
    reply, data, action, agencies = "", None, intent, []

    if intent == "find_agencies":
        agencies = kb().get("sample_agencies", [])
        ags = load("agencies")
        ags.extend([{"name": a["name"], "country": a["country"],
                     "email": a["email"], "saved": datetime.now().isoformat()} for a in agencies])
        save("agencies", ags[-200:])
        reply = f"Found {len(agencies)} trusted agencies for Canada, Romania, Poland. All verified by VisaHoBe."
        data = agencies
    elif intent == "add_candidate":
        cand = add_candidate(result["data"])
        add_lead(cand.get("name"), cand.get("phone"), cand.get("country"), "Chat")
        reply = f"Candidate added: {cand.get('name','Unknown')} ({cand.get('country','N/A')}). CRM updated real time."
        data = cand
    elif intent == "post_job":
        jobs = load("jobs")
        job = {"id": str(int(time.time() * 1000))[-9:], **result["data"],
               "applications": 0, "created": datetime.now().isoformat()}
        jobs.append(job)
        save("jobs", jobs)
        reply = f"Job posted: {job['title']} ({job['country']}). Live on public /jobs page now."
        data = job
    elif intent == "show_leads":
        data = load("leads")
        reply = f"You have {len(data)} leads."
    elif intent == "show_candidates":
        data = load("candidates")
        reply = f"You have {len(data)} candidates."
    elif intent == "show_profit":
        s = stats()
        data = s
        reply = f"Income: {s['income']} BDT | Expense: {s['expense']} BDT | Profit: {s['profit']} BDT"
    elif intent == "generate_voice":
        reply = "Voice note generated below - realistic human-like voice."
        data = {"text": result["text"]}
    elif intent == "send_email":
        reply = ("Email template ready (First Contact / Follow Up / Candidate List). "
                 "Add Gmail App Password in API Keys to send real emails - 500/day free.")
        data = {"templates": ["first_contact", "follow_up", "candidate_list"]}
    elif intent == "create_post":
        reply = "Post design created - placeholder generated."
        data = {"image": "https://via.placeholder.com/800x800/0ea5e9/ffffff?text=VisaHoBe+Post"}
    elif intent == "generate_video_script":
        topic = result.get("topic", message)
        reply = "Reel script generated: HOOK + DETAILS + CTA."
        data = {"script": {
            "hook": f"POV: You want to work in {topic} but don't know where to start?",
            "details": "VisaHoBe handles everything - work permit, documents, air ticket.",
            "cta": "DM 'VISA' now. Your Dream Abroad Starts Here."}}
    else:
        reply = gemini_reply(message) or knowledge_reply(message)

    voice_url = text_to_voice_realistic(reply)
    return jsonify({"reply": reply, "intent": intent, "voice_url": voice_url,
                    "action": action, "agencies": agencies, "data": data,
                    "real_time": True})

# ------------------------- 3. candidate CRM -------------------------

@app.route("/api/candidates", methods=["GET", "POST"])
def candidates_api():
    if request.method == "GET":
        return jsonify(load("candidates"))
    body = request.get_json(force=True)
    cand = add_candidate(body)
    return jsonify(cand)

@app.route("/api/candidates/<cid>", methods=["DELETE"])
def delete_candidate(cid):
    cands = [c for c in load("candidates") if c.get("id") != cid]
    save("candidates", cands)
    return jsonify({"deleted": cid, "remaining": len(cands)})

@app.route("/api/candidates/export")
def export_candidates():
    cands = load("candidates")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "name", "phone", "passport", "age", "country", "job", "status", "payment", "created"])
    for c in cands:
        w.writerow([c.get(k, "") for k in ["id", "name", "phone", "passport", "age", "country", "job", "status", "payment", "created"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=visahobe_candidates.csv"})

# ------------------------- 4. leads -------------------------

@app.route("/api/leads", methods=["GET", "POST"])
def leads_api():
    if request.method == "GET":
        leads = load("leads")
        today = datetime.now().strftime("%Y-%m-%d")
        due = [l for l in leads if l.get("next_follow", "") <= today]
        return jsonify({"leads": leads, "follow_up_due": due, "total": len(leads)})
    b = request.get_json(force=True)
    return jsonify(add_lead(b.get("name"), b.get("phone"), b.get("interest"),
                            b.get("source", "Website"), b.get("status", "New")))

# ------------------------- 5. jobs -------------------------

@app.route("/api/jobs", methods=["GET", "POST"])
def jobs_api():
    if request.method == "GET":
        return jsonify(load("jobs"))
    b = request.get_json(force=True)
    jobs = load("jobs")
    job = {"id": str(int(time.time() * 1000))[-9:], "title": b.get("title", "New Position"),
           "country": b.get("country", ""), "salary": b.get("salary", ""),
           "vacancy": b.get("vacancy", ""), "deadline": b.get("deadline", ""),
           "type": b.get("type", "Full Time"), "description": b.get("description", ""),
           "applications": 0, "created": datetime.now().isoformat()}
    jobs.append(job)
    save("jobs", jobs)
    return jsonify(job)

@app.route("/api/jobs/<jid>", methods=["DELETE"])
def delete_job(jid):
    jobs = [j for j in load("jobs") if j.get("id") != jid]
    save("jobs", jobs)
    return jsonify({"deleted": jid, "remaining": len(jobs)})

@app.route("/api/jobs/public")
def public_jobs():
    return jsonify(load("jobs"))

@app.route("/api/apply", methods=["POST"])
def apply_job():
    b = request.get_json(force=True)
    cand = add_candidate({"name": b.get("name"), "phone": b.get("phone"),
                          "passport": b.get("passport"), "status": "New"})
    add_lead(b.get("name"), b.get("phone"), "Job Application", "Website")
    jobs = load("jobs")
    for j in jobs:
        if j.get("id") == b.get("job_id"):
            j["applications"] = j.get("applications", 0) + 1
    save("jobs", jobs)
    return jsonify({"status": "applied", "candidate": cand, "real_time": True})

# ------------------------- 6. agency finder + scam checker -------------------------

@app.route("/api/find-agencies", methods=["POST"])
def find_agencies():
    b = request.get_json(force=True)
    all_ag = kb().get("sample_agencies", [])
    country = (b.get("country") or "").lower()
    kw = (b.get("keyword") or "").lower()
    matches = [a for a in all_ag if (not country or country in a["country"].lower())
               and (not kw or kw in a["name"].lower())]
    ags = load("agencies")
    for a in matches:
        ags.append({"name": a["name"], "country": a["country"], "email": a["email"],
                    "saved": datetime.now().isoformat()})
    save("agencies", ags[-200:])
    return jsonify({"agencies": matches, "saved_to": "agencies.json", "real_time": True})

@app.route("/api/check-agency", methods=["POST"])
def check_agency():
    b = request.get_json(force=True)
    email = (b.get("email") or "").lower()
    website = (b.get("website") or "").lower()
    details, score = [], 60
    known_good = {"globalworker", "workvantage", "canadastaffing"}
    for k in known_good:
        if k in email or k in website:
            score = 95
            details.append("Known verified agency in VisaHoBe database")
    free_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]
    if any(d in email for d in free_domains) and not website:
        score = min(score, 35)
        details.append("Free email only, no company website - risky")
    elif any(d in email for d in free_domains):
        score = min(score, 55)
        details.append("Free email address - medium risk")
    if website:
        score += 20
        details.append("Has own company domain")
    if not email and not website:
        score, details = 30, ["No contact info provided"]
    risk = "Low" if score >= 80 else "Medium" if score >= 50 else "High"
    details.append("Always verify: visit office, check trade license, never pay to personal bank account - VisaHoBe")
    return jsonify({"email": email, "website": website, "score": score,
                    "risk": risk, "details": details})

# ------------------------- 7. email center -------------------------

EMAIL_TEMPLATES = {
    "first_contact": ("VisaHoBe - Work Permit Partnership",
                      "Dear Sir/Madam,\n\nWe are VisaHoBe, a trusted visa consultancy from Bangladesh. "
                      "We have 500+ job-ready candidates for Canada, Romania and Poland with passports, "
                      "NID and police clearance ready.\n\nCan we send you our candidate list?\n\n"
                      "Best regards,\nVisaHoBe Team\nYour Dream Abroad Starts Here"),
    "follow_up": ("VisaHoBe - Following Up",
                  "Dear Sir/Madam,\n\nFollowing up on our previous email about our job-ready candidates. "
                  "We would love to discuss how we can support your recruitment needs.\n\n"
                  "Best regards,\nVisaHoBe Team"),
    "candidate_list": ("VisaHoBe - Candidate List",
                       "Dear Sir/Madam,\n\nPlease find our current candidate list attached. "
                       "All documents verified. Reply for full profiles.\n\nVisaHoBe Team"),
}

@app.route("/api/generate-email", methods=["POST"])
def generate_email():
    b = request.get_json(force=True)
    t = b.get("template", "first_contact")
    subject, body = EMAIL_TEMPLATES.get(t, EMAIL_TEMPLATES["first_contact"])
    to = b.get("to", "")
    gmail_email = get_setting("gmail_email")
    gmail_pass = get_setting("gmail_app_password")
    sent = False
    if to and gmail_email and gmail_pass:
        try:
            msg = MIMEMultipart()
            msg["From"], msg["To"], msg["Subject"] = gmail_email, to, subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(gmail_email, gmail_pass)
                s.send_message(msg)
            sent = True
        except Exception:
            sent = False
    return jsonify({"template": t, "subject": subject, "body": body,
                    "to": to, "sent": sent,
                    "mode": "real" if sent else "demo",
                    "note": "Add Gmail App Password in API Keys for real sending (500/day free)"})

# ------------------------- 9. post designer -------------------------

@app.route("/api/create-post", methods=["POST"])
def create_post():
    b = request.get_json(force=True)
    ptype = (b.get("type") or "general").replace(" ", "+")
    title = (b.get("title") or "VisaHoBe").replace(" ", "+")
    return jsonify({"image": f"https://via.placeholder.com/800x800/0ea5e9/ffffff?text={title}",
                    "type": ptype, "title": b.get("title", ""),
                    "note": "Connect AI image generation for branded VisaHoBe posts"})

# ------------------------- 10. reels factory -------------------------

@app.route("/api/generate-video-script", methods=["POST"])
def video_script():
    b = request.get_json(force=True)
    topic = b.get("topic", "work abroad")
    return jsonify({"script": {
        "hook": f"POV: You want to work in {topic} but think it's impossible?",
        "details": f"VisaHoBe made it simple - {topic} work permit, free documents guidance, "
                   "transparent service charge, no hidden cost.",
        "cta": "DM 'VISA' now. Follow VisaHoBe. Your Dream Abroad Starts Here."},
        "duration": "30 sec", "format": "9:16 Reel"})

# ------------------------- 11. documents -------------------------

@app.route("/api/generate-doc", methods=["POST"])
def generate_doc():
    b = request.get_json(force=True)
    t = b.get("type", "cv")
    name = b.get("name", "Candidate")
    if t == "cv":
        content = {"sections": ["Personal Info", "Objective", "Experience",
                                "Education", "Languages", "Skills"],
                   "note": "European ATS format", "name": name}
        reply = f"CV generated for {name} - European format, ATS friendly."
    elif t == "agreement":
        content = {"clause_1": "Service charge all inclusive", "clause_2": "Refund policy",
                   "clause_3": "Document handling", "name": name}
        reply = f"Agreement generated for {name}."
    else:
        content = {"paragraphs": 3, "type": "cover letter", "name": name}
        reply = f"Cover letter generated for {name}."
    return jsonify({"type": t, "content": content, "reply": reply, "note": "Placeholder - connect AI for full text"})

# ------------------------- 12. profit tracker -------------------------

@app.route("/api/transactions", methods=["GET", "POST"])
def transactions_api():
    if request.method == "GET":
        return jsonify(load("transactions"))
    b = request.get_json(force=True)
    trxs = load("transactions")
    trx = {"id": str(int(time.time() * 1000))[-9:],
           "type": b.get("type", "Income-Client"), "amount": float(b.get("amount", 0)),
           "desc": b.get("desc", ""), "candidate": b.get("candidate", ""),
           "date": b.get("date", datetime.now().strftime("%Y-%m-%d"))}
    trxs.append(trx)
    save("transactions", trxs)
    return jsonify(trx)

# ------------------------- 13. voice agent -------------------------

VOICES = ["bn-BD-NabanitaNeural", "bn-BD-PradeepNeural", "en-US-JennyNeural", "en-US-GuyNeural"]

@app.route("/api/voice/generate", methods=["POST"])
def voice_generate():
    b = request.get_json(force=True)
    text = b.get("text", "")
    voice = b.get("voice", "bn-BD-NabanitaNeural")
    if voice not in VOICES:
        voice = "bn-BD-NabanitaNeural"
    url = text_to_voice_realistic(text, voice)
    return jsonify({"text": text, "voice": voice, "voice_url": url,
                    "human_like": True, "free": True, "real_time": True})

@app.route("/api/voice/chat", methods=["POST"])
def voice_chat():
    b = request.get_json(force=True)
    message = b.get("message", "")
    reply = gemini_reply(message) or knowledge_reply(message)
    voice_url = text_to_voice_realistic(reply)
    convs = load("conversations")
    convs.append({"user": message, "bot": reply, "voice_url": voice_url,
                  "ts": datetime.now().isoformat()})
    save("conversations", convs[-500:])
    return jsonify({"reply": reply, "voice_url": voice_url, "real_time": True})

# ------------------------- 14. AI chat -------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    b = request.get_json(force=True)
    message = b.get("message", "")
    reply = gemini_reply(message)
    mode = "gemini" if reply else "rule-based"
    if not reply:
        reply = knowledge_reply(message)
    return jsonify({"reply": reply, "mode": mode,
                    "gemini_connected": is_connected("gemini")})

# ------------------------- 15. WhatsApp webhook -------------------------

@app.route("/api/whatsapp-webhook", methods=["GET"])
def wa_verify():
    if request.args.get("hub.verify_token") == get_setting("whatsapp_verify_token", "visahobe123"):
        return request.args.get("hub.challenge", ""), 200
    return "Verification failed", 403

@app.route("/api/whatsapp-webhook", methods=["POST"])
def wa_receive():
    body = request.get_json(force=True, silent=True) or {}
    message, phone = "", ""
    if "entry" in body:  # Meta Cloud API format
        try:
            msgs = body["entry"][0]["changes"][0]["value"]["messages"][0]
            message = msgs.get("text", {}).get("body", "")
            phone = msgs.get("from", "")
        except Exception:
            pass
    else:
        message = body.get("message", "")
        phone = body.get("phone", "")

    if not message:
        return jsonify({"status": "received", "reply": "", "real_time": True,
                        "whatsapp_control": True}), 200

    result = ai_parse_command(message)
    intent = result["intent"]
    if intent == "add_candidate":
        cand = add_candidate(result["data"])
        reply = f"Candidate added: {cand.get('name', 'Unknown')}. VisaHoBe CRM updated."
    elif intent == "find_agencies":
        agencies = kb().get("sample_agencies", [])
        reply = "Verified agencies: " + "; ".join(f"{a['name']} ({a['email']})" for a in agencies)
    else:
        reply = gemini_reply(message) or knowledge_reply(message)

    voice_url = text_to_voice_realistic(reply)
    wa_token = get_setting("whatsapp_token")
    wa_phone_id = get_setting("whatsapp_phone_id")
    if wa_token and wa_phone_id and phone:
        try:
            requests.post(
                f"https://graph.facebook.com/v19.0/{wa_phone_id}/messages",
                headers={"Authorization": f"Bearer {wa_token}"},
                json={"messaging_product": "whatsapp", "to": phone, "type": "text",
                      "text": {"body": reply}}, timeout=15)
        except Exception:
            pass
    convs = load("conversations")
    convs.append({"phone": phone, "user": message, "bot": reply, "channel": "whatsapp",
                  "ts": datetime.now().isoformat()})
    save("conversations", convs[-500:])
    return jsonify({"status": "received", "intent": intent, "reply": reply,
                    "voice_url": voice_url, "real_time": True, "whatsapp_control": True})

# ------------------------- 16. settings -------------------------

def mask(v):
    return (v[:4] + "****" + v[-4:]) if v and len(v) > 8 else ("****" if v else "")

@app.route("/api/settings")
def get_settings():
    return jsonify({
        "gemini_key": mask(get_setting("gemini_key")),
        "gmail_email": get_setting("gmail_email", ""),
        "gmail_app_password": mask(get_setting("gmail_app_password")),
        "fb_page_id": get_setting("fb_page_id", ""),
        "fb_page_token": mask(get_setting("fb_page_token")),
        "whatsapp_phone_id": get_setting("whatsapp_phone_id", ""),
        "whatsapp_token": mask(get_setting("whatsapp_token")),
        "whatsapp_verify_token": get_setting("whatsapp_verify_token", "visahobe123"),
        "gemini_connected": is_connected("gemini"),
        "gmail_connected": is_connected("gmail"),
        "fb_connected": is_connected("fb"),
        "whatsapp_connected": is_connected("whatsapp"),
        "webhook_url": "/api/whatsapp-webhook",
        "real_time_status": True})

@app.route("/api/settings/save", methods=["POST"])
def save_settings():
    b = request.get_json(force=True)
    s = load("settings")
    for k in ["gemini_key", "gmail_email", "gmail_app_password", "fb_page_token",
              "fb_page_id", "whatsapp_token", "whatsapp_phone_id", "whatsapp_verify_token"]:
        if k in b and b[k] and str(b[k]).strip() and "****" not in str(b[k]):
            s[k] = str(b[k]).strip()
    save("settings", s)
    # upsert .env (no restart needed - settings.json is source of truth at runtime)
    try:
        env_path = os.path.join(BASE, ".env")
        lines = []
        if os.path.exists(env_path):
            lines = open(env_path).read().strip().split("\n")
        for k in s:
            key = k.upper()
            done = False
            lines = [(f"{key}={s[k]}" if l.startswith(key + "=") else l) for l in lines]
            if key not in [l.split("=")[0] for l in lines]:
                lines.append(f"{key}={s[k]}")
        open(env_path, "w").write("\n".join(lines) + "\n")
    except Exception:
        pass
    return jsonify({"saved": True, "keys": list(s.keys()), "no_restart_needed": True,
                    "real_time_status": True})

@app.route("/api/settings/test/<service>", methods=["POST"])
def test_service(service):
    ok, msg = False, "Not configured"
    try:
        if service == "gemini":
            r = gemini_reply("Hello")
            if r: ok, msg = True, "Gemini connected and replying"
        elif service == "gmail":
            ge, gp = get_setting("gmail_email"), get_setting("gmail_app_password")
            if ge and gp:
                with smtplib.SMTP("smtp.gmail.com", 587) as s:
                    s.starttls(); s.login(ge, gp)
                ok, msg = True, "Gmail SMTP login OK"
        elif service == "whatsapp":
            t, p = get_setting("whatsapp_token"), get_setting("whatsapp_phone_id")
            if t and p:
                r = requests.get(f"https://graph.facebook.com/v19.0/{p}",
                                 headers={"Authorization": f"Bearer {t}"}, timeout=15)
                ok = r.status_code == 200
                msg = "WhatsApp Cloud API connected" if ok else f"Failed: {r.status_code}"
        elif service == "fb":
            t, p = get_setting("fb_page_token"), get_setting("fb_page_id")
            if t and p:
                r = requests.get(f"https://graph.facebook.com/v19.0/{p}?fields=name",
                                 headers={"Authorization": f"Bearer {t}"}, timeout=15)
                ok = r.status_code == 200
                msg = f"Facebook page: {r.json().get('name','?')}" if ok else f"Failed: {r.status_code}"
    except Exception as e:
        msg = f"Error: {str(e)[:100]}"
    return jsonify({"service": service, "connected": ok, "message": msg})

# ------------------------- 17. backup -------------------------

@app.route("/api/backup")
def backup():
    return jsonify({f: load(f) for f in ["candidates", "leads", "jobs", "transactions",
                                          "agencies", "settings", "conversations", "knowledge_base"]})

@app.route("/static/audio/<path:p>")
def audio(p):
    return send_from_directory(AUDIO_DIR, p)

@app.route("/api/last_updated")
def api_last_updated():
    """Live sync: timestamp of the newest data change."""
    return jsonify({"ts": last_updated(), "cloud": CLOUD_MODE})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
