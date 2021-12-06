import threading

from time import time, sleep
from datetime import datetime, timedelta
from nearest import *


class RepeatedTimer(object):
    """
    Copied from: https://stackoverflow.com/questions/474528/what-is-the-best-way-to-repeatedly-execute-a-function-every-x-seconds
    """
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
            self._timer = threading.Timer(self.next_call - time(), self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


class NearestTimer(RepeatedTimer):
    def __init__(self, resolution, function, delay = 0, *args, **kwargs):
        self.resolution = resolution
        self._timer = None
        self.interval = resolution_to_seconds[resolution]
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        #print("Start time: ")
        #print(datetime.now())
        self.delay = delay
        self.start()

    def start(self):
        if not self.is_running:
            now = datetime.now().timestamp()
            start_time = next_interval[self.resolution](now, delay=self.delay) #+ delay
            print("The next execution will start at: ")
            print(datetime.fromtimestamp(start_time))
            self._timer = threading.Timer(start_time - time(), self._run)
            self._timer.start()
            self.is_running = True

if '__main__' == __name__:
    def print_now():
        print("The current time is: ", datetime.now())

    timer = NearestTimer("1m", print_now, delay=1)