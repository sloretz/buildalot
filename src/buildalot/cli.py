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

from .config import Template
from .config import temporary_parse_config


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arg", nargs=1)
    parser.add_argument("--config", nargs="+")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    # parser.add_argument("--skip-if-exists", action="store_true")
    parser.add_argument("--one-arch", action="store_true")
    parser.add_argument("thing_to_build")

    args = parser.parse_args()
    return args


def main():
    args = parse_arguments()
    print("Hello world" + repr(args))

    config = temporary_parse_config()
    print(config.parameters())

    ros_core = config.top_level_stuff[0]
    ros_base = config.top_level_stuff[1]
    print(ros_core.has_exact_match("ros-core"))
    print(ros_base.has_exact_match("ros_core"))
    print(config.graph)
    print(config.build_order)
    # I'm not sure about exact replacements, because how do I know if something has exact replacements
    # without trying to evaluate it?
