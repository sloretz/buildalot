# Copyright 2024 Shane Loretz.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import re
import sys

from .config import BindSource
from .config import temporary_parse_config
from . import oci
from . import buildah
from . import work


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument("--config", nargs=1, default=["buildalot.yaml"])
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--native-arch-only", action="store_true")
    parser.add_argument("thing_to_build")

    args = parser.parse_args()
    return args


def parse_cli_build_args(need_args, args):
    """Exit with helpful CLI message unless all required args are given."""
    have_build_args = []
    arg_regex = re.compile(r"^([a-zA-Z0-9-_]+)=(.*)$")
    for argvalue in args.arg:
        m = arg_regex.match(argvalue)
        if m is None:
            sys.stderr.write("Invalid --arg format '{argvalue}'\n")
            sys.exit(-1)
        given_build_arg = m.group(1)
        given_build_value = m.group(2)
        if given_build_arg not in need_args:
            sys.stderr.write(
                f"Given unnecessary --arg {given_build_arg}={given_build_value}\n"
            )
            sys.exit(-1)
        have_build_args.append((given_build_arg, given_build_value))

    return have_build_args


def check_have_all_args(have_args, need_args):
    fail = False
    for arg in need_args:
        if arg not in have_args:
            fail = True
            sys.stderr.write(f"Config needs --arg {arg}=??? to be specified\n")
    if fail:
        sys.exit(-1)


def main():
    args = parse_arguments()

    config = temporary_parse_config()
    relevant_config = config.partial_config([args.thing_to_build])
    need_args = relevant_config.parameters()
    have_cli_build_args = parse_cli_build_args(need_args, args)

    cli_binding = BindSource(
        source_name="__command_line__",
        architectures=[] if args.native_arch_only else None,
        arguments=have_cli_build_args,
    )

    print(relevant_config)
    print("-----------------")
    bound_config = relevant_config.bind(cli_binding)
    print(repr(bound_config))
    print("-----------------")
    print(bound_config)
    print("-----------------")
    oci_graph = oci.build_graph(bound_config)
    print(oci.graph_to_dot(oci_graph))
    print("-----------------")
    work_graph = buildah.build_graph(oci_graph)
    print(work.graph_to_dot(work_graph))
    work.execute(work_graph)

    # Now that I have the OCI graph, it's time to turn it into buildah commands
    # Some sort of buildah.build_graph(oci_graph) to produce
    # a graph of work to execute.
    # I can print that dot graph again for debugging (nodes are commands to run?)
    # Then I can pass that to some sort of concurrent.futures executor!
