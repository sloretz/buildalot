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
from .config import Template
from .config import temporary_parse_config
from .config import ImageTemplate
from .config import GroupTemplate


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument("--config", nargs=1, default=["buildalot.yaml"])
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    # parser.add_argument("--skip-if-exists", action="store_true")
    parser.add_argument("--one-arch", action="store_true")
    # parser.add_argument("--cli-args-override", action="store_true")
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


def consolidate_args(cli_args, group_args, allow_override):
    fail = False
    for cli_name in cli_args.keys():
        if cli_name in group_args and not allow_override:
            fail = True
            sys.stderr.write(
                f"--arg {cli_name} is specified by both the command line and group, but --cli-args-overrides was not given\n"
            )
    if fail:
        sys.exit(-1)
    args = {}
    args.update(cli_args)
    args.update(group_args)
    return args


def main():
    args = parse_arguments()

    config = temporary_parse_config()
    relevant_config = config.partial_config([args.thing_to_build])
    need_args = relevant_config.parameters()
    have_cli_build_args = parse_cli_build_args(need_args, args)

    cli_binding = BindSource(
        source_name="__command_line__",
        architectures=None,  # TODO architectures from CLI?
        arguments=have_cli_build_args,
    )

    print(relevant_config)
    print("-----------------")
    bound_config = relevant_config.bind(cli_binding)
    print(repr(bound_config))
    print("-----------------")
    print(bound_config)
    print(bound_config.build_order)
    print(bound_config.dependencies_of("desktop"))

    # Now that I have the bound config (sort of, I wish it was a graph)
    # It's time to break down the work into OCI images and manifests to build
    # Sort of seems like "Group" should disappear after binding.
    # Like, args have been applied to images, maybe architectures should be applied too.
