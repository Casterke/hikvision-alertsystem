# hikvision-detection

## General
Using python to access the Hikvision ISAPI alertstream to catch a specific event with help of the YOLOv3 and OpenCV
to analyze the camera snapshot. The script will send an Pushbullet notification. 

## More details
Forked from [hikvision-alertsystem](https://github.com/Casterke/hikvision-alertsystem). Consolidated the code a little bit and swapped the email sending with pushbullet notifications.

Added features:
- Pushbullet support
- Ability to limit per channel the list of objects that raise an alert
- Moved config to a json format

## Steps to make it run
 - Install numpy opencv, requests and pushbullet from pip
 - Download yolov3.weights file to the cfg folder from [here](https://pjreddie.com/media/files/yolov3.weights)
 - Create a config.json file in the cfg folder based on the example file that is there - config_example.json

## NB! Be aware
Still pretty raw and needs a lot of cleanup.





