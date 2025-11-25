# Automated Bottle Quality Inspection System
Project ini dibuat untuk kebutuhan magang sebagai sistem inspeksi kualitas botol menggunakan Computer Vision dan Machine Learning.

## 🔧 Teknologi yang digunakan
- Python
- YOLOv11
- Fast R-CNN
- Flask (Web Interface)
- OpenCV
- MySQL

## 🚀 Fitur Utama
- Real-time detection botol menggunakan webcam
- Klasifikasi Normal vs Defect (Touching Characters, Missing Text, Double Print)
- Line-crossing counting system (region-based)
- Penyimpanan hasil deteksi ke database
- UI untuk monitoring dan gallery defect

## 📁 Struktur Folder
📦 Project/
┣ 📂 dataset
┣ 📂 model
┣ 📂 app
┣ 📂 captured
┣ 🐍 app.py
┣ 🐍 Fast-rcnn.py
┗ 📄 README.md


## 🧪 Training Model
YOLOv11 dilatih menggunakan dataset internal dengan ukuran 640x640, batch size 16, dan 100 epoch.  
Fast R-CNN digunakan sebagai perbandingan performa model.

## 📌 Installation

```sh
pip install -r requirements.txt
python app.py


👤 Author
Valentino Fernando – Electrical Engineering @ UMN
