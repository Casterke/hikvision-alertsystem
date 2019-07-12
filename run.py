import datetime
import time
import sys
import os
import json
import cv2
import numpy as np
import requests
import threading
from requests.auth import HTTPDigestAuth
from pushbullet import Pushbullet
import xml.etree.ElementTree as ET
from shutil import copyfile


class Config():
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.cfg_path = self.root_dir + '/cfg/'
        self.cfg_file = self.cfg_path + 'config.json'
        with open(self.cfg_file) as config:
            self.configuration = json.load(config)
    
            self.nvr_url = self.configuration['nvr']['url']
            self.nvr_usr = self.configuration['nvr']['user']
            self.nvr_pass = self.configuration['nvr']['pass']
            self.opencv_weights = self.configuration['opencv']['weights']
            self.opencv_class = self.configuration['opencv']['class']
            self.opencv_config = self.configuration['opencv']['config']
            self.pb_api_key = self.configuration['pushbullet']['api_key']


        # CONFIGS ENDS
        self.xml_namespace = 'http://www.hikvision.com/ver20/XMLSchema'

        self.default_headers = {
            'Content-Type': "application/xml; charset='UTF-8'",
            'Accept': "*/*"
        }

class CameraImage():
    def __init__(self, config, channel_id):
        self.config = config
        self.channel_id = channel_id
        self.alerting_classes = self.config.configuration['channels'][self.channel_id]['alert_on']

    def _pretty_print_rec_objects(self, rec_objects):
        for object, confidence in rec_objects:
            output += "obj: %s ; conf: %s === " % (object, confidence) 
        return output

    def process_snapshot_threaded(self):
        thread = threading.Thread(target=self._process_snapshot)
        thread.start()

    def _process_snapshot(self):
        date = datetime.datetime.now()
        snapshot_filename = self._download_snapshot(date.strftime("%Y-%m-%d_%H-%M-%S"), self.channel_id)
        process_input_path = self.config.root_dir + '/snapshot/%s' % snapshot_filename
        process_output_path = self.config.root_dir + '/output/%s' % snapshot_filename

        if snapshot_filename is False:
            return

        if self.channel_id is False:
            return

        rec_objects = self._recognize_image(process_input_path, process_output_path)
        attachment_file = process_output_path

        if len(rec_objects) > 0:
            print('Sending push because we recognize these: %s' % rec_objects)
            text = ('%s %s %s' % (
                date.strftime("%Y-%m-%d %H:%M:%S"), self.channel_id, rec_objects))
            self._send_push_attachment(self.config.pb_api_key, text, attachment_file)
        else:
            print('Not recognized anything so delete the snapshot and output')
            #As file at filePath is deleted now, so we should check if file exists or not not before deleting them
            if os.path.exists(process_input_path):
                os.remove(process_input_path)
            if os.path.exists(process_output_path):
                os.remove(process_output_path)
            else:
                print('Can not delete the file as it doesn\'t exists')
        return


    def _recognize_image(self, input_image_name, output_image_name):
        image = cv2.imread(input_image_name)
        width = image.shape[1]
        height = image.shape[0]

        opencv_weights = (self.config.cfg_path + self.config.opencv_weights)
        opencv_config = (self.config.cfg_path + self.config.opencv_config)
        opencv_classes = (self.config.cfg_path + self.config.opencv_class)

        classes = None
        with open(opencv_classes, 'r') as f:
            classes = [line.strip() for line in f.readlines()]

        net = cv2.dnn.readNet(opencv_weights, opencv_config)
        blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (608, 608), True, False)
        net.setInput(blob)
        outs = net.forward(self._get_output_layers(net))
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

        recognized_objects =  []

        for i in indices:
            i = i[0]
            box = boxes[i]
            x = box[0]
            y = box[1]
            w = box[2]
            h = box[3]

            object_name = str(classes[int(class_ids[i])])
            object_confidence = round(confidences[i], 3)
            if object_name in self.alerting_classes:             
                self._draw_prediction(image, object_name, object_confidence, round(x), round(y), round(x + w), round(y + h))
                detected_object = { object_name: object_confidence}
                recognized_objects.append(detected_object)

        # Save the image
        cv2.imwrite(output_image_name, image)

        return recognized_objects

    def _draw_prediction(self, img, object_name, object_confidence, x, y, x_plus_w, y_plus_h):
        label = '%s - %s' % (object_name.upper(), object_confidence)
        cv2.rectangle(img, (x, y), (x_plus_w, y_plus_h), (0, 0, 255), 2)
        cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    def _get_output_layers(self, net):
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]

        return output_layers

    def _send_push_attachment(self, api_key, text, file=None):
        pb = Pushbullet(api_key)
        # If the file exist than open and push, otherwise attach an error message to the content
        if os.path.exists(file):
            with open(file, "rb") as fil:
                file_data = pb.upload_file(fil, text)
            pb.push_file(**file_data)
        else:
            print('Error: File does not exists. file:' + file)

    def _download_snapshot(self, date, channel_id):
        picture_url = self.config.nvr_url + \
                    '/ISAPI/Streaming/channels/%s01/picture?' \
                    'videoResolutionWidth=1920&' \
                    'videoResolutionHeight=1080' % channel_id

        hik_request = requests.Session()
        hik_request.auth = HTTPDigestAuth(self.config.nvr_usr, self.config.nvr_pass)
        hik_request.headers.update(self.config.default_headers)

        r = hik_request.get(picture_url, stream=True)
        if r.status_code == 200:
            print('%s - Downloaded snapshot successfully' % date)
            with open(self.config.root_dir + '/snapshot/%s-channel-%s.jpg' % (date, channel_id), 'wb') as f:
                f.write(r.content)
            return '%s-channel-%s.jpg' % (date, channel_id)

        return False

class EventStream():
    def __init__(self, config):
        self.config = config
        self.hik_request = requests.Session()
        self.hik_request.auth = HTTPDigestAuth(self.config.nvr_usr, self.config.nvr_pass)
        self.hik_request.headers.update(self.config.default_headers)

        self.url = self.config.nvr_url + '/ISAPI/Event/notification/alertStream'
    
    def detect_event(self):
        parse_string = ''
        start_event = False
        fail_count = 0

        detection_date = datetime.datetime.now()
        detection_id = '0'

        log_file = open(self.config.root_dir + "/log.txt", "a+")
        try:
            stream = self.hik_request.get(self.url, stream=True, timeout=(5, 60))

            if stream.status_code != requests.codes.ok:
                raise ValueError('Connection unsuccessful.')
            else:
                print('Connection successful to: ' + self.config.nvr_url)
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

                            channelID = tree.find('{%s}%s' % (self.config.xml_namespace, 'channelID'))
                            if channelID is None:
                                # Some devices use a different key
                                channelID = tree.find('{%s}%s' % (self.config.xml_namespace, 'dynChannelID'))

                            if channelID.text == '0':
                                # Continue and clear the chunk
                                parse_string = ""
                                continue

                            eventType = tree.find('{%s}%s' % (self.config.xml_namespace, 'eventType'))
                            eventState = tree.find('{%s}%s' % (self.config.xml_namespace, 'eventState'))
                            postCount = tree.find('{%s}%s' % (self.config.xml_namespace, 'activePostCount'))
                            print(eventType.text,eventState.text,postCount.text)

                            current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            log_file.write('%s - count: %s event: %s eventState: %s channel_id: %s\n' % (
                                current_date, postCount.text, eventType.text, eventState.text, channelID.text))
                            if 'detection' in eventType.text:
                                # Only trigger the event if the event not repeated in 5 sec
                                if (detection_date < datetime.datetime.now() - datetime.timedelta(
                                        seconds=5)) and (detection_id != channelID):
                                    log_file.write('count: %s (triggered)\n' % postCount.text)
                                    detection_date = datetime.datetime.now()
                                    detection_id = channelID.text
                             
                                    # start the subprocess to process by channelID
                                    image = CameraImage(self.config, detection_id)
                                    image.process_snapshot_threaded()
                                else:
                                    log_file.write(
                                        'count: %s last detection time: %s last channel id: %s (not triggered)\n' % (
                                            postCount.text, detection_date.strftime("%Y-%m-%d %H:%M:%S"), detection_id))

                            # Clear the chunk
                            parse_string = ""

                    else:
                        if start_event:
                            parse_string += str_line

        except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as err:
            fail_count += 1
            time.sleep(fail_count * 5)

def main():
    config = Config()
    stream = EventStream(config)
    while True:
        stream.detect_event()
        continue

if __name__ == "__main__":
    main()
