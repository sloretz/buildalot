import queue
import sys
import threading


class CohesiveOutput:
    """Makes sure output is cohesively streamed.

    If two unrelated tasks want to output to the console, CohesiveOutput
    will make sure all of the logs from the first task to start are output
    before the logs from the second task begin.
    """

    # The currently active output
    output_lock: threading.Lock = threading.Lock()
    has_active_output: bool = False
    output_queue: queue.Queue = queue.Queue()

    def __init__(self, name: str):
        self._name = name
        self._buffer = [f">>> Begin output from: {name}\n"]
        self._lock = threading.Lock()
        self._is_active_output = False
        self._exited: bool = False

    @classmethod
    def _join_output_queue(cls, instance):
        with cls.output_lock:
            cls.output_queue.put(instance)
            if not cls.has_active_output:
                # First in the queue!
                cls._next_in_queue()

    @classmethod
    def _next_in_queue(cls):
        try:
            next_output = cls.output_queue.get_nowait()
        except queue.Empty:
            # No more outputs in the queue
            return
        # Dump all output
        with next_output._lock:
            for line in next_output._buffer:
                sys.stdout.write(line)
            if not next_output._exited:
                # Become active output
                next_output._is_active_output = True
                cls.has_active_output = True

    def write(self, line):
        with self._lock:
            if self._is_active_output:
                sys.stdout.write(line)
            else:
                self._buffer.append(line)

    def __enter__(self):
        type(self)._join_output_queue(self)
        return self

    def __exit__(self, t, v, tb):
        self.write(f"<<< End output from: {self._name}\n")
        with type(self).output_lock:
            self._exited = True
            self._is_active_output = False
            type(self).has_active_output = False
            type(self)._next_in_queue()
