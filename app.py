from flask import Flask, render_template, request, redirect, session
import mysql.connector
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
import os
import numpy as np
import uuid
from PIL import Image
from collections import Counter

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__)
app.secret_key = "secret123"

# -----------------------------
# Load Model
# -----------------------------
cnn_model = load_model("sugarcane_model.keras")
print("✅ Model Loaded")

# -----------------------------
# Upload Config
# -----------------------------
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -----------------------------
# DB Connection
# -----------------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="suba",
        database="sugar"
    )

# -----------------------------
# Helpers
# -----------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_leaf_image(filepath):
    try:
        img = Image.open(filepath).convert("RGB").resize((224, 224))
        img_array = np.array(img)

        green_pixels = np.sum(
            (img_array[:, :, 1] > img_array[:, :, 0]) &
            (img_array[:, :, 1] > img_array[:, :, 2])
        )

        return (green_pixels / (224 * 224)) > 0.10
    except:
        return False


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload")
def upload_page():
    if "user_email" not in session:
        return redirect("/login")
    return render_template("upload.html")


# -----------------------------
# Static Pages
# -----------------------------
@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/diseases")
def diseases():
    return render_template("diseases.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/more")
def more():
    return render_template("more.html")


# -----------------------------
# Register
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""
    success = False

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            message = "Passwords do not match"
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO users (email, password) VALUES (%s, %s)",
                    (email, password)
                )

                conn.commit()
                success = True

            except mysql.connector.errors.IntegrityError:
                message = "User already exists"

            finally:
                cursor.close()
                conn.close()

    return render_template("register.html", message=message, success=success)


# -----------------------------
# Login (FIXED 🔥)
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # ✅ ADMIN LOGIN (IMPORTANT)
        if email == "admin@gmail.com" and password == "admin123":
            session["admin"] = True
            return redirect("/admin_dashboard")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user:
            message = "User not registered"
        elif user["password"] != password:
            message = "Wrong password"
        else:
            session["user_email"] = email

            # Save login log
            try:
                cursor.execute(
                    "INSERT INTO login_logs (email) VALUES (%s)",
                    (email,)
                )
                conn.commit()
            except:
                pass

            cursor.close()
            conn.close()
            return redirect("/upload")

        cursor.close()
        conn.close()

    return render_template("userlogin.html", message=message)


# -----------------------------
# Predict
# -----------------------------
@app.route("/predict", methods=["POST"])
def predict():

    if "user_email" not in session:
        return redirect("/login")

    file = request.files.get("image")

    if not file or not allowed_file(file.filename):
        return render_template("upload.html", error="Upload valid image")

    filename = str(uuid.uuid4()) + ".jpg"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    if not is_leaf_image(filepath):
        os.remove(filepath)
        return render_template("upload.html", error="Upload leaf image")

    img = image.load_img(filepath, target_size=(224, 224))
    img_array = image.img_to_array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    prediction = cnn_model.predict(img_array, verbose=0)[0]

    classes = ['healthy', 'mosaic', 'red_rot', 'rust', 'yellow']
    index = np.argmax(prediction)

    result = classes[index]
    confidence = float(prediction[index]) * 100

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO predictions (email, image_path, result, confidence) VALUES (%s, %s, %s, %s)",
        (session["user_email"], filepath, result, round(confidence, 2))
    )

    conn.commit()
    cursor.close()
    conn.close()

    return render_template(
        "upload.html",
        prediction=result,
        confidence=round(confidence, 2),
        image_path=filepath
    )


# -----------------------------
# History
# -----------------------------
@app.route("/history")
def history():
    if "user_email" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM predictions WHERE email=%s",
        (session["user_email"],)
    )
    predictions = cursor.fetchall()

    cursor.close()
    conn.close()

    results = [p["result"] for p in predictions]
    counts = Counter(results)

    return render_template(
        "history.html",
        predictions=predictions,
        labels=list(counts.keys()),
        values=list(counts.values())
    )


# -----------------------------
# Admin Dashboard
# -----------------------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT * FROM predictions")
    predictions = cursor.fetchall()

    try:
        cursor.execute("SELECT * FROM login_logs")
        logs = cursor.fetchall()
    except:
        logs = []

    cursor.close()
    conn.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        predictions=predictions,
        logs=logs
    )


# -----------------------------
# Logout
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)