FROM python:3.11
LABEL maintainer="joel.lupfer@gmail.com"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Required for dlib (face_recognition), OpenCV (libGL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Pre-cache YOLO, plate detection, and EasyOCR models
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); YOLO('https://huggingface.co/Koushim/yolov8-license-plate-detection/resolve/main/best.pt')" && \
    python -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False)"

COPY . .

RUN mkdir -p /app/data/snapshot /app/data/output /app/data/events

VOLUME /app/data
VOLUME /config

EXPOSE 5000

CMD ["python", "-u", "run.py"]
