from abc import abstractmethod, ABC
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import shlex
import subprocess
import sys
from threading import Event, Lock
import time
from typing import Callable, Optional

from .cohesive_output import CohesiveOutput


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


class WorkFailedError(Exception):

    def __init__(self):
        pass


def execute(graph: WorkGraph, max_workers=None, dry_run=False):
    """Execute the given work graph.

    This consumes the given graph and destroys it as work is completed.
    """
    # futures: list[Future] = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    all_done = Event()
    lock = Lock()

    def shutdown_on_error(f):
        nonlocal all_done
        nonlocal executor
        e = f.exception()
        if e is not None:
            sys.stderr.write(f"Failed to execute command {e}\n")
            executor.shutdown(wait=False, cancel_futures=True)
            all_done.set()

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
        future_done_callbacks: list[tuple[Future, tuple[Callable[[Future], None]]]] = []
        with lock:
            scheduled: list[Work] = []
            for work, deps in graph.items():
                if len(deps) == 0:
                    try:
                        if dry_run:
                            f = executor.submit(lambda: print(str(work)))
                        else:
                            f = executor.submit(work)
                    except RuntimeError:
                        # Executor shutding down, something went wrong
                        return
                    # https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
                    future_done_callbacks.append(
                        (
                            f,
                            (
                                shutdown_on_error,
                                lambda _, work=work: remove_completed_work(work),
                                lambda _: queue_next_work(),
                            ),
                        )
                    )
                    scheduled.append(work)
            for work in scheduled:
                # Prevent work getting scheduled multiple times
                del graph[work]

        # Must add done callbacks after iterating over graph because they could modify it
        # Must add done callbacks outside of locking because lock is not reentrant
        for future, done_callbacks in future_done_callbacks:
            for callback in done_callbacks:
                future.add_done_callback(callback)

    queue_next_work()
    all_done.wait()
    executor.shutdown()


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
        with CohesiveOutput(str(self)) as co:
            process = subprocess.Popen(
                self.__cmd,
                cwd=self.__working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            while line := process.stdout.readline().decode():
                assert line
                co.print(line)
            return_code = process.poll()
            assert return_code is not None
            if return_code != 0:
                raise WorkFailedError


class Retry(Work):

    def __init__(
        self,
        work: Work,
        attempts=5,
        exponent=2,
        multiplier=15,
        constant=5,
        exceptions=(WorkFailedError,),
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
