import os
import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify
from datetime import datetime
import base64
from deepface import DeepFace
import sqlite3
from pathlib import Path
import time

app = Flask(__name__)

DATABASE_PATH = "database/attendance.db"
FACES_DIR = "database/faces"
SPOOFING_THRESHOLD = 0.01

Path(FACES_DIR).mkdir(parents=True, exist_ok=True)
Path("database").mkdir(parents=True, exist_ok=True)


class AttendanceDB:
    def __init__(self):
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                face_encoding_path TEXT NOT NULL,
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                punch_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence_score REAL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        conn.commit()
        conn.close()

    def register_user(self, name, face_path):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (name, face_encoding_path) VALUES (?, ?)",
                (name, face_path)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def get_user_by_name(self, name):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
        user = cursor.fetchone()
        conn.close()
        return user

    def record_attendance(self, user_id, punch_type, confidence):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO attendance (user_id, punch_type, confidence_score) VALUES (?, ?, ?)",
            (user_id, punch_type, confidence)
        )
        conn.commit()
        conn.close()

    def get_today_attendance(self, user_id):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT punch_type, timestamp FROM attendance 
            WHERE user_id = ? 
            AND DATE(timestamp) = DATE('now')
            ORDER BY timestamp DESC
        ''', (user_id,))
        records = cursor.fetchall()
        conn.close()
        return records

    def get_all_users(self):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name FROM users")
        users = cursor.fetchall()
        conn.close()
        return users

    def get_attendance_history(self, days=7):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name, a.punch_type, a.timestamp, a.confidence_score
            FROM attendance a
            JOIN users u ON a.user_id = u.user_id
            WHERE DATE(a.timestamp) >= DATE('now', '-' || ? || ' days')
            ORDER BY a.timestamp DESC
        ''', (days,))
        history = cursor.fetchall()
        conn.close()
        return history


db = AttendanceDB()


class FaceRecognitionSystem:
    def __init__(self):
        self.model_name = "Facenet512"
        self.distance_metric = "cosine"
        self.detection_backend = "opencv"

    def detect_liveness(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(laplacian_var / 1000, 1.0)

        color_std = np.std([
            np.std(frame[:, :, 0]),
            np.std(frame[:, :, 1]),
            np.std(frame[:, :, 2])
        ])

        liveness_score = (sharpness_score + min(color_std / 100, 1.0)) / 2
        is_live = liveness_score > SPOOFING_THRESHOLD

        return is_live, liveness_score

    def register_face(self, frame, name):
        try:
            is_live, liveness_score = self.detect_liveness(frame)

            if not is_live:
                return {
                    "success": False,
                    "message": f"Liveness check failed. Please use live camera feed. (Score: {liveness_score:.2f})"
                }

            face_path = os.path.join(FACES_DIR, f"{name}_{int(time.time())}.jpg")
            cv2.imwrite(face_path, frame)

            user_id = db.register_user(name, face_path)

            if user_id is None:
                return {
                    "success": False,
                    "message": "User already exists!"
                }

            return {
                "success": True,
                "message": f"User {name} registered successfully!",
                "user_id": user_id,
                "liveness_score": liveness_score
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error during registration: {str(e)}"
            }

    def recognize_face(self, frame):
        try:
            is_live, liveness_score = self.detect_liveness(frame)

            if not is_live:
                return {
                    "success": False,
                    "message": f"Spoof detected! Liveness score: {liveness_score:.2f}"
                }

            users = db.get_all_users()

            if not users:
                return {
                    "success": False,
                    "message": "No registered users found!"
                }

            best_match = None
            best_distance = float('inf')

            for user_id, name in users:
                user_data = db.get_user_by_name(name)
                face_path = user_data[2]

                try:
                    result = DeepFace.verify(
                        img1_path=frame,
                        img2_path=face_path,
                        model_name=self.model_name,
                        distance_metric=self.distance_metric,
                        detector_backend=self.detection_backend,
                        enforce_detection=False
                    )

                    distance = result['distance']

                    if distance < best_distance and result['verified']:
                        best_distance = distance
                        best_match = (user_id, name)

                except Exception:
                    continue

            if best_match is None:
                return {
                    "success": False,
                    "message": "Face not recognized!"
                }

            user_id, name = best_match
            confidence = 1 - best_distance

            today_records = db.get_today_attendance(user_id)

            if not today_records:
                punch_type = "PUNCH-IN"
            elif today_records[0][0] == "PUNCH-IN":
                punch_type = "PUNCH-OUT"
            else:
                punch_type = "PUNCH-IN"

            db.record_attendance(user_id, punch_type, confidence)

            return {
                "success": True,
                "name": name,
                "punch_type": punch_type,
                "confidence": confidence,
                "liveness_score": liveness_score,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Recognition error: {str(e)}"
            }


face_system = FaceRecognitionSystem()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        name = data.get('name')
        image_data = data.get('image')

        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = face_system.register_face(frame, name)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        })


@app.route('/authenticate', methods=['POST'])
def authenticate():
    try:
        data = request.json
        image_data = data.get('image')

        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = face_system.recognize_face(frame)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        })


@app.route('/history')
def history():
    try:
        records = db.get_attendance_history(days=7)
        history_data = [
            {
                "name": record[0],
                "punch_type": record[1],
                "timestamp": record[2],
                "confidence": f"{record[3]:.2f}"
            }
            for record in records
        ]
        return jsonify({"success": True, "history": history_data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/users')
def users():
    try:
        users_list = db.get_all_users()
        return jsonify({
            "success": True,
            "users": [{"id": u[0], "name": u[1]} for u in users_list]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


if __name__ == '__main__':
    print("Face Authentication Attendance System Starting...")
    print("Navigate to http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
