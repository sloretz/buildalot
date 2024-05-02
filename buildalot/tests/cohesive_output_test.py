from buildalot.cohesive_output import CohesiveOutput


def test_enter_exit():
    with CohesiveOutput("foobar") as co:
        pass

def test_writing_one_output(capsys):
    name = "foobar"
    message = "Hello world!"
    with CohesiveOutput(name) as co:
        co.write(message + "\n")
    captured = capsys.readouterr()
    stdout_lines = captured.out.split("\n")[:-1]  # -1 to remove '' from last \n
    assert stdout_lines == [
        f">>> Begin output from: {name}",
        f"{message}",
        f"<<< End output from: {name}"]