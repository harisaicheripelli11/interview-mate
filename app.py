from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pymysql
from pymysql.err import IntegrityError
import bcrypt
from groq import Groq
import os
import re
import json
import uuid


# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "interview-mate-secret")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------- DATABASE ----------------
db = pymysql.connect(
    host="localhost",
    user="root",
    password="root123",
    database="interview_mate",
    cursorclass=pymysql.cursors.DictCursor
)

# ---------------- HELPERS ----------------
def extract_json(text):
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end != -1:
            return json.loads(text[start:end])
    except:
        pass
    return None


def safe_score(value):
    try:
        score = int(re.findall(r"\d+", str(value))[0])
        return min(max(score, 1), 10)
    except:
        return 5


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("index.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_pw = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt()
        ).decode("utf-8")

        try:
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (name, email, password) VALUES (%s,%s,%s)",
                    (name, email, hashed_pw)
                )
            db.commit()
            return redirect(url_for("login"))

        except IntegrityError:
            return render_template("signup.html", error="Email already exists")

    return render_template("signup.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        with db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()

        # ✅ VALID LOGIN
        if user and bcrypt.checkpw(password.encode(), user["password"].encode()):
            session["user"] = user["email"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]   # 🔐 role stored

            # 🔀 ROLE-BASED REDIRECT
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("dashboard"))

        # ❌ INVALID LOGIN
        return render_template("login.html", error="Invalid email or password")

    # GET REQUEST
    return render_template("login.html")



# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")

#--------------------Admin-------------------

@app.route("/admin")
def admin_dashboard():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    with db.cursor() as cur:
        # Total users
        cur.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cur.fetchone()["total"]

        # User + interview data
        cur.execute("""
            SELECT 
                u.name,
                u.email,
                COUNT(DISTINCT i.interview_id) AS interviews_taken,
                GROUP_CONCAT(DISTINCT i.interview_value SEPARATOR ', ') AS interview_types
            FROM users u
            LEFT JOIN interview_scores i 
                ON u.email = i.user_email
            GROUP BY u.id
            ORDER BY interviews_taken DESC
        """)
        users = cur.fetchall()

    return render_template(
        "admin.html",
        total_users=total_users,
        users=users
    )

# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("login"))

    with db.cursor() as cur:

        # ---------- USER INFO ----------
        cur.execute("""
            SELECT name, email, created_at
            FROM users
            WHERE email=%s
        """, (session["user"],))
        user = cur.fetchone()

        # ---------- RECENT INTERVIEWS (FIXED) ----------
        cur.execute("""
            SELECT
                interview_id,
                interview_type,
                interview_value,
                MIN(created_at) AS created_at
            FROM interview_scores
            WHERE user_email=%s
            GROUP BY interview_id, interview_type, interview_value
            ORDER BY created_at DESC
            LIMIT 5
        """, (session["user"],))
        history = cur.fetchall()

        # ---------- STATS ----------
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                AVG(confidence) AS avg_conf,
                AVG(clarity) AS avg_clarity
            FROM interview_scores
            WHERE user_email=%s
        """, (session["user"],))
        raw = cur.fetchone() or {}

    # 🔒 SAFE DEFAULTS (IMPORTANT)
    stats = {
        "total": int(raw.get("total") or 0),
        "avg_conf": float(raw.get("avg_conf") or 0),
        "avg_clarity": float(raw.get("avg_clarity") or 0)
    }

    return render_template(
        "profile.html",
        user=user,
        history=history,
        stats=stats
    )





# ---------------- PERFORMANCE DATA (AJAX) ----------------
@app.route("/performance-data")
def performance_data():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    with db.cursor() as cur:

        # ---------------- TOTAL INTERVIEWS (FIXED) ----------------
        cur.execute("""
            SELECT 
                COUNT(DISTINCT interview_id) AS total_interviews,
                ROUND(AVG(confidence), 2) AS avg_confidence,
                ROUND(AVG(clarity), 2) AS avg_clarity
            FROM interview_scores
            WHERE user_email = %s
        """, (session["user"],))

        stats = cur.fetchone() or {}

        total = int(stats.get("total_interviews") or 0)
        avg_conf = float(stats.get("avg_confidence") or 0)
        avg_cla = float(stats.get("avg_clarity") or 0)

        overall_score = (
            round(((avg_conf + avg_cla) / 20) * 100, 1)
            if total > 0 else 0
        )

        # ---------------- INTERVIEW-WISE TREND (BEST PRACTICE) ----------------
        cur.execute("""
            SELECT
                interview_id,
                ROUND(AVG(confidence), 2) AS confidence,
                ROUND(AVG(clarity), 2) AS clarity
            FROM interview_scores
            WHERE user_email = %s
            GROUP BY interview_id
            ORDER BY MIN(created_at)
        """, (session["user"],))

        rows = cur.fetchall()

        confidence_trend = [row["confidence"] for row in rows]
        clarity_trend = [row["clarity"] for row in rows]
        labels = list(range(1, len(rows) + 1))

    # ---------------- FEEDBACK ----------------
    strengths, improvements, action_plan = generate_feedback(
        avg_conf, avg_cla, total
    )

    return jsonify({
        "stats": {
            "total_interviews": total,
            "avg_confidence": avg_conf,
            "avg_clarity": avg_cla,
            "overall_score": overall_score
        },
        "trend": {
            "labels": labels,
            "confidence": confidence_trend,
            "clarity": clarity_trend
        },
        "feedback": {
            "strengths": strengths,
            "improvements": improvements,
            "action_plan": action_plan
        }
    })



#---------------- FEEDBACK GENERATOR ----------------
def generate_feedback(avg_conf, avg_clarity, total):
    strengths = []
    improvements = []
    action_plan = []

    # ---------- STRENGTHS ----------
    if avg_conf >= 7:
        strengths.append("Confident while answering interview questions")
    if avg_clarity >= 7:
        strengths.append("Clear and structured explanations")
    if total >= 5:
        strengths.append("Consistent interview practice")

    if len(strengths) < 3:
        strengths.extend([
            "Good understanding of core concepts",
            "Positive improvement over time",
            "Comfortable with interview environment"
        ])

    strengths = strengths[:3]

    # ---------- IMPROVEMENTS ----------
    if avg_conf < 6:
        improvements.append("Needs more confidence while answering")
    if avg_clarity < 6:
        improvements.append("Improve clarity and answer structure")
    if total < 3:
        improvements.append("Attempt more mock interviews")

    if len(improvements) < 3:
        improvements.extend([
            "Add more real-world examples",
            "Be more concise in explanations",
            "Improve technical depth gradually"
        ])

    improvements = improvements[:3]

    # ---------- ACTION PLAN ----------
    action_plan.append("Practice STAR method answers daily")
    action_plan.append("Explain answers using real project examples")

    if avg_conf < 6:
        action_plan.append("Speak answers aloud to build confidence")
    if avg_clarity < 6:
        action_plan.append("Structure answers: definition → example → impact")

    action_plan.append("Attempt at least 2 mock interviews every week")

    return strengths, improvements, action_plan


# ---------------- MOCK INTERVIEW ----------------
@app.route("/mock-interview")
def mock_interview():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("mock_interview.html")


# ---------------- INTERVIEW START ----------------
@app.route("/interview")
def interview():
    if "user" not in session:
        return redirect(url_for("login"))

    interview_type = request.args.get("type")
    interview_value = request.args.get("value")
    interview_mode = request.args.get("mode", "chat")

    if not interview_type or not interview_value:
        return redirect(url_for("mock_interview"))
    
    session["interview_id"] = str(uuid.uuid4())
    session.update({
        "interview_type": interview_type,
        "interview_value": interview_value,
        "interview_mode": interview_mode,
        "current_round": 1,
        "question_count": 0,
        "max_rounds": 3,
        "questions_per_round": 3,
        "total_questions": 9,
        "answered_questions": 0,
        "asked_questions": []
    })
    
    return render_template(
        "interview.html",
        interview_type=interview_type,
        interview_value=interview_value,
        interview_mode=interview_mode
    )


# ---------------- CHAT HANDLER ----------------
@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # ================= FIRST QUESTION (AUTO START) =================
    if user_message.upper() == "START":
        first_question = (
            "👋 Hi! I’ll be your interviewer today. "
            "Let’s start with a quick introduction — Tell me about yourself."
        )

        session["asked_questions"] = [first_question]
        session.setdefault("answered_questions", 0)
        session.setdefault("question_count", 0)
        session.setdefault("current_round", 1)

        return jsonify({
            "confidence": None,
            "clarity": None,
            "answer_review": None,
            "next_question": first_question
        })

    # ---------------- ROUND & DIFFICULTY ----------------
    round_num = session.get("current_round", 1)

    if round_num == 1:
        difficulty = "basic concepts and definitions"
    elif round_num == 2:
        difficulty = "practical usage and examples"
    else:
        difficulty = "advanced scenarios and edge cases"

    # ---------------- PREVIOUS QUESTION ----------------
    asked_questions = session.get("asked_questions", [])
    last_question = asked_questions[-1] if asked_questions else "Tell me about yourself."

    # ---------------- DETECT 'I DON’T KNOW' ----------------
    dont_know_phrases = [
        "i don't know", "i dont know", "no idea",
        "not sure", "dont know", "i have no idea"
    ]
    is_dont_know = any(p in user_message.lower() for p in dont_know_phrases)

    # ---------------- SYSTEM PROMPT ----------------
    system_prompt = f"""
You are a professional interview panelist.

Interview Type: {session["interview_type"]}
Interview Focus: {session["interview_value"]}
Difficulty Level: {difficulty}

Rules:
- Evaluate the user's answer based on relevance to the previous question
- Consider correct terminology and keywords
- Be supportive if the candidate does not know the answer
- Always ask EXACTLY ONE next interview question

Respond ONLY in valid JSON:
{{
  "confidence": 1,
  "clarity": 1,
  "answer_review": "Feedback only. No questions.",
  "next_question": "Ask exactly ONE interview question."
}}

confidence and clarity must be between 1 and 10.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": f"Previous interview question: {last_question}"},
        {"role": "user", "content": user_message}
    ]

    # ---------------- AI CALL ----------------
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0
        )
        ai_data = extract_json(response.choices[0].message.content)
    except Exception as e:
        print("AI ERROR:", e)
        ai_data = None

    # ---------------- FALLBACK ----------------
    if not isinstance(ai_data, dict):
        ai_data = {
            "confidence": 5,
            "clarity": 5,
            "answer_review": "Let’s continue with another question.",
            "next_question": "Can you explain a basic concept related to your role?"
        }

    # ---------------- SCORE CLEANER ----------------
    def safe_score(val):
        try:
            return max(1, min(int(val), 10))
        except:
            return 5

    confidence = safe_score(ai_data.get("confidence"))
    clarity = safe_score(ai_data.get("clarity"))
    review = (ai_data.get("answer_review") or "").strip()
    question = (ai_data.get("next_question") or "").strip()

    # ---------------- KEYWORD BOOST ----------------
    keyword_map = {
        "variable": ["change", "reassign", "mutable"],
        "constant": ["fixed", "cannot change", "immutable"],
        "oops": ["encapsulation", "inheritance", "polymorphism", "abstraction"],
        "database": ["table", "sql", "query", "schema"],
        "api": ["request", "response", "endpoint"],
        "python": ["list", "dictionary", "function", "loop"]
    }

    keyword_hits = 0
    user_text = user_message.lower()

    for key, words in keyword_map.items():
        if key in last_question.lower():
            if any(w in user_text for w in words):
                keyword_hits += 1

    confidence = min(confidence + keyword_hits, 10)
    clarity = min(clarity + keyword_hits, 10)

    # ---------------- HANDLE 'I DON’T KNOW' ----------------
    if is_dont_know:
        confidence = 1
        clarity = 1
        review = (
            "It’s okay to not know the answer. "
            "Try explaining what you understand so far or related concepts."
        )
        question = "Can you explain a basic concept related to your role?"

    # ---------------- FORCE VALID QUESTION ----------------
    if not question or len(question) < 5 or question in asked_questions:
        question = "Explain another important concept related to your role."

    asked_questions.append(question)
    session["asked_questions"] = asked_questions

    # ---------------- SAVE SCORE (REAL ANSWERS ONLY) ----------------
    if len(user_message.split()) >= 3:
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO interview_scores
                (
                    interview_id,
                    user_email,
                    interview_type,
                    interview_value,
                    round_number,
                    confidence,
                    clarity,
                    comment
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session["interview_id"],
                session["user"],
                session["interview_type"],
                session["interview_value"],
                session["current_round"],
                confidence,
                clarity,
                review
            ))
        db.commit()

        session["answered_questions"] += 1
        session["question_count"] += 1

    # ---------------- ROUND ADVANCE ----------------
    if session["question_count"] >= session["questions_per_round"]:
        session["current_round"] += 1
        session["question_count"] = 0

    # ---------------- COMPLETE ----------------
    if session["answered_questions"] >= session["total_questions"]:
        return jsonify({"completed": True, "redirect": "/final-report"})

    return jsonify({
        "confidence": confidence,
        "clarity": clarity,
        "answer_review": review,
        "next_question": question
    })

# ---------------- FINAL REPORT ----------------
@app.route("/final-report")
def final_report():
    if "user" not in session:
        return redirect(url_for("login"))

    with db.cursor() as cur:
        # ✅ Get latest interview meta safely
        cur.execute("""
            SELECT interview_id, interview_type, interview_value
            FROM interview_scores
            WHERE user_email=%s
            ORDER BY created_at DESC
            LIMIT 1
        """, (session["user"],))
        meta = cur.fetchone()

        if not meta:
            return redirect(url_for("dashboard"))

        interview_id = meta["interview_id"]

        # ✅ Fetch answers for THAT interview only
        cur.execute("""
            SELECT confidence, clarity, comment
            FROM interview_scores
            WHERE interview_id=%s
        """, (interview_id,))
        rows = cur.fetchall()

    if not rows:
        return redirect(url_for("dashboard"))

    # ✅ Averages
    avg_conf = round(sum(r["confidence"] for r in rows) / len(rows), 2)
    avg_clar = round(sum(r["clarity"] for r in rows) / len(rows), 2)
    overall_score = round((avg_conf + avg_clar) / 2, 1)

    # ✅ Analysis
    analysis = analyze_performance(rows)

    return render_template(
        "final_report.html",
        avg_confidence=avg_conf,
        avg_clarity=avg_clar,
        overall_score=overall_score,
        strengths=analysis["strengths"],
        improvements=analysis["improvements"],
        future=analysis["future"]
    )

#----------------- ANALYZE PERFORMANCE ----------------
def analyze_performance(rows):
    strengths = set()
    improvements = set()
    future = set()

    for r in rows:
        conf = r["confidence"]
        clar = r["clarity"]
        comment = (r["comment"] or "").lower()

        # -------- STRENGTHS --------
        if conf >= 7:
            strengths.add("Good confidence while answering questions")

        if clar >= 7:
            strengths.add("Clear and structured explanations")

        if "project" in comment:
            strengths.add("Strong project understanding")

        if "api" in comment:
            strengths.add("Good understanding of APIs")

        # -------- IMPROVEMENTS --------
        if conf <= 4:
            improvements.add("Low confidence while answering")
            future.add("Practice mock interviews to improve confidence")

        if clar <= 4:
            improvements.add("Lack of clarity in explanations")
            future.add("Use structured answering methods like STAR")

        if "brief" in comment or "short" in comment:
            improvements.add("Answers are too brief")
            future.add("Add examples and detailed explanations")

        if "technical" in comment:
            improvements.add("Needs deeper technical understanding")
            future.add("Revise core technical concepts")

    # fallback if empty
    if not strengths:
        strengths.add("Participated actively in the interview")

    return {
        "strengths": list(strengths),
        "improvements": list(improvements),
        "future": list(future)
    }
    
#---------------- PERFORMANCE PAGE ----------------   

@app.route("/performance")
def performance():
    if "user" not in session:
        return redirect(url_for("login"))

    with db.cursor() as cur:

        # ✅ TOTAL INTERVIEWS (NO DUPLICATES)
        cur.execute("""
            SELECT COUNT(DISTINCT interview_id) AS total_interviews
            FROM interview_scores
            WHERE user_email=%s
        """, (session["user"],))
        total = cur.fetchone()["total_interviews"] or 0

        # ✅ AVERAGES
        cur.execute("""
            SELECT 
                ROUND(AVG(confidence),2) AS avg_confidence,
                ROUND(AVG(clarity),2) AS avg_clarity
            FROM interview_scores
            WHERE user_email=%s
        """, (session["user"],))
        stats = cur.fetchone() or {}

    avg_conf = float(stats.get("avg_confidence") or 0)
    avg_cla = float(stats.get("avg_clarity") or 0)

    overall_score = round(((avg_conf + avg_cla) / 20) * 100, 1) if total else 0

    strengths = []
    improvements = []

    if avg_conf >= 7:
        strengths.append("Good confidence in answers")
    else:
        improvements.append("Needs more confident explanations")

    if avg_cla >= 7:
        strengths.append("Clear and structured responses")
    else:
        improvements.append("Work on clarity and structure")

    suggestion = "Practice mock interviews regularly and focus on explaining concepts clearly."

    return render_template(
        "performance.html",
        total_interviews=total,
        avg_confidence=avg_conf,
        avg_clarity=avg_cla,
        overall_score=overall_score,
        strengths=strengths,
        improvements=improvements,
        suggestion=suggestion
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    print("🔥 Interview Mate running on port 3000")
    app.run()

