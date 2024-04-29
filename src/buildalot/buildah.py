from .work import ExecuteCommand, Retry, WorkGraph
from .oci import OCIGraph


def build_graph(oci_graph: OCIGraph) -> WorkGraph:
    work_graph: WorkGraph = {}
    # TODO
    # Maybe start by building a work graph that echos stuff
    # Then I can see if it executes properly
    echo1 = ExecuteCommand(["echo", "hello world"])
    echo2 = ExecuteCommand(["echo", "My name is Bob"])
    echo3 = Retry(ExecuteCommand(["echo", "I'm Alice"]))
    echo4 = ExecuteCommand(["echo", "I'm so excited to meet you all"])

    work_graph[echo1] = []
    work_graph[echo2] = [echo1]
    work_graph[echo3] = [echo1]
    work_graph[echo4] = [echo2, echo3]

    return work_graph
