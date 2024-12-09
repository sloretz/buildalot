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
from .config import Config
from . import oci
from . import buildah
from . import work


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parameter", action="append", default=[])
    parser.add_argument("--config", default="buildalot.yaml")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--native-arch-only", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("thing_to_build")

    args = parser.parse_args()
    return args


def parse_cli_parameters(need_parameters, args):
    """Exit with helpful CLI message unless all required parameters are given."""
    have_parameters = []
    parameter_regex = re.compile(r"^([a-zA-Z0-9-_]+)=(.*)$")
    for parametervalue in args.parameter:
        m = parameter_regex.match(parametervalue)
        if m is None:
            sys.stderr.write("Invalid --parameter format '{parametervalue}'\n")
            sys.exit(-1)
        given_parameter = m.group(1)
        given_value = m.group(2)
        if given_parameter not in need_parameters:
            sys.stderr.write(
                f"Given unnecessary --parameter {given_parameter}={given_value}\n"
            )
            sys.exit(-1)
        have_parameters.append((given_parameter, given_value))

    return have_parameters


def check_have_all_parameters(have_parameters, need_parameters):
    fail = False
    for parameter in need_parameters:
        if parameter not in have_parameters:
            fail = True
            sys.stderr.write(f"Config needs --parameter {parameter}=??? to be specified\n")
    if fail:
        sys.exit(-1)


def main():
    args = parse_arguments()

    # Parse the entire config
    with open(args.config, 'r') as fin:
        config = Config.parse_stream(fin)

    # Reduce the config to just the portions that we've been asked to build
    relevant_config = config.partial_config([args.thing_to_build])
    if args.debug:
        print("-----------------")
        print("- Debug printing relevant config")
        print(relevant_config)

    # Check that all required CLI parameters have been passed
    need_parameters = relevant_config.parameters()
    have_cli_parameters = parse_cli_parameters(need_parameters, args)

    cli_binding = BindSource(
        source_name="__command_line__",
        architectures=[] if args.native_arch_only else None,
        arguments=have_cli_parameters,
    )

    # Bind the config (that is, evaluate it so all given parameters are applied)
    bound_config = relevant_config.bind(cli_binding)
    if args.debug:
        print("-----------------")
        print("- Debug printing bound config with sources")
        print(repr(bound_config))
    if args.debug:
        print("-----------------")
        print("- Debug printing bound config")
        print(bound_config)

    # Convert the bound config into a graph of OCI images and manifests to produce
    oci_graph = oci.build_graph(bound_config)
    if args.debug:
        print("-----------------")
        print("- Debug printing OCI graph")
        print(oci.graph_to_dot(oci_graph))

    # Convert the OCI graph into a graph of CLI commands to run
    work_graph = buildah.build_graph(oci_graph, push=args.push)
    if args.debug:
        print("-----------------")
        print("- Debug printing Work graph")
        print(work.graph_to_dot(work_graph))
        print("-----------------")

    # Run all the CLI commands to produce the images and manifests
    work.execute(work_graph, dry_run=args.dry_run)
