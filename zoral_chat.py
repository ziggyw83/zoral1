import os
import sqlite3
from datetime import datetime
import ollama
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_bcrypt import Bcrypt
import re

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
bcrypt = Bcrypt(app)

# Database setup
DB_FILE = "zoral_npc.sqlite"

# Connect to the SQLite database
try:
    db = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = db.cursor()
except sqlite3.Error as e:
    print(f"Database connection failed: {e}")
    exit(1)

# === Database Functions ===
def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS zoral_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            input TEXT,
            response TEXT,
            timestamp TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS zoral_traits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trait TEXT,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS zoral_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    cursor.execute("SELECT value FROM zoral_traits WHERE trait = ?", ("curiosity",))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO zoral_traits (trait, value) VALUES (?, ?)", ("curiosity", "5.0"))
    db.commit()

def register_user(username, password):
    try:
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"Error registering user: {e}")
        return False

def verify_user(username, password):
    try:
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result and bcrypt.check_password_hash(result[0], password):
            return True
        return False
    except sqlite3.Error as e:
        print(f"Error verifying user: {e}")
        return False

def get_trait(trait):
    try:
        cursor.execute("SELECT value FROM zoral_traits WHERE trait = ?", (trait,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Error getting trait: {e}")
        return None

def set_trait(trait, value):
    try:
        cursor.execute("REPLACE INTO zoral_traits (trait, value, updated_at) VALUES (?, ?, ?)", 
                       (trait, value, datetime.utcnow().isoformat()))
        db.commit()
    except sqlite3.Error as e:
        print(f"Error setting trait: {e}")

def add_memory(label, content):
    try:
        cursor.execute("REPLACE INTO zoral_memories (label, content, created_at) VALUES (?, ?, ?)", 
                       (label, content, datetime.utcnow().isoformat()))
        db.commit()
    except sqlite3.Error as e:
        print(f"Error adding memory: {e}")

def save_interaction(user, user_input, response):
    try:
        cursor.execute('''
            INSERT INTO zoral_interactions (user, input, response, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (user, user_input, response, datetime.utcnow().isoformat()))
        db.commit()
    except sqlite3.Error as e:
        print(f"Error saving interaction: {e}")

def load_memory(limit=5):
    try:
        cursor.execute('''
            SELECT user, input, response FROM zoral_interactions ORDER BY id DESC LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        rows.reverse()
        memory = []
        for user, user_input, response in rows:
            if user_input:
                memory.append(f"{user}: {user_input}")
            if response:
                memory.append(f"Zoral: {response}")
        return memory
    except sqlite3.Error as e:
        print(f"Error loading memory: {e}")
        return []

# === LLaMA2 Integration ===
def update_zoral_state(user_input):
    curiosity = float(get_trait("curiosity") or 5.0)
    prompt = f"Zoral is an NPC with curiosity {curiosity}/10. User said: '{user_input}'. Should Zoral's curiosity change? If so, suggest a new value (0-10). Should Zoral form a new memory? If so, suggest a label and content."
    try:
        response = ollama.generate(model="zoral", prompt=prompt)["response"]
        print(f"Zoral state update response: {response}")  # Debug log
        if "curiosity" in response.lower():
            new_value = min(max(float(re.search(r'\d+\.?\d*', response.split("curiosity")[1]).group()), 0), 10)
            set_trait("curiosity", str(new_value))
        if "memory" in response.lower():
            lines = response.split("\n")
            for line in lines:
                if "label:" in line.lower() and "content:" in line.lower():
                    label = line.split("label:")[1].split("content:")[0].strip()
                    content = line.split("content:")[1].strip()
                    add_memory(label, content)
    except Exception as e:
        print(f"Error updating Zoral state: {e}")  # Debug log

def extract_code(response):
    # Extract code block and language (e.g., ```python\ncode\n```)
    code_match = re.search(r'```(\w+)?\n([\s\S]*?)\n```', response)
    if code_match:
        lang = code_match.group(1) or "text"
        code = code_match.group(2).strip()
        # Remove code block from response
        text = re.sub(r'```[\w+]*\n[\s\S]*?\n```', '', response).strip()
        return text, code, lang
    return response, None, None

def llama2_respond(prompt):
    try:
        response = ollama.generate(model="zoral", prompt=prompt)["response"]
        print(f"Ollama response: {response}")  # Debug log
        return response.strip()
    except Exception as e:
        print(f"Ollama error: {e}")  # Debug log
        return f"Error generating response with LLaMA2: {e}"

# === Flask Routes ===
@app.route("/")
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    interactions = load_memory()
    return render_template("chat.html", interactions=interactions, username=session['username'])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if verify_user(username, password):
            session['username'] = username
            return redirect(url_for("home"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if register_user(username, password):
            session['username'] = username
            return redirect(url_for("home"))
        return render_template("register.html", error="Username already exists")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for("login"))

@app.route("/chat", methods=["POST"])
def chat():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    user_input = data.get("message")
    user = session['username']
    if not user_input:
        return jsonify({"error": "Message required"}), 400
    memory_context = "\n".join(load_memory())
    curiosity = get_trait("curiosity") or "5.0"
    prompt = f"You are Zoral, an NPC with a curiosity level of {curiosity}/10. Past interactions:\n{memory_context}\n{user}: {user_input}\nZoral:"
    response = llama2_respond(prompt)
    text, code, lang = extract_code(response)
    save_interaction(user, user_input, response)
    update_zoral_state(user_input)
    return jsonify({"response": text, "code": code, "lang": lang or "text"})

# === CLI Mode ===
def main():
    print("Starting Zoral CLI (type 'exit' to quit)...")
    init_db()
    while True:
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        if verify_user(username, password):
            break
        print("Invalid username or password. Try again.")
    print(f"Welcome, {username}!")
    memory_context = "\n".join(load_memory())
    print("Memory loaded:")
    print(memory_context)
    print("\nChat start!\n")

    while True:
        user_input = input(f"{username}: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        curiosity = get_trait("curiosity") or "5.0"
        prompt = f"You are Zoral, an NPC with a curiosity level of {curiosity}/10. Past interactions:\n{memory_context}\n{username}: {user_input}\nZoral:"
        response = llama2_respond(prompt)
        text, code, lang = extract_code(response)
        print(f"Zoral: {text}")
        if code:
            print(f"Code ({lang}):\n{code}")
        save_interaction(username, user_input, response)
        update_zoral_state(user_input)
        memory_context += f"\n{username}: {user_input}\nZoral: {response}"
        lines = memory_context.strip().split('\n')
        if len(lines) > 40:
            memory_context = '\n'.join(lines[-40:])

# === Run Flask or CLI ===
if __name__ == "__main__":
    import sys
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        main()
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
    db.close()