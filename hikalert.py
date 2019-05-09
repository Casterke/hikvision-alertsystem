import configparser
import datetime
import os
import smtplib
import time
import xml.etree.ElementTree as ET
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from os.path import basename
from shutil import copyfile

import cv2
import numpy as np
import requests
from requests.auth import HTTPDigestAuth

print("Hikvision alert started")

# CONFIGS START
config = configparser.ConfigParser()
exists = os.path.isfile('/config/config.ini')

if exists:
    config.read('/config/config.ini')
else:
    copyfile('cfg/config.ini', '/config/config.ini')
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
EMAIL_RECEIVERS = config['DEFAULT']['EMAIL_RECEIVERS']
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

print("Email address to send the notification:" + EMAIL_RECEIVERS)


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

    with open(file, "rb") as fil:
        part = MIMEApplication(
            fil.read(),
            Name=basename(file)
        )
    # After the file is closed
    part['Content-Disposition'] = 'attachment; filename="%s"' % basename(file)
    msg.attach(part)

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

    r = hik_request.get(picture_url, stream=True)
    if r.status_code == 200:
        print('%s - Downloaded snapshot successfully' % date)
        with open(APP_PATH + '/snapshot/%s-channel-%s.jpg' % (date, channel_id), 'wb') as f:
            f.write(r.content)
        return '%s-channel-%s.jpg' % (date, channel_id)

    return False


def process_snapshot(date, channel_id):
    snapshot_filename = download_snapshot(date.strftime("%Y-%m-%d_%H-%M-%S"), channel_id)
    process_input_path = APP_PATH + "/snapshot/%s" % snapshot_filename
    process_output_path = "/output/%s" % snapshot_filename

    if snapshot_filename is False:
        return

    if channelID is False:
        return

    rec_objects = recognize_image(process_input_path, process_output_path)
    attachment_file = process_output_path
    send_to = EMAIL_RECEIVERS

    if rec_objects != '':
        print('Sending an email because we recognize these: %s' % rec_objects)
        text = ('Date: %s in the %s channel_id is a(n) %s recognized' % (
            date.strftime("%Y-%m-%d %H:%M:%S"), channel_id, rec_objects))
        send_mail_attachment(send_to, 'Python script detected movement', text, attachment_file)
    else:
        print('Not recognized anything so not sending an email')
    return


parse_string = ''
start_event = False
fail_count = 0

detection_date = datetime.datetime.now()

while True:

    try:
        stream = hik_request.get(url, stream=True, timeout=(5, 60))

        if stream.status_code != requests.codes.ok:
            raise ValueError('Connection unsuccessful.')
        else:
            print('Connection Successful.')
            fail_count = 0

        for line in stream.iter_lines():
            # filter out keep-alive new lines
            if line:
                str_line = line.decode("utf-8")

                if str_line.find('<EventNotificationAlert') != -1:
                    start_event = True
                    parse_string += str_line
                elif str_line.find('</EventNotificationAlert>') != -1:
                    parse_string += str_line
                    start_event = False
                    if parse_string:
                        tree = ET.fromstring(parse_string)

                        channelID = tree.find('{%s}%s' % (XML_NAMESPACE, 'channelID'))
                        if channelID is None:
                            # Some devices use a different key
                            channelID = tree.find('{%s}%s' % (XML_NAMESPACE, 'dynChannelID'))

                        if channelID.text == '0':
                            parse_string = ""
                            continue

                        eventType = tree.find('{%s}%s' % (XML_NAMESPACE, 'eventType'))
                        eventState = tree.find('{%s}%s' % (XML_NAMESPACE, 'eventState'))
                        postCount = tree.find('{%s}%s' % (XML_NAMESPACE, 'activePostCount'))

                        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        print('%s - count: %s event: %s eventState: %s channel_id: %s ' % (
                            current_date, postCount.text, eventType.text, eventState.text,
                            channelID.text))
                        if eventType.text == 'linedetection':
                            # Only trigger the event if the event not repeated in 5 sec
                            if detection_date < datetime.datetime.now() - datetime.timedelta(seconds=5):
                                print('%s - count: %s event: %s eventState: %s channel_id: %s ' % (
                                    current_date, postCount.text, eventType.text, eventState.text,
                                    channelID.text))
                                detection_date = datetime.datetime.now()
                                # start the snapshot process
                                process_snapshot(detection_date, channelID.text)

                        parse_string = ""

                else:
                    if start_event:
                        parse_string += str_line

    except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as err:
        fail_count += 1
        time.sleep(fail_count * 5)
        continue
