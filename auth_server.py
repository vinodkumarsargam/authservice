from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
import os
import datetime
import logging
import boto3
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("authservice")

app = Flask(__name__)

DB_SSLCERT = "/certs/global-bundle.pem"

# Cache secret to avoid calling AWS every request
_cached_secret = None

def get_secret():
    global _cached_secret

    if _cached_secret:
        return _cached_secret

    client = boto3.client("secretsmanager", region_name="ap-northeast-1")

    response = client.get_secret_value(
        SecretId="authservice/db_credentials"
    )

    _cached_secret = json.loads(response["SecretString"])
    return _cached_secret


def get_db():
    secret = get_secret()

    return psycopg2.connect(
        host=secret["host"],
        port=secret["port"],
        dbname=secret["dbname"],
        user=secret["username"],
        password=secret["password"],
        sslmode="verify-full",
        sslrootcert=DB_SSLCERT,
    )


def get_jwt_secret():
    secret = get_secret()
    return secret["jwt_secret"]


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      VARCHAR(100) UNIQUE NOT NULL,
            email         VARCHAR(200) UNIQUE NOT NULL,
            password_hash VARCHAR(200) NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database initialised")


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ── Register ──────────────────────────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data     = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "username, email and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (username, email, pw_hash),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.IntegrityError:
        return jsonify({"error": "username or email already exists"}), 409
    except Exception as e:
        logger.error("register db error: %s", e)
        return jsonify({"error": "internal server error"}), 500

    SECRET_KEY = get_jwt_secret()

    token = jwt.encode(
        {
            "user_id":  user_id,
            "username": username,
            "email":    email,
            "exp":      datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=48),
        },
        SECRET_KEY,
        algorithm="HS256",
    )

    logger.info("registered user: %s", username)
    return jsonify({"token": token, "user_id": user_id, "username": username}), 201


# ── Login ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["POST"])
def login():
    data     = request.get_json(force=True)
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, username, email, password_hash FROM users WHERE email = %s",
            (email,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error("login db error: %s", e)
        return jsonify({"error": "internal server error"}), 500

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "invalid email or password"}), 401

    SECRET_KEY = get_jwt_secret()

    token = jwt.encode(
        {
            "user_id":  user["id"],
            "username": user["username"],
            "email":    user["email"],
            "exp":      datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=48),
        },
        SECRET_KEY,
        algorithm="HS256",
    )

    logger.info("login success: %s", user["username"])
    return jsonify({"token": token, "user_id": user["id"], "username": user["username"]}), 200


# ── Verify ────────────────────────────────────────────────────────────────────

@app.route("/verify", methods=["GET"])
def verify():
    token = request.args.get("token", "")
    if not token:
        return jsonify({"valid": False, "error": "no token provided"}), 400

    SECRET_KEY = get_jwt_secret()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return jsonify({
            "valid": True,
            "user_id": payload["user_id"],
            "username": payload["username"]
        }), 200
    except jwt.ExpiredSignatureError:
        return jsonify({"valid": False, "error": "token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"valid": False, "error": "invalid token"}), 401


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    init_db()
    app.run(host="0.0.0.0", port=port)