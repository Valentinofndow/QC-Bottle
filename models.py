# models.py — UPDATED VERSION
# Improvements:
# ✅ Tambah kolom object_id untuk track unique bottles
# ✅ Tambah index untuk faster queries
# ✅ Better column types untuk MySQL

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Bottle(db.Model):
    """
    Model untuk menyimpan hasil inspeksi botol
    
    Columns:
    - id: Primary key (auto increment)
    - timestamp: Waktu botol melewati garis (string format: "YYYY-MM-DD HH:MM:SS")
    - category: Kategori botol (Normal, Double_Print, Missing_Text, Touching_Characters)
    - confidence: Confidence score dari YOLO (0.0 - 1.0)
    - image_path: Path ke gambar yang disimpan (bisa kosong)
    - object_id: ID tracking objek (untuk debugging dan tracing)
    """
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Timestamp inspeksi
    # Format: "2025-01-15 14:30:45"
    timestamp = db.Column(db.String(32), nullable=False, index=True)
    
    # Kategori hasil inspeksi
    # Possible values: "Normal", "Double_Print", "Missing_Text", "Touching_Characters"
    category = db.Column(db.String(64), nullable=False, index=True)
    
    # Confidence score dari YOLO (0.0 - 1.0)
    # Disimpan sebagai FLOAT dengan 4 decimal precision
    confidence = db.Column(db.Float, default=0.0, nullable=False)
    
    # Path ke gambar yang disimpan
    # Format: "captured/Normal_20250115_143045_ID123.jpg"
    # Bisa kosong kalau SAVE_ONLY_DEFECT=True dan botol normal
    image_path = db.Column(db.String(256), default="")
    
    # ID tracking objek (untuk debugging)
    # Ini adalah ID yang diassign oleh tracking system
    # Berguna untuk trace back kalau ada masalah counting
    object_id = db.Column(db.Integer, nullable=True, index=True)
    
    def __repr__(self):
        """
        String representation untuk debugging
        """
        return f"<Bottle #{self.id} | {self.category} | {self.confidence:.2f} | {self.timestamp}>"
    
    def to_dict(self):
        """
        Convert object ke dictionary (untuk API response)
        """
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'category': self.category,
            'confidence': round(self.confidence, 4),
            'image_path': self.image_path,
            'object_id': self.object_id
        }


# ============================================================================
# HELPER FUNCTIONS (OPTIONAL)
# ============================================================================

def get_total_stats():
    """
    Get total statistik inspeksi
    
    Returns:
        dict: {
            'total': int,
            'good': int,
            'defect': int,
            'percent_good': float,
            'percent_defect': float
        }
    """
    from sqlalchemy import func
    
    # Query group by category
    rows = db.session.query(
        Bottle.category, 
        func.count(Bottle.id)
    ).group_by(Bottle.category).all()
    
    counts = {category: count for category, count in rows}
    
    # Hitung total good & defect
    good = counts.get('Normal', 0)
    defect = sum(counts.get(cat, 0) for cat in ['Double_Print', 'Missing_Text', 'Touching_Characters'])
    total = good + defect
    
    # Hitung persentase
    percent_good = (good / total * 100) if total > 0 else 0.0
    percent_defect = 100.0 - percent_good
    
    return {
        'total': total,
        'good': good,
        'defect': defect,
        'percent_good': round(percent_good, 2),
        'percent_defect': round(percent_defect, 2),
        'breakdown': counts
    }


def get_recent_defects(limit=50):
    """
    Get defect bottles terbaru
    
    Args:
        limit (int): Jumlah maksimum record yang diambil
        
    Returns:
        list: List of Bottle objects yang defect
    """
    return Bottle.query.filter(
        Bottle.category != 'Normal'
    ).order_by(
        Bottle.timestamp.desc()
    ).limit(limit).all()


def get_defect_breakdown():
    """
    Get breakdown defect per kategori.
    Selalu kembalikan semua kategori (0 jika tidak ada datanya).
    """
    from sqlalchemy import func

    # Daftar kategori defect yang kita pakai di sistem
    defect_categories = ['Double_Print', 'Missing_Text', 'Touching_Characters']

    # Query hitung jumlah per kategori yang ada di DB
    rows = db.session.query(
        Bottle.category,
        func.count(Bottle.id)
    ).filter(
        Bottle.category.in_(defect_categories)
    ).group_by(Bottle.category).all()

    # Convert hasil ke dict
    row_map = {category: int(count) for category, count in rows}

    # Lengkapi kategori yang tidak muncul dengan 0
    full_breakdown = {cat: row_map.get(cat, 0) for cat in defect_categories}

    return full_breakdown



# ============================================================================
# DATABASE MIGRATION NOTES
# ============================================================================
"""
CARA MIGRATION DARI SCHEMA LAMA KE BARU:

1. Backup database dulu:
   mysqldump -u root -p bottle_inspection > backup.sql

2. Tambah kolom object_id:
   ALTER TABLE bottle ADD COLUMN object_id INT NULL;
   ALTER TABLE bottle ADD INDEX idx_object_id (object_id);

3. Atau drop table dan bikin ulang (HATI-HATI: DATA HILANG!):
   DROP TABLE bottle;
   
4. Jalankan app.py, Flask akan auto-create table baru
"""