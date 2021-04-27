import configparser
import datetime
import os
import shutil
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from os.path import basename
import cv2
import numpy as np
import requests
from requests.auth import HTTPDigestAuth
import sys

print("Subprocess started")

# CONFIGS START
config = configparser.ConfigParser()
exists = os.path.isfile('/config/config.ini')

if exists:
    config.read('/config/config.ini')

APP_PATH = config['DEFAULT']['APP_PATH']
NVR_URL = config['DEFAULT']['NVR_URL']
NVR_USR = config['DEFAULT']['NVR_USR']
NVR_PASS = config['DEFAULT']['NVR_PASS']
OPENCV_WEIGHTS = config['DEFAULT']['OPENCV_WEIGHTS']
OPENCV_CLASS = config['DEFAULT']['OPENCV_CLASS']
OPENCV_CONFIG = config['DEFAULT']['OPENCV_CONFIG']
GMAIL_EMAIL = config['DEFAULT']['GMAIL_EMAIL']
GMAIL_PASS = config['DEFAULT']['GMAIL_PASS']
EMAIL_RECEIVERS = (config['DEFAULT']['EMAIL_RECEIVERS']).split()

# CONFIGS ENDS

XML_NAMESPACE = 'http://www.hikvision.com/ver20/XMLSchema'

DEFAULT_HEADERS = {
    'Content-Type': "application/xml; charset='UTF-8'",
    'Accept': "*/*"
}

hik_request = requests.Session()
hik_request.auth = HTTPDigestAuth(NVR_USR, NVR_PASS)
hik_request.headers.update(DEFAULT_HEADERS)

url = NVR_URL + '/ISAPI/Event/notification/alertStream'


def draw_prediction(img, object_name, object_confidence, x, y, x_plus_w, y_plus_h):
    label = '%s - %s' % (object_name.upper(), object_confidence)
    cv2.rectangle(img, (x, y), (x_plus_w, y_plus_h), (0, 0, 255), 2)
    cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)


def get_output_layers(net):
    layer_names = net.getLayerNames()
    output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]

    return output_layers


def recognize_image(input_image_name, output_image_name):
    image = cv2.imread(input_image_name)
    width = image.shape[1]
    height = image.shape[0]

    opencv_weights = (APP_PATH + OPENCV_WEIGHTS)
    opencv_config = (APP_PATH + OPENCV_CONFIG)
    opencv_classes = (APP_PATH + OPENCV_CLASS)

    classes = None
    with open(opencv_classes, 'r') as f:
        classes = [line.strip() for line in f.readlines()]

    net = cv2.dnn.readNet(opencv_weights, opencv_config)
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (608, 608), True, False)
    net.setInput(blob)
    outs = net.forward(get_output_layers(net))
    class_ids = []
    confidences = []
    boxes = []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.2:
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                x = center_x - w / 2
                y = center_y - h / 2
                class_ids.append(class_id)
                confidences.append(float(confidence))
                boxes.append([x, y, w, h])

    conf_threshold = 0.5
    nms_threshold = 0.4
    indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)

    recognized_objects = ''

    for i in indices:
        i = i[0]
        box = boxes[i]
        x = box[0]
        y = box[1]
        w = box[2]
        h = box[3]

        object_name = str(classes[int(class_ids[i])])
        object_confidence = round(confidences[i], 3)
        draw_prediction(image, object_name, object_confidence, round(x), round(y), round(x + w), round(y + h))
        recognized_objects += '%s: (%s), ' % (object_name, object_confidence)

    # Save the image
    cv2.imwrite(output_image_name, image)

    return recognized_objects


def send_mail_attachment(send_to, subject, text, file=None):
    assert isinstance(send_to, list)

    # Gmail Sign In
    gmail_sender = GMAIL_EMAIL
    gmail_passwd = GMAIL_PASS

    msg = MIMEMultipart()
    msg['From'] = gmail_sender
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    # If the file exist than open and attach to the email, otherwise attach an error message to the content
    if os.path.exists(file):
        with open(file, "rb") as fil:
            part = MIMEApplication(
                fil.read(),
                Name=basename(file)
            )
            # After the file is closed
            part['Content-Disposition'] = 'attachment; filename="%s"' % basename(file)
            msg.attach(part)
    else:
        print('Error: File does not exists. file:' + file)

    smtp = smtplib.SMTP('smtp.gmail.com', 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(gmail_sender, gmail_passwd)

    smtp.sendmail(gmail_sender, send_to, msg.as_string())
    smtp.quit()


def download_snapshot(date, channel_id):
    picture_url = NVR_URL + \
                  '/ISAPI/Streaming/channels/%s01/picture?' \
                  'videoResolutionWidth=1920&' \
                  'videoResolutionHeight=1080' % channel_id

    r = hik_request.get(picture_url, stream=True, timeout=(5, 60), verify=False)
    if r.status_code == 200:
        print('%s - Downloaded snapshot successfully' % date)
        with open('/snapshot/%s-channel-%s.jpg' % (date, channel_id), 'wb') as f:
            f.write(r.content)
        return '%s-channel-%s.jpg' % (date, channel_id)

    return False


def process_snapshot(channel_id):
    date = datetime.datetime.now()
    snapshot_filename = download_snapshot(date.strftime("%Y-%m-%d_%H-%M-%S"), channel_id)
    process_input_path = '/snapshot/%s' % snapshot_filename
    process_output_path = '/output/%s' % snapshot_filename
    unrecognized_path = '/output/unrecognized/%s' % snapshot_filename

    if snapshot_filename is False:
        return

    if channel_id is False:
        return

    rec_objects = recognize_image(process_input_path, process_output_path)
    attachment_file = process_output_path
    send_to = EMAIL_RECEIVERS

    if rec_objects != '':
        print('Sending an email because we recognize these: %s' % rec_objects)
        text = ('Date: %s in the %s channel_id is a(n) %s recognized' % (
            date.strftime("%Y-%m-%d %H:%M:%S"), channel_id, rec_objects))
        send_mail_attachment(send_to, 'Movement detected', text, attachment_file)
    else:
        print('Not recognized anything.')
        #check the file before deleting/moving
        if os.path.exists(process_input_path):
            os.remove(process_input_path)
        if os.path.exists(process_output_path):
            shutil.move(process_output_path, unrecognized_path)
        else:
            print('Can not delete the file as it doesn\'t exists')
    return


# Process the arguments

if len(sys.argv) > 1:
    ch_id = sys.argv[1]
    process_snapshot(ch_id)
else:
    print('Error: Channel id not defined.')
