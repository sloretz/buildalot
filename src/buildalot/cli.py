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
    parser.add_argument("--allow-arg-override", action="store_true")
    parser.add_argument("stuff_to_build", nargs="+")

    args = parser.parse_args()
    return args


def get_all_required_build_args(need_args, args):
    """Exit with helpful CLI message unless all required args are given."""
    have_args = {}
    arg_regex = re.compile(r"^([a-zA-Z0-9-_]+)=(.*)$")
    for argvalue in args.arg:
        m = arg_regex.match(argvalue)
        if m is None:
            sys.stderr.write("Invalid --arg format '{argvalue}'\n")
            sys.exit(-1)
        given_arg = m.group(1)
        given_value = m.group(2)
        if given_arg not in need_args:
            sys.stderr.write(f"Given unnecessary --arg {given_arg}={given_value}\n")
            sys.exit(-1)
        have_args[given_arg] = given_value

    return have_args


"""
    # This is wrong place to check! GroupImage might provide the argument we need
    fail = False
    for arg in need_args:
        if arg not in have_args:
            fail = True
            sys.stderr.write(f"Config needs --arg {arg}=??? to be specified\n")
    if fail:
        sys.exit(-1)
"""


def consolidate_arguments(cli_args, group_args, allow_override):
    fail = False
    for cli_name in cli_args.keys():
        if cli_name in group_args and not allow_override:
            fail = True
            sys.stderr.write(
                f"--arg {cli_name} is specified by both the command line and group, but --allow-arg-override was not given\n"
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
    partial_config = config.partial_config(args.stuff_to_build)
    have_cli_args = get_all_required_build_args(partial_config.parameters(), args)

    for thing_id in args.stuff_to_build:
        thing_to_build = partial_config.get_top_level(thing_id)
        if isinstance(thing_to_build, ImageTemplate):
            # TODO try building one image
            pass
        elif isinstance(thing_to_build, GroupTemplate):
            # TODO Try building a group of images
            # Group template can provide arguments
            have_group_args = thing_to_build.specifies_args()
            final_args = consolidate_arguments(
                have_cli_args, have_group_args, args.allow_arg_override
            )
            # TODO check that we have all required arguments!
            print(final_args)

    print(partial_config.graph)
    print(partial_config.build_order)
