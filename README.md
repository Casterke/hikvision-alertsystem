# hikvision-alertsystem
Using python to access the Hikvision ISAPI alertstream to catch a specific "linecrossing" event with help of the YOLOv3 and OpenCV
to analyze the camera snapshot.
The script will send an email message with the image attached if anything recognized.

[Docker]
In order to make it work with docker you need to attach some volume. (config, output, snapshot)

- [ ] Improve script error handling
- [ ] Improve script speed
- [ ] Simplify installation by docker
- [ ] Refactor code

<p><a href="https://registry.hub.docker.com/u/casterke/hikvision-alertsystem/"><img src="http://dockeri.co/image/casterke/hikvision-alertsystem" alt="docker" title="docker"></a></p>
