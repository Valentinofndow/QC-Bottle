# Automated Bottle Quality Inspection (Improved Line Crossing Counter)
# Author: Valentino Fernando (Improved Version)
# Context: Internship Project - Automated Bottle Quality Inspection using Vision & ML
# Improvements: Better tracking, label consistency, database-ready structure

from ultralytics import YOLO
import cv2
import math
from datetime import datetime

# ============================================================================
# KONFIGURASI MODEL & CAMERA
# ============================================================================

# Load model YOLO yang udah di-training
model = YOLO("runs_11s2/detect/train/weights/best.pt")

# Buka webcam (0 = default camera, ganti ke 1/2 kalau ada multiple camera)
cap = cv2.VideoCapture(0)

# Set resolusi camera biar lebih stabil (opsional, bisa di-comment kalau ga perlu)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# ============================================================================
# PARAMETER TRACKING
# ============================================================================

# Jarak maksimum (dalam pixel) untuk menganggap 2 deteksi adalah objek yang sama
# Kalau jarak centroid < threshold ini, dianggap objek yang sama di frame berikutnya
DISTANCE_THRESHOLD = 120

# Berapa frame objek masih dianggap "hidup" meskipun tidak terdeteksi YOLO
# Berguna kalau YOLO miss detection 1-2 frame karena blur/lighting
OBJECT_LIFETIME = 15

# Minimum confidence YOLO buat deteksi dianggap valid (0.0 - 1.0)
# Semakin tinggi, semakin strict (less false positive tapi mungkin miss detection)
DETECTION_CONFIDENCE = 0.5

# Zona "deadzone" di sekitar garis crossing (dalam pixel)
# Objek harus benar-benar melewati zona ini baru dihitung
# Berguna buat mencegah objek yang "nongkrong" di garis terus-terusan
CROSSING_DEADZONE = 10

# ============================================================================
# COUNTER VARIABLES
# ============================================================================

# Counter utama
total_count = 0      # Total semua botol yang lewat garis
good_count = 0       # Botol dengan kualitas "Normal"
defect_count = 0     # Botol dengan defect (semua kelas selain Normal)

# Counter per jenis defect (opsional, berguna buat statistik detail)
defect_breakdown = {
    "Double_Print": 0,
    "Missing_Text": 0,
    "Touching_Characters": 0
}

# ============================================================================
# TRACKING DATA STRUCTURE
# ============================================================================

# List untuk menyimpan semua objek yang sedang di-track
# Struktur: Dictionary dengan format:
# {
#     'id': int,              # ID unik objek
#     'cx_prev': float,       # Posisi X sebelumnya (untuk deteksi crossing)
#     'cx_now': float,        # Posisi X saat ini
#     'cy': float,            # Posisi Y (untuk matching)
#     'lifetime': int,        # Sisa umur objek (frame)
#     'label': str,           # Label kelas (LOCKED setelah pertama kali terdeteksi)
#     'confidence': float,    # Confidence score tertinggi
#     'has_crossed': bool,    # Sudah melewati garis atau belum
#     'timestamp': datetime   # Waktu pertama kali terdeteksi (untuk database)
# }
tracked_objects = []

# ID counter untuk assign ID baru ke objek yang baru terdeteksi
next_object_id = 1

# ============================================================================
# CLASS NAMES (sesuai urutan training YOLO)
# ============================================================================
CLASS_NAMES = ["Double_Print", "Missing_Text", "Normal", "Touching_Characters"]

# ============================================================================
# FUNGSI HELPER
# ============================================================================

def calculate_distance(x1, y1, x2, y2):
    """
    Menghitung jarak Euclidean antara dua titik
    Digunakan untuk matching objek antar frame
    
    Args:
        x1, y1: Koordinat titik pertama
        x2, y2: Koordinat titik kedua
    
    Returns:
        float: Jarak antara dua titik
    """
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


def find_matching_object(cx, cy, label, confidence):
    """
    Mencari objek yang sudah di-track yang cocok dengan deteksi baru
    
    Algoritma:
    1. Loop semua objek yang sedang di-track
    2. Hitung jarak antara deteksi baru dengan posisi objek terakhir
    3. Kalau jarak < threshold, dianggap objek yang sama
    4. Return objek dengan jarak terkecil (kalau ada beberapa kandidat)
    
    Args:
        cx: Posisi X centroid deteksi baru
        cy: Posisi Y centroid deteksi baru
        label: Label kelas dari YOLO
        confidence: Confidence score dari YOLO
    
    Returns:
        dict or None: Objek yang cocok, atau None kalau ga ketemu
    """
    best_match = None
    min_distance = float('inf')  # Inisialisasi dengan nilai tak hingga
    
    # Loop semua objek yang sedang di-track
    for obj in tracked_objects:
        # Hitung jarak antara deteksi baru dengan posisi objek saat ini
        dist = calculate_distance(cx, cy, obj['cx_now'], obj['cy'])
        
        # Kalau jarak < threshold DAN ini jarak terkecil yang ditemukan
        if dist < DISTANCE_THRESHOLD and dist < min_distance:
            min_distance = dist
            best_match = obj
    
    return best_match


def create_new_object(obj_id, cx, cy, label, confidence):
    """
    Membuat objek tracking baru
    Dipanggil saat YOLO mendeteksi objek yang belum pernah di-track
    
    Args:
        obj_id: ID unik untuk objek baru
        cx: Posisi X centroid
        cy: Posisi Y centroid
        label: Label kelas dari YOLO
        confidence: Confidence score dari YOLO
    
    Returns:
        dict: Objek tracking baru
    """
    return {
        'id': obj_id,
        'cx_prev': cx,           # Posisi awal = posisi saat ini
        'cx_now': cx,
        'cy': cy,
        'lifetime': OBJECT_LIFETIME,
        'label': label,          # LABEL DI-LOCK DI SINI, ga akan berubah lagi
        'confidence': confidence,
        'has_crossed': False,
        'timestamp': datetime.now()  # Untuk database nanti
    }


def update_object(obj, cx, cy, confidence):
    """
    Update posisi objek yang sudah di-track
    
    PENTING: Label TIDAK di-update! Label tetap seperti saat pertama kali terdeteksi
    Ini mencegah label berubah-ubah yang bikin counter jadi salah
    
    Args:
        obj: Dictionary objek yang mau di-update
        cx: Posisi X baru
        cy: Posisi Y baru
        confidence: Confidence score baru
    """
    # Pindahkan posisi sekarang ke posisi sebelumnya
    obj['cx_prev'] = obj['cx_now']
    
    # Update posisi sekarang
    obj['cx_now'] = cx
    obj['cy'] = cy
    
    # Reset lifetime karena objek masih terdeteksi
    obj['lifetime'] = OBJECT_LIFETIME
    
    # Update confidence kalau yang baru lebih tinggi (opsional)
    if confidence > obj['confidence']:
        obj['confidence'] = confidence
    
    # CATATAN: obj['label'] TIDAK di-update! Tetap label pertama kali


def check_crossing(obj, mid_x):
    """
    Mengecek apakah objek melewati garis virtual
    
    Logika:
    - Objek harus dari kiri ke kanan (cx_prev < mid_x dan cx_now >= mid_x)
    - Objek belum pernah melewati garis sebelumnya (has_crossed == False)
    - Ada deadzone untuk mencegah objek yang "stuck" di garis
    
    Args:
        obj: Dictionary objek yang mau dicek
        mid_x: Posisi X garis virtual
    
    Returns:
        bool: True kalau objek baru saja melewati garis
    """
    # Kalau objek udah pernah lewat garis, langsung return False
    if obj['has_crossed']:
        return False
    
    # Cek apakah objek melewati garis dari kiri ke kanan
    # Dengan deadzone untuk memastikan objek benar-benar melewati
    crossed_line = (
        obj['cx_prev'] < (mid_x - CROSSING_DEADZONE) and 
        obj['cx_now'] >= (mid_x + CROSSING_DEADZONE)
    )
    
    return crossed_line


def log_crossing_event(obj, count_number):
    """
    Logging event crossing (untuk debugging dan database)
    
    Fungsi ini bisa diperluas untuk:
    - Simpan ke database MySQL
    - Save screenshot botol
    - Trigger rejection system (kalau defect)
    
    Args:
        obj: Dictionary objek yang melewati garis
        count_number: Nomor urut botol
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✓ GOOD" if obj['label'] == "Normal" else "✗ DEFECT"
    
    print(f"[{timestamp}] Botol #{count_number} | {status} | Class: {obj['label']} | Conf: {obj['confidence']:.2f}")
    
    # TODO: Simpan ke database MySQL di sini
    # Contoh struktur query:
    # INSERT INTO inspections (timestamp, bottle_number, status, class_name, confidence)
    # VALUES (?, ?, ?, ?, ?)

# ============================================================================
# MAIN LOOP
# ============================================================================

print("=" * 60)
print("BOTTLE QUALITY INSPECTION SYSTEM")
print("=" * 60)
print("Controls:")
print("  ESC  : Exit program")
print("  R    : Reset counters")
print("=" * 60)

while True:
    # Baca frame dari camera
    ret, frame = cap.read()
    
    # Kalau gagal baca frame (camera disconnect/error), break loop
    if not ret:
        print("ERROR: Tidak bisa membaca frame dari camera!")
        break
    
    # Dapatkan dimensi frame
    frame_height, frame_width = frame.shape[:2]
    
    # Hitung posisi garis virtual di tengah frame
    mid_x = frame_width // 2
    
    # ========================================================================
    # DETEKSI YOLO
    # ========================================================================
    
    # Jalankan YOLO detection
    # conf=DETECTION_CONFIDENCE: hanya deteksi dengan confidence > threshold
    # verbose=False: matikan print output YOLO biar ga spam terminal
    results = model.predict(frame, conf=DETECTION_CONFIDENCE, verbose=False)
    
    # Ambil semua bounding boxes dari hasil deteksi
    boxes = results[0].boxes
    
    # List untuk menyimpan deteksi frame ini
    current_detections = []
    
    # Loop semua deteksi dari YOLO
    for box in boxes:
        # Ambil koordinat bounding box (x1, y1, x2, y2)
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        
        # Hitung centroid (titik tengah) bounding box
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        
        # Ambil class ID dan confidence
        class_id = int(box.cls.cpu().numpy())
        confidence = float(box.conf.cpu().numpy())
        
        # Convert class ID ke nama kelas
        label = CLASS_NAMES[class_id]
        
        # Simpan ke list deteksi
        current_detections.append({
            'cx': cx,
            'cy': cy,
            'label': label,
            'confidence': confidence
        })
    
    # ========================================================================
    # UPDATE TRACKING
    # ========================================================================
    
    # Set untuk tracking deteksi mana yang udah di-match
    matched_detections = set()
    
    # Loop semua deteksi dan coba match dengan objek yang udah di-track
    for idx, detection in enumerate(current_detections):
        # Cari objek yang cocok dengan deteksi ini
        matching_obj = find_matching_object(
            detection['cx'], 
            detection['cy'],
            detection['label'],
            detection['confidence']
        )
        
        if matching_obj is not None:
            # Objek ketemu! Update posisi objek yang udah ada
            update_object(
                matching_obj,
                detection['cx'],
                detection['cy'],
                detection['confidence']
            )
            matched_detections.add(idx)
        else:
            # Objek baru! Buat tracking baru
            new_obj = create_new_object(
                next_object_id,
                detection['cx'],
                detection['cy'],
                detection['label'],
                detection['confidence']
            )
            tracked_objects.append(new_obj)
            next_object_id += 1
            matched_detections.add(idx)
    
    # ========================================================================
    # DECREASE LIFETIME & REMOVE DEAD OBJECTS
    # ========================================================================
    
    # Kurangi lifetime semua objek yang tidak terdeteksi di frame ini
    for obj in tracked_objects:
        obj['lifetime'] -= 1
    
    # Hapus objek yang sudah "mati" (lifetime habis)
    tracked_objects = [obj for obj in tracked_objects if obj['lifetime'] > 0]
    
    # ========================================================================
    # CHECK LINE CROSSING
    # ========================================================================
    
    # Loop semua objek yang sedang di-track
    for obj in tracked_objects:
        # Cek apakah objek melewati garis
        if check_crossing(obj, mid_x):
            # Increment counter
            total_count += 1
            
            # Mark objek sudah melewati garis (prevent double counting)
            obj['has_crossed'] = True
            
            # Update counter berdasarkan label
            if obj['label'] == "Normal":
                good_count += 1
            else:
                defect_count += 1
                # Update breakdown per jenis defect
                if obj['label'] in defect_breakdown:
                    defect_breakdown[obj['label']] += 1
            
            # Log event (dan simpan ke database di sini)
            log_crossing_event(obj, total_count)
    
    # ========================================================================
    # VISUALISASI
    # ========================================================================
    
    # Gambar bounding boxes + labels dari YOLO
    annotated_frame = results[0].plot()
    
    # Gambar garis virtual di tengah
    cv2.line(annotated_frame, (mid_x, 0), (mid_x, frame_height), (0, 255, 0), 3)
    
    # Gambar zona deadzone (opsional, untuk debugging)
    # Uncomment kalau mau lihat zona deadzone
    # cv2.line(annotated_frame, (mid_x - CROSSING_DEADZONE, 0), 
    #          (mid_x - CROSSING_DEADZONE, frame_height), (255, 255, 0), 1)
    # cv2.line(annotated_frame, (mid_x + CROSSING_DEADZONE, 0), 
    #          (mid_x + CROSSING_DEADZONE, frame_height), (255, 255, 0), 1)
    
    # Gambar tracking points untuk setiap objek
    for obj in tracked_objects:
        # Warna: Hijau untuk Normal, Merah untuk Defect
        color = (0, 255, 0) if obj['label'] == "Normal" else (0, 0, 255)
        
        # Gambar circle di centroid
        cv2.circle(annotated_frame, (int(obj['cx_now']), int(obj['cy'])), 
                   6, color, -1)
        
        # Gambar ID dan label
        text = f"ID{obj['id']}: {obj['label']}"
        cv2.putText(annotated_frame, text, 
                    (int(obj['cx_now']) + 10, int(obj['cy']) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Gambar garis tracking (dari posisi sebelumnya ke sekarang)
        cv2.line(annotated_frame, 
                 (int(obj['cx_prev']), int(obj['cy'])),
                 (int(obj['cx_now']), int(obj['cy'])),
                 color, 2)
    
    # ========================================================================
    # DISPLAY COUNTERS
    # ========================================================================
    
    # Background semi-transparan untuk counter (biar lebih keliatan)
    overlay = annotated_frame.copy()
    cv2.rectangle(overlay, (10, 10), (400, 150), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, annotated_frame, 0.4, 0, annotated_frame)
    
    # Display counters
    y_offset = 40
    cv2.putText(annotated_frame, f"TOTAL: {total_count}", 
                (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    y_offset += 40
    cv2.putText(annotated_frame, f"GOOD: {good_count}", 
                (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    y_offset += 40
    cv2.putText(annotated_frame, f"DEFECT: {defect_count}", 
                (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    
    # Display window
    cv2.imshow("Bottle Quality Inspection System", annotated_frame)
    
    # ========================================================================
    # KEYBOARD CONTROLS
    # ========================================================================
    
    key = cv2.waitKey(1) & 0xFF
    
    # ESC: Exit program
    if key == 27:
        print("\nProgram dihentikan oleh user.")
        break
    
    # R: Reset counters
    elif key == ord('r') or key == ord('R'):
        total_count = 0
        good_count = 0
        defect_count = 0
        defect_breakdown = {k: 0 for k in defect_breakdown}
        tracked_objects = []
        next_object_id = 1
        print("\n[RESET] Semua counter di-reset ke 0")

# ============================================================================
# CLEANUP
# ============================================================================

# Release camera dan tutup semua windows
cap.release()
cv2.destroyAllWindows()

# Print summary
print("\n" + "=" * 60)
print("INSPECTION SESSION SUMMARY")
print("=" * 60)
print(f"Total Bottles Inspected: {total_count}")
print(f"Good Bottles: {good_count} ({good_count/total_count*100 if total_count > 0 else 0:.1f}%)")
print(f"Defect Bottles: {defect_count} ({defect_count/total_count*100 if total_count > 0 else 0:.1f}%)")
print("\nDefect Breakdown:")
for defect_type, count in defect_breakdown.items():
    print(f"  - {defect_type}: {count}")
print("=" * 60)