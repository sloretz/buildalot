
# Hmm I know I need a graph, but what structure suits my needs?
# I want to build images in order of their dependencies
# I also want to inspect the dependencies in a config file by
# outputting it using DOT format.
# This graph should both be a graph of top level things in the config
# and a graph of build actions to be performed.
# Probably a node is a thing to do, and an edge is a dependency between
# two things.


class Node:

    def __init__(self, thing):
        # thing might be an ImageTemplateInstance
        # Or thing might be a "BuildAction" instance
        self.thing = thing

class DirectedEdge:

    # An edge between two nodes
    def __init__(self, begin, end):
        pass


# Hey hey hey, can I use  the standard library graphlib here?