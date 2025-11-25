# Automated Bottle Quality Inspection System
Sistem ini dikembangkan sebagai bagian dari program magang untuk melakukan inspeksi kualitas botol secara otomatis menggunakan Computer Vision dan Machine Learning.

---

## 🔧 Teknologi yang Digunakan

- Python
- YOLOv11
- Fast R-CNN
- Flask (Web Interface)
- OpenCV
- MySQL

---

## 🚀 Fitur Utama

- Real-time bottle detection menggunakan webcam
- Klasifikasi kondisi botol:
  - Normal
  - Touching Characters
  - Missing Text
  - Double Print
- Line-crossing counting system berbasis region
- Penyimpanan hasil deteksi ke database
- Web dashboard untuk monitoring dan gallery defect

---

## 📁 Struktur Folder
📦 Project/
┣ 📂 dataset
┣ 📂 model
┣ 📂 captured
┣ 📂 static
┣ 📂 templates
┣ 🐍 app.py
┣ 🐍 models.py
┣ 📄 requirements.txt
┗ 📄 README.md

> Catatan: Folder seperti `venv/`, `__pycache__/`, `model/runs/`, dan file berat seperti `.pt` tidak disertakan di repository.

---

## 🧪 Training Model

YOLOv11 dilatih menggunakan dataset internal dengan parameter berikut:

| Parameter  | Nilai    |
|------------|----------|
| Image size | 640×640  |
| Batch size | 16       |
| Epoch      | 100      |

Fast R-CNN digunakan sebagai baseline pembanding performa deteksi.

---

## 📌 Installation

```sh
pip install -r requirements.txt
python app.py

---

🛠 Git Workflow (Supaya Tidak Mem-Push venv)
Repo ini sudah menggunakan .gitignore untuk menghindari commit ke file yang tidak diperlukan seperti venv/.

Gunakan alur berikut saat update project:
🔹 Menambahkan file baru
        git add <nama_file>
        git commit -m "Add new feature or file"
        git push    
🔹 Update file existing
        git add -u
        git commit -m "Update logic or fix bug"
        git push
🔹 Update dependency (setelah install library baru)
        pip freeze > requirements.txt
        git add requirements.txt
        git commit -m "Update dependencies"
        git push


👤 Author

Valentino Fernando
Electrical Engineering – Universitas Multimedia Nusantara