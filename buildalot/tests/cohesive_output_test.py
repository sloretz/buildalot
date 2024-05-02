from buildalot.cohesive_output import CohesiveOutput


def test_enter_exit():
    with CohesiveOutput("foobar") as co:
        pass