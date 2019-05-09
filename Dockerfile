FROM python:3.7
MAINTAINER joel.lupfer@gmail.com

ENV PYTHONUNBUFFERED=0

WORKDIR /hikalert/app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

RUN wget -P cfg/ 'https://pjreddie.com/media/files/yolov3.weights'

COPY . .

VOLUME /config

VOLUME /output

CMD [ "python","-u","/hikalert/app/run.py" ]
