from app import app, db, Bottle
from datetime import datetime

with app.app_context():
    db.session.add(
        Bottle(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category="good",
            confidence=0.95,
            image_path="captured/good_test.jpg"
        )
    )

    db.session.add(
        Bottle(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category="defect",
            confidence=0.82,
            image_path="captured/defect_test.jpg"
        )
    )

    db.session.commit()
    print("Data dummy berhasil dimasukkan ke database!")
