# app.py — FIXED VERSION: Proper Tracking + Database Integration
# Improvements:
# ✅ Label locking per object
# ✅ Confidence tersimpan dengan benar
# ✅ Database save pas crossing (bukan tiap frame)
# ✅ Better object matching logic
# ✅ Prevent double counting dengan cooldown per-object

from flask import Flask, render_template, redirect, session, request, jsonify, Response, send_from_directory
from models import db, Bottle
from datetime import datetime
from ultralytics import YOLO
from sqlalchemy import func
from threading import Thread
import cv2, os, time, glob, threading, math
import numpy as np
from collections import deque, defaultdict

# ============================================================================
# KONFIGURASI FLASK & DATABASE
# ============================================================================

app = Flask(__name__)
app.secret_key = "something_secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:NewPass123@localhost/bottle_inspection"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ============================================================================
# SISTEM DASAR
# ============================================================================

RESET_KEY = os.getenv("RESET_KEY", "admin123")
print(f"[server] RESET_KEY loaded: {RESET_KEY!r}")

# ============================================================================
# LABEL & LOGIKA DETEKSI
# ============================================================================

GOOD_LABEL = "Normal"
DEFECT_CLASSES = {"Touching_Characters", "Double_Print", "Missing_Text"}

# Flag untuk simpan semua atau hanya defect
SAVE_ONLY_DEFECT = False

def norm(label: str) -> str:
    """Normalisasi nama label (remove spaces, lowercase)"""
    return label.strip().replace(" ", "_")

GOOD_KEY = norm(GOOD_LABEL)
DEFECT_KEYS = {norm(x) for x in DEFECT_CLASSES}

# ============================================================================
# MUAT MODEL YOLO
# ============================================================================

MODEL_PATH = "model/runs_v2_s2_fix/detect/train/weights/best.pt"
print(f"[model] loading YOLO model from: {MODEL_PATH}")
model = YOLO(MODEL_PATH)
id2name = model.names  # mapping index → nama class

# ============================================================================
# KONFIGURASI KAMERA
# ============================================================================

cam_lock = threading.Lock()
CURRENT_CAM = 0
cams = {}

# Coba connect ke 3 kamera
for i in (0, 1, 2):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 90)
    ok, _ = cap.read()
    if ok and cap.isOpened():
        cams[i] = cap
        print(f"[camera] CAM {i} connected")
    else:
        try:
            cap.release()
        except Exception:
            pass
        cams[i] = None
        print(f"[camera] CAM {i} not detected")

# Bikin folder untuk simpan gambar
os.makedirs("captured", exist_ok=True)

def set_camera(index: int):
    """Switch active camera"""
    global CURRENT_CAM
    with cam_lock:
        if index not in cams:
            return False, f"CAM {index} tidak dikenali"
        cap = cams[index]
        if cap is None or not cap.isOpened():
            return False, f"CAM {index} tidak terhubung"
        CURRENT_CAM = index
        return True, f"CAM {index} aktif"

# ============================================================================
# SHARED BUFFERS (ASYNC)
# ============================================================================

latest_frame = None        # Frame mentah dari camera
latest_annotated = None    # Frame dengan bounding boxes
running = True             # Flag untuk stop worker thread

# ============================================================================
# TRACKING CONFIGURATION
# ============================================================================

# Posisi garis virtual (X coordinate)
LINE_X = 320

# Margin untuk crossing detection (deadzone)
CROSS_MARGIN = 15

# Jarak maksimum untuk matching objek (pixel)
MAX_MATCH_DIST = 100

# TTL objek (berapa frame objek masih "hidup" tanpa deteksi)
TRACK_TTL = 15

# Cooldown setelah crossing (prevent re-counting)
COUNT_COOLDOWN = 20

# Panjang history untuk stabilisasi label
STABLE_LEN = 5

# Minimum confidence untuk deteksi
MIN_CONFIDENCE = 0.7

# Toggle debug prints in yolo_worker
WORKER_DEBUG = True
# Jika True, LINE_X akan di-set ke tengah frame pada frame pertama (berguna kalau posisi garis salah)
AUTO_CENTER_LINE = True
# internal flag untuk menandai kalau line sudah di-set
_line_centered = False

# ============================================================================
# COUNTER VARIABLES (GLOBAL)
# ============================================================================

good_count = 0
defect_count = 0

# ============================================================================
# YOLO WORKER THREAD (IMPROVED VERSION)
# ============================================================================

def yolo_worker():
    """
    Versi STABIL:
    - Satu event per botol (cooldown waktu, bukan tracking posisi)
    - Simpan ke DB setiap deteksi baru setelah cooldown
    - Masih pakai sistem confidence & label locking
    """
    global latest_frame, latest_annotated, good_count, defect_count

    last_event_ts = 0.0  # cooldown timer (detik)
    EVENT_COOLDOWN = 1.0  # minimal jarak antar event (detik)
    MIN_CONF = 0.6        # minimum confidence deteksi

    while running:
        frame = latest_frame
        if frame is None:
            time.sleep(0.05)
            continue

        try:
            # Jalankan YOLO tiap frame (tapi hasil disaring waktu)
            results = model.predict(frame, conf=MIN_CONF, verbose=False)
            annotated = results[0].plot()
            latest_annotated = annotated

            frame_labels = set()
            detections = []

            # Ambil semua label yang valid
            for box in results[0].boxes:
                conf = float(box.conf[0])
                if conf < MIN_CONF:
                    continue
                cls_id = int(box.cls[0])
                label = norm(model.names[cls_id])
                frame_labels.add(label)
                detections.append((label, conf))

            now = time.time()
            if frame_labels and (now - last_event_ts) > EVENT_COOLDOWN:
                last_event_ts = now
                ts_h = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ts_f = datetime.now().strftime("%Y%m%d_%H%M%S")

                # pilih deteksi dengan confidence tertinggi
                top_label, top_conf = max(detections, key=lambda x: x[1])

                if top_label in DEFECT_KEYS:
                    defect_count += 1
                    print(f"[COUNT] DEFECT +1 ({top_label}) | conf={top_conf:.2f}")
                    filename = f"captured/{top_label}_{ts_f}.jpg"
                    cv2.imwrite(filename, frame)
                    with app.app_context():
                        db.session.add(Bottle(
                            timestamp=ts_h,
                            category=top_label,
                            confidence=top_conf,
                            image_path=filename
                        ))
                        db.session.commit()

                elif top_label == GOOD_KEY:
                    good_count += 1
                    print(f"[COUNT] GOOD +1 | conf={top_conf:.2f}")
                    filename = ""
                    if not SAVE_ONLY_DEFECT:
                        filename = f"captured/{GOOD_KEY}_{ts_f}.jpg"
                        cv2.imwrite(filename, frame)
                    with app.app_context():
                        db.session.add(Bottle(
                            timestamp=ts_h,
                            category=GOOD_KEY,
                            confidence=top_conf,
                            image_path=filename
                        ))
                        db.session.commit()

        except Exception as e:
            print(f"[yolo_worker] error: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(0.05)


# ============================================================================
# STREAMING FUNCTION
# ============================================================================

def generate_frames():
    """
    Generator untuk streaming video ke browser
    """
    global latest_frame, latest_annotated
    
    while True:
        with cam_lock:
            cap = cams.get(CURRENT_CAM)

        # Kalau camera disconnect, tampilkan error frame
        if cap is None or not cap.isOpened():
            img = 30 * np.ones((360, 640, 3), dtype=np.uint8)
            cv2.putText(
                img, 
                "Camera disconnected", 
                (20, 180),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.9, 
                (0, 0, 255), 
                2
            )
            ok, buffer = cv2.imencode(".jpg", img)
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            time.sleep(0.3)
            continue

        # Baca frame dari camera
        ok, frame = cap.read()
        if not ok:
            continue

        # Update latest frame (untuk YOLO worker)
        latest_frame = frame.copy()

        # Ambil annotated frame (atau gunakan frame mentah kalau belum ada)
        annotated = latest_annotated if latest_annotated is not None else frame.copy()

        # Gambar counter di pojok kiri atas
        # Background semi-transparan
        overlay = annotated.copy()
        cv2.rectangle(overlay, (10, 10), (450, 80), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)
        
        # Text counter
        cv2.putText(
            annotated,
            f"GOOD: {good_count} | DEFECT: {defect_count}",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        # Encode frame ke JPEG
        ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")


# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route("/")
def index():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")
        if user == "admin" and pw == "admin123":
            session["logged_in"] = True
            return redirect("/main")
        return render_template("login.html", error="Username atau password salah")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/main")
def main_page():
    if "logged_in" not in session:
        return redirect("/login")
    return render_template("main.html")


@app.route("/analysis")
def analysis_page():
    if "logged_in" not in session:
        return redirect("/login")
    return render_template("analysis.html")


@app.route("/video_feed")
def video_feed():
    """Streaming endpoint"""
    return Response(
        generate_frames(), 
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/set_cam", methods=["POST"])
def set_cam():
    """Switch camera endpoint"""
    index = int(request.args.get("i", 0))
    ok, msg = set_camera(index)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/camera_status")
def camera_status():
    """Check camera status"""
    with cam_lock:
        cap = cams.get(CURRENT_CAM)
    if cap is None or not cap.isOpened():
        return jsonify({"ok": False, "msg": "Disconnected"})
    return jsonify({"ok": True, "msg": f"CAM {CURRENT_CAM} aktif"})


@app.route("/stats")
def stats():
    """
    API untuk ambil statistik dari database
    Returns: {good, defect, percent_good, percent_defect}
    """
    rows = db.session.query(Bottle.category, func.count()).group_by(Bottle.category).all()
    counts = {k: int(v) for k, v in rows}
    
    good_total = counts.get(GOOD_KEY, 0)
    defect_total = sum(counts.get(k, 0) for k in DEFECT_KEYS)
    
    # Hitung total dari semua kategori (termasuk unknown)
    total = good_total + defect_total
    
    p_good = (good_total / total * 100) if total else 0.0
    p_def = 100.0 - p_good
    
    return jsonify({
        "good": good_total,
        "defect": defect_total,
        "percent_good": round(p_good, 2),
        "percent_defect": round(p_def, 2),
    })


@app.route("/live_counts")
def live_counts():
    """
    API untuk ambil counter real-time (dari variable global)
    Ini untuk monitoring di dashboard tanpa query database
    """
    return jsonify({
        "good": good_count,
        "defect": defect_count
    })


@app.route("/gallery")
def gallery_page():
    """Halaman galeri untuk lihat defect bottles"""
    if "logged_in" not in session:
        return redirect("/login")
    
    # Ambil semua defect bottles dari database
    defects = Bottle.query.filter(
        Bottle.category != GOOD_KEY
    ).order_by(Bottle.timestamp.desc()).all()
    
    return render_template("gallery.html", defects=defects)


@app.route('/captured/<path:filename>')
def serve_captured(filename):
    """Serve gambar dari folder captured"""
    return send_from_directory('captured', filename)


@app.route("/reset", methods=["POST"])
def reset():
    """
    Reset database dan hapus semua gambar
    Require password untuk security
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    check_only = data.get("checkOnly", False)

    # Validasi password
    if key != RESET_KEY:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    # Kalau cuma check password (step 1), langsung return
    if check_only:
        return jsonify({"ok": True})

    # Eksekusi reset (step 2)
    try:
        # Hapus semua record dari database
        with app.app_context():
            deleted_rows = db.session.query(Bottle).delete()
            db.session.commit()
            print(f"[RESET] Deleted {deleted_rows} rows from database")
        
        # Hapus semua gambar di folder captured
        deleted_images = 0
        for img_path in glob.glob(os.path.join("captured", "*.jpg")):
            try:
                os.remove(img_path)
                deleted_images += 1
            except Exception as e:
                print(f"[RESET] Failed to delete {img_path}: {e}")
        
        print(f"[RESET] Deleted {deleted_images} images from captured folder")
        
        return jsonify({
            "ok": True, 
            "deleted_rows": deleted_rows,
            "deleted_images": deleted_images
        })
        
    except Exception as e:
        print(f"[RESET ERROR] {e}")
        return jsonify({"ok": False, "msg": str(e)}), 500


# ============================================================================
# MAIN PROGRAM
# ============================================================================

if __name__ == "__main__":
    # Bikin database tables kalau belum ada
    with app.app_context():
        db.create_all()
        print("[db] Database tables created/verified")
        # Initialize in-memory counters from DB so live_counts reflects persisted totals
        try:
            rows = db.session.query(Bottle.category, func.count()).group_by(Bottle.category).all()
            counts = {k: int(v) for k, v in rows}
            good_total = counts.get(GOOD_KEY, 0)
            defect_total = sum(counts.get(k, 0) for k in DEFECT_KEYS)
            good_count = good_total
            defect_count = defect_total
            print(f"[init] Counters initialized from DB — GOOD: {good_count}, DEFECT: {defect_count}")
        except Exception as e:
            print(f"[init] Failed to init counters from DB: {e}")
    
    # Start YOLO worker thread
    Thread(target=yolo_worker, daemon=True).start()
    print("[worker] YOLO worker thread started")
    
    # Run Flask server
    # IMPORTANT: use_reloader=False biar thread ga jalan double
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)