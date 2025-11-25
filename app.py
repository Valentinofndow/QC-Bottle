# app.py — REGION-BASED LINE COUNTER (Final, cleaned)
# Author: adapted for Valentino Fernando — region-based approach
# Notes: Replace MODEL_PATH with your trained weights path.

from flask import Flask, render_template, redirect, session, request, jsonify, Response, send_from_directory
from models import db, Bottle
from datetime import datetime, timedelta
from ultralytics import YOLO
from sqlalchemy import func
from threading import Thread
import cv2, os, time, glob, threading, math
import numpy as np

# ====================================================================
# CONFIGURATION
# ====================================================================
MODEL_PATH = "model/runs_v2_s2_fix/detect/train/weights/best.pt"  # <-- adjust if needed
RESET_KEY = os.getenv("RESET_KEY", "admin123")

# Tuning
CONF_THRESH = 0.45       # YOLO conf threshold
LINE_REL_POS = 0.5       # LINE position as fraction of frame width (0.5 = center)
LAMP_MS = 1000           # lamp duration for defect (ms)
SAVE_ONLY_DEFECT = False # save only defect images or all

# Display flags
SHOW_LINE = True
AUTO_HIDE_LINE_AFTER = 3.0  # seconds; set 0 to never hide

# ----------------- FLASK & DB -----------------
app = Flask(__name__)
app.secret_key = "something_secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:NewPass123@localhost/bottle_inspection"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

print(f"[server] RESET_KEY: {RESET_KEY!r}")

GOOD_LABEL = "Normal"
DEFECT_CLASSES = {"Touching_Characters", "Double_Print", "Missing_Text"}
def norm(l): return l.strip().replace(" ", "_")
GOOD_KEY = norm(GOOD_LABEL)
DEFECT_KEYS = {norm(x) for x in DEFECT_CLASSES}

# ====================================================================
# YOLO MODEL
# ====================================================================
print("[model] loading YOLO model:", MODEL_PATH)
model = YOLO(MODEL_PATH)

# ====================================================================
# CAMERA SETUP
# ====================================================================
cam_lock = threading.Lock()
CURRENT_CAM = 0
cams = {}
for i in (0, 1, 2):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    ok, _ = cap.read()
    if ok and cap.isOpened():
        cams[i] = cap
        print(f"[camera] CAM {i} connected")
    else:
        try: cap.release()
        except: pass
        cams[i] = None
        print(f"[camera] CAM {i} not detected")

os.makedirs("captured", exist_ok=True)

def set_camera(index: int):
    global CURRENT_CAM
    with cam_lock:
        if index not in cams:
            return False, f"CAM {index} unknown"
        cap = cams[index]
        if cap is None or not cap.isOpened():
            return False, f"CAM {index} disconnected"
        CURRENT_CAM = index
        return True, f"CAM {index} active"

# ====================================================================
# SHARED STATE
# ====================================================================
latest_frame = None
latest_annotated = None
running = True

# in-memory counters (quick access) — DB is source of truth
good_count = 0
defect_count = 0

# lamp
lamp_state = False
lamp_lock = threading.Lock()

def trigger_lamp(duration_ms=LAMP_MS):
    def _worker():
        global lamp_state
        with lamp_lock:
            lamp_state = True
        time.sleep(duration_ms / 1000.0)
        with lamp_lock:
            lamp_state = False
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

# ====================================================================
# DB COUNTS — single source of truth (needed by routes & overlay)
# ====================================================================
def get_db_counts():
    """Return (good, defect) totals from the database."""
    with app.app_context():
        rows = db.session.query(Bottle.category, func.count()).group_by(Bottle.category).all()
        counts = {k: int(v) for k, v in rows}
    good_total = counts.get(GOOD_KEY, 0)
    defect_total = sum(counts.get(k, 0) for k in DEFECT_KEYS)
    return good_total, defect_total

# ====================================================================
# YOLO WORKER — REGION BASED
# ====================================================================
def yolo_worker():
    global latest_frame, latest_annotated, good_count, defect_count

    print("[worker] REGION-BASED MODE ACTIVE")

    # track_state keyed by tracker id only (we skip detections without a tracker id)
    # Structure: tid -> { seen_left:bool, counted:bool, best_label:str, best_conf:float, ts_first:datetime }
    track_state = {}

    while running:
        frame = latest_frame
        if frame is None:
            time.sleep(0.02)
            continue

        try:
            # Use model.track so Ultralytics tries to assign stable IDs
            results = model.track(source=frame, persist=True, conf=CONF_THRESH, verbose=False)

            if len(results) == 0:
                latest_annotated = frame.copy()
                continue

            res = results[0]
            annotated = res.plot()
            latest_annotated = annotated

            boxes = res.boxes

            # SAFE extraction — YOLO may return empty boxes or id None
            if len(boxes):
                xyxy_arr = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().tolist()
                # cls/index safe
                try:
                    clss = boxes.cls.int().cpu().tolist()
                except Exception:
                    clss = [0] * len(xyxy_arr)
                # ids can be None (no tracker id); handle that
                if boxes.id is None:
                    ids = [None] * len(xyxy_arr)
                else:
                    ids = boxes.id.int().cpu().tolist()
            else:
                xyxy_arr, confs, clss, ids = [], [], [], []

            fh, fw = frame.shape[:2]
            LINE = fw // 2  # counting line in the middle

            now = datetime.now()

            for i, box in enumerate(xyxy_arr):
                tid = ids[i]           # may be None
                conf = float(confs[i])
                label = norm(model.names[clss[i]]) if clss and i < len(clss) else GOOD_KEY

                # centroid X
                x1, y1, x2, y2 = box
                cx = float((x1 + x2) / 2.0)

                # IMPORTANT: follow your rule — only count objects that were seen on the LEFT first.
                # Without tracker id we can't verify "seen_left" across frames reliably, so skip those.
                if tid is None:
                    # skip detection-only boxes: must have been tracked from left first
                    continue

                # init state for new track id
                if tid not in track_state:
                    track_state[tid] = {
                        "seen_left": False,
                        "counted": False,
                        "best_label": label,
                        "best_conf": conf,
                        "ts_first": now
                    }

                st = track_state[tid]

                # update best label/confidence if improved
                if conf > st["best_conf"]:
                    st["best_conf"] = conf
                    st["best_label"] = label

                # mark seen_left if centroid on left half
                if cx < LINE:
                    st["seen_left"] = True

                # region-based event: if object was seen left and now is in right half (cx >= LINE)
                if st["seen_left"] and not st["counted"] and cx >= LINE:
                    st["counted"] = True

                    final_label = st["best_label"]
                    final_conf = st["best_conf"]

                    ts_h = now.strftime("%Y-%m-%d %H:%M:%S")
                    ts_f = now.strftime("%Y%m%d_%H%M%S")

                    # DEFECT
                    if final_label in DEFECT_KEYS:
                        defect_count += 1
                        fname = f"captured/{final_label}_{ts_f}.jpg"
                        cv2.imwrite(fname, frame)

                        with app.app_context():
                            db.session.add(Bottle(
                                timestamp=ts_h,
                                category=final_label,
                                confidence=final_conf,
                                image_path=fname
                            ))
                            db.session.commit()

                        trigger_lamp(LAMP_MS)
                        print(f"[CROSS] DEFECT +1 | {final_label} | {final_conf:.2f}")

                    # NORMAL
                    else:
                        good_count += 1
                        fname = ""
                        if not SAVE_ONLY_DEFECT:
                            fname = f"captured/{GOOD_KEY}_{ts_f}.jpg"
                            cv2.imwrite(fname, frame)

                        with app.app_context():
                            db.session.add(Bottle(
                                timestamp=ts_h,
                                category=GOOD_KEY,
                                confidence=final_conf,
                                image_path=fname
                            ))
                            db.session.commit()

                        print(f"[CROSS] GOOD +1 | {final_label} | {final_conf:.2f}")

            # cleanup track_state to avoid memory growth
            to_del = []
            for tid, st in track_state.items():
                age = (now - st["ts_first"]).total_seconds()
                if st["counted"] and age > 10:
                    to_del.append(tid)
                if age > 60:  # too old
                    to_del.append(tid)
            for tid in to_del:
                track_state.pop(tid, None)

        except Exception as e:
            print("[worker] ERROR:", e)
            import traceback
            traceback.print_exc()

        time.sleep(0.01)

# ====================================================================
# STREAM (video feed)
# ====================================================================
def generate_frames():
    global latest_frame, latest_annotated
    line_shown_time = time.time()

    while True:
        with cam_lock:
            cap = cams.get(CURRENT_CAM)

        if cap is None or not cap.isOpened():
            img = 30 * np.ones((360,640,3), dtype=np.uint8)
            cv2.putText(img, "Camera disconnected", (20,180),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,255), 2)
            ok, buffer = cv2.imencode(".jpg", img)
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + buffer.tobytes() + b"\r\n")
            time.sleep(0.3)
            continue

        ok, frame = cap.read()
        if not ok:
            continue

        latest_frame = frame.copy()
        annotated = latest_annotated if latest_annotated is not None else frame.copy()

        fh, fw = annotated.shape[:2]
        LINE = int(fw * LINE_REL_POS)

        # auto-hide line after some seconds (initial visual aid)
        show_line_now = SHOW_LINE
        if AUTO_HIDE_LINE_AFTER and (time.time() - line_shown_time) > AUTO_HIDE_LINE_AFTER:
            show_line_now = False

        if show_line_now:
            cv2.line(annotated, (LINE, 0), (LINE, fh), (0,255,0), 3)

        # overlay DB counts
        g, d = get_db_counts()
        overlay = annotated.copy()
        cv2.rectangle(overlay, (10,10), (420,80), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)

        cv2.putText(annotated,
                    f"GOOD: {g} | DEFECT: {d}",
                    (20,50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0,255,0),
                    2)

        ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + buffer.tobytes() + b"\r\n")

# ====================================================================
# FLASK ROUTES
# ====================================================================
@app.route("/")
def index(): return redirect("/login")

@app.route("/login", methods=["GET","POST"])
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
    session.clear(); return redirect("/login")

@app.route("/main")
def main_page():
    if "logged_in" not in session: return redirect("/login")
    return render_template("main.html")

@app.route("/analysis")
def analysis_page():
    if "logged_in" not in session: return redirect("/login")
    return render_template("analysis.html")

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/set_cam", methods=["POST"])
def set_cam():
    index = int(request.args.get("i", 0)); ok,msg = set_camera(index); return jsonify({"ok": ok, "msg": msg})

@app.route("/camera_status")
def camera_status():
    with cam_lock:
        cap = cams.get(CURRENT_CAM)
    if cap is None or not cap.isOpened(): return jsonify({"ok": False, "msg":"Disconnected"})
    return jsonify({"ok": True, "msg": f"CAM {CURRENT_CAM} aktif"})

@app.route("/stats")
def stats():
    rows = db.session.query(Bottle.category, func.count()).group_by(Bottle.category).all()
    counts = {k:int(v) for k,v in rows}
    good_total = counts.get(GOOD_KEY, 0)
    defect_total = sum(counts.get(k,0) for k in DEFECT_KEYS)
    total = good_total + defect_total
    p_good = (good_total/total*100) if total else 0.0
    return jsonify({"good": good_total, "defect": defect_total, "percent_good": round(p_good,2), "percent_defect": round(100-p_good,2)})

@app.route("/api/analysis_data")
def api_analysis_data():
    from models import get_total_stats, get_defect_breakdown
    totals = get_total_stats()
    breakdown = get_defect_breakdown()
    categories = ['Touching_Characters','Double_Print','Missing_Text']
    breakdown_full = {k:int(breakdown.get(k,0)) for k in categories}
    response = {"good": totals.get("good",0),"defect": totals.get("defect",0),"percent_good": totals.get("percent_good",0.0),"percent_defect": totals.get("percent_defect",0.0),"breakdown": breakdown_full}
    return jsonify(response)

@app.route("/stats_detail")
def stats_detail():
    try:
        from models import get_defect_breakdown
        breakdown = get_defect_breakdown() or {}
        data = {"Touching_Characters": breakdown.get("Touching_Characters",0),"Double_Print": breakdown.get("Double_Print",0),"Missing_Text": breakdown.get("Missing_Text",0)}
        return jsonify(data)
    except Exception as e:
        print("[API ERROR]", e)
        return jsonify({"Touching_Characters":0,"Double_Print":0,"Missing_Text":0}), 500

@app.route("/live_counts")
def live_counts():
    g, d = get_db_counts()
    return jsonify({"good": g, "defect": d})

@app.route("/gallery")
def gallery_page():
    if "logged_in" not in session: return redirect("/login")
    defects = Bottle.query.filter(Bottle.category != GOOD_KEY).order_by(Bottle.timestamp.desc()).all()
    return render_template("gallery.html", defects=defects)

@app.route("/captured/<path:filename>")
def serve_captured(filename): return send_from_directory("captured", filename)

@app.route("/reset", methods=["POST"])
def reset():
    data = request.get_json(silent=True) or {}
    key = data.get("key",""); check_only = data.get("checkOnly", False)
    if key != RESET_KEY: return jsonify({"ok": False, "msg": "unauthorized"}), 401
    if check_only: return jsonify({"ok": True})
    try:
        with app.app_context():
            deleted_rows = db.session.query(Bottle).delete(); db.session.commit()
        deleted_images = 0
        for img_path in glob.glob(os.path.join("captured","*.jpg")):
            try: os.remove(img_path); deleted_images +=1
            except Exception as e: print("[RESET] failed remove", img_path, e)
        return jsonify({"ok": True, "deleted_rows": deleted_rows, "deleted_images": deleted_images})
    except Exception as e:
        print("[RESET ERROR]", e)
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/lamp_state")
def get_lamp_state():
    with lamp_lock:
        s = bool(lamp_state)
    return jsonify({"lamp": s})

# ====================================================================
# MAIN
# ====================================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("[db] tables created/verified")
        try:
            rows = db.session.query(Bottle.category, func.count()).group_by(Bottle.category).all()
            counts = {k:int(v) for k,v in rows}
            good_count = counts.get(GOOD_KEY,0)
            defect_count = sum(counts.get(k,0) for k in DEFECT_KEYS)
            print(f"[init] GOOD={good_count} DEFECT={defect_count}")
        except Exception as e:
            print("[init] failed to load counters:", e)

    Thread(target=yolo_worker, daemon=True).start()
    print("[worker] started")
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
