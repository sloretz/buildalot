import contextlib
import random

from buildalot.cohesive_output import CohesiveOutput


def test_enter_exit():
    with CohesiveOutput("foobar") as co:
        pass


def test_one_output(capsys):
    name = "foobar"
    message = "Hello world!"
    with CohesiveOutput(name) as co:
        co.write(message + "\n")
    captured = capsys.readouterr()
    stdout_lines = captured.out.split("\n")[:-1]  # -1 to remove '' from last \n
    assert stdout_lines == [
        f">>> Begin output from: {name}",
        f"{message}",
        f"<<< End output from: {name}",
    ]


def test_nested_output(capsys):
    with CohesiveOutput("co1") as co1:
        co1.write("co1: foo\n")
        with CohesiveOutput("co2") as co2:
            co2.write("co2: foo\n")
            co1.write("co1: bar\n")
            co2.write("co2: bar\n")
        co1.write("co1: baz\n")
    captured = capsys.readouterr()
    stdout_lines = captured.out.split("\n")[:-1]  # -1 to remove '' from last \n
    assert stdout_lines == [
        ">>> Begin output from: co1",
        "co1: foo",
        "co1: bar",
        "co1: baz",
        "<<< End output from: co1",
        ">>> Begin output from: co2",
        "co2: foo",
        "co2: bar",
        "<<< End output from: co2",
    ]


def test_many_outputs(capsys):
    outputs = {}
    for i in range(100):
        outputs[i] = CohesiveOutput(f"co{i}")

    with contextlib.ExitStack() as exit_stack:
        for co in outputs.values():
            exit_stack.enter_context(co)

        # Average 10 messages from each CohesiveOutput
        for m in range(len(outputs) * 10):
            i, co = random.choice(tuple(outputs.items()))
            co.write(f"co{i}: {m}\n")

    captured = capsys.readouterr()
    stdout_lines = captured.out.split("\n")[:-1]  # -1 to remove '' from last \n

    i = 0
    started = False
    for line in stdout_lines:
        co = outputs[i]
        if not started:
            assert line == f">>> Begin output from: co{i}", stdout_lines
            started = True
        elif line == f"<<< End output from: co{i}":
            started = False
            i += 1
        else:
            assert line.startswith(f"co{i}"), stdout_lines
