from ultralytics import YOLO
import cv2

model = YOLO("Model/runs_11s/detect/train/weights/best.pt")

img = cv2.imread("captured/Missing_Text_20251021_161320.jpg")
results = model(img, conf=0.25, verbose=False)

for box in results[0].boxes:
    print(model.names[int(box.cls[0])], float(box.conf[0]))
