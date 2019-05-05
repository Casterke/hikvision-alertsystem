#!/usr/bin/python
import sys
from subprocess import Popen

filename = sys.argv[1]
while True:
    print("\nStarting " + filename)
    p = Popen("python " + filename, shell=True)
    p.wait()
