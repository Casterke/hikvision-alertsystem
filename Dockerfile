FROM python:3.11
MAINTAINER joel.lupfer@gmail.com

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Pre-cache YOLO model
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

COPY . .

RUN mkdir -p /app/data/snapshot /app/data/output /app/data/events

VOLUME /app/data
VOLUME /config

EXPOSE 5000

CMD ["python", "-u", "run.py"]
