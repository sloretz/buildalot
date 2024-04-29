from abc import abstractmethod, ABC
from concurrent.futures import Future, ThreadPoolExecutor
import copy
from pathlib import Path
import shlex
import subprocess
import sys
from threading import Event, RLock
import time
from typing import Optional


class Work(ABC):

    @abstractmethod
    def __str__(self) -> str: ...

    @abstractmethod
    def __call__(self) -> None: ...

    def __hash__(self) -> int:
        return str(self).__hash__()


# WorkGraph is a dictionary where:
#  Key = Work
#  Value = Work that must finish before Key can be started
type WorkGraph = dict[Work, list[Work]]


def execute(graph: WorkGraph, max_workers=None):
    """Execute the given work graph."""
    # futures: list[Future] = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    all_done = Event()
    # Reentrant to in case f completes so fast that done callbacks are executed
    # immediately while lock is still held
    lock = RLock()
    # Deep-copy because we're going to remove completed work from the graph.
    graph = copy.deepcopy(graph)

    def remove_completed_work(done_work: Work):
        nonlocal all_done
        nonlocal graph
        nonlocal lock
        with lock:
            for deps in graph.values():
                if done_work in deps:
                    deps.remove(done_work)
            if len(graph) == 0:
                all_done.set()

    def queue_next_work():
        nonlocal executor
        # nonlocal futures
        nonlocal graph
        nonlocal lock
        with lock:
            scheduled: list[Work] = []
            for work, deps in graph.items():
                if len(deps) == 0:
                    f = executor.submit(work)
                    # https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
                    f.add_done_callback(
                        lambda _, work=work: remove_completed_work(work)
                    )
                    f.add_done_callback(lambda _: queue_next_work())
                    scheduled.append(work)
            for work in scheduled:
                # Prevent work getting scheduled multiple times
                del graph[work]

    queue_next_work()
    all_done.wait()


def graph_to_dot(graph: WorkGraph):

    def make_str(work: Work):
        return str(work).replace('"', r"\"")

    output = ["digraph work_graph {"]
    for node in graph.keys():
        output.append(f'  "{make_str(node)}";')
    for node, deps in graph.items():
        for dep in deps:
            output.append(f'  "{make_str(node)}" -> "{make_str(dep)}";')
    output.append("}")
    return "\n".join(output)


class ExecuteCommand(Work):

    def __init__(self, cmd: list[str], working_directory: Optional[Path] = None):
        super().__init__()
        self.__cmd = cmd
        if working_directory is None:
            working_directory = Path.cwd()
        self.__working_directory = working_directory

    def __str__(self):
        return shlex.join(self.__cmd)

    def __call__(self):
        subprocess.check_call(self.__cmd, cwd=self.__working_directory)


class Retry(Work):

    def __init__(
        self,
        work: Work,
        attempts=5,
        exponent=2,
        multiplier=15,
        constant=5,
        exceptions=(subprocess.CalledProcessError,),
    ):
        super().__init__()
        self.__work = work
        self.__attempts = attempts
        self.__exponent = exponent
        self.__multiplier = multiplier
        self.__constant = constant
        self.__exceptions = exceptions

    def __str__(self):
        return f"Retry(attempts={self.__attempts}): {str(self.__work)}"

    def __call__(self):
        for i in range(self.__attempts):
            try:
                self.__work()
            except self.__exceptions as e:
                if i + 1 >= self.__attempts:
                    # This was our last attempt
                    raise e
                seconds_to_wait = (
                    self.__multiplier * pow(i, self.__exponent) + self.__constant
                )
                sys.stderr.write(
                    f"Caught exception {e}; retrying in {seconds_to_wait} seconds\n"
                )
                time.sleep(seconds_to_wait)
                # Retry
                continue
            # Success
            break
