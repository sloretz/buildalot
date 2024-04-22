import collections
import graphlib
import re

import yaml


class ParseError(RuntimeError):

    def __init__(self, msg):
        super().__init__(msg)


def parse_config(stream):
    """Parse a config describing images to build.
    Return a list of all top level groups."""
    yaml_dict = yaml.safe_load(stream)

    top_level = []

    for key, item in yaml_dict.items():
        if not isinstance(item, collections.Mapping):
            raise ParseError(f"Top level key '{key}' must be a dictionary")

    if "build" in item.keys():
        # Image template
        top_level.append(ImageTemplate.ParseFrom(item))
    elif "images" in item.keys():
        # Group
        top_level.append(GroupTemplate.ParseFrom(item))


class Config:

    def __init__(self, top_level_stuff):
        # All top-level things, unsorted at this point
        self.top_level_stuff = top_level_stuff

        # Add all the nodes to the graph
        self.graph = {}
        for thing in top_level_stuff:
            self.graph[thing.id] = set()
        for thing in top_level_stuff:
            for other in top_level_stuff:
                if other.has_exact_match(thing.id):
                    # Found an edge! Other thing needs this thing
                    self.graph[other.id].add(thing.id)

        ts = graphlib.TopologicalSorter(self.graph)
        self.build_order = tuple(ts.static_order())

    def parameters(self):
        params = set()
        for thing in self.top_level_stuff:
            params.update(thing.parameters)
        return sorted(tuple(params))


def temporary_parse_config():
    """Placeholder before I write the parsing code."""
    top_level = []
    top_level.append(
        ImageTemplate(
            id="ros_core",
            name="ros",
            tag="${rosdistro}-ros-core",
            build_context="ros2/ros-core",
            build_args={"FROM": "${ubuntu_image}"},
        )
    )
    top_level.append(
        ImageTemplate(
            id="ros_base",
            name="ros",
            tag="${rosdistro}-ros-base",
            build_context="ros2/ros-base",
            build_args={"FROM": "ros_core"},
        )
    )
    top_level.append(
        ImageTemplate(
            id="perception",
            name="ros",
            tag="${rosdistro}-perception",
            build_context="ros2/perception",
            build_args={"FROM": "ros_base"},
        )
    )
    top_level.append(
        ImageTemplate(
            id="simulation",
            name="ros",
            tag="${rosdistro}-simulation",
            build_context="ros2/simulation",
            build_args={"FROM": "ros_base"},
        )
    )
    top_level.append(
        ImageTemplate(
            id="desktop",
            name="ros",
            tag="${rosdistro}-desktop",
            build_context="ros2/desktop",
            build_args={"FROM": "ros_base"},
        )
    )
    top_level.append(
        ImageTemplate(
            id="desktop_full",
            name="ros",
            tag="${rosdistro}-desktop-full",
            build_context="ros2/desktop-full",
            build_args={"FROM": "desktop"},
        )
    )
    top_level.append(
        GroupTemplate(
            id="humble",
            images=[
                "ros_core",
                "ros_base",
                "desktop",
                "perception",
                "simulation",
                "desktop_full",
            ],
            architectures=["amd64", ["arm64", "v8"]],
            args={"rosdistro": "humble", "ubuntu_image": "ubuntu:jammy"},
        )
    )
    top_level.append(
        GroupTemplate(
            id="iron",
            images=[
                "ros_core",
                "ros_base",
                "desktop",
                "perception",
                "simulation",
                "desktop_full",
            ],
            architectures=["amd64", ["arm64", "v8"]],
            args={"rosdistro": "iron", "ubuntu_image": "ubuntu:jammy"},
        )
    )
    top_level.append(
        GroupTemplate(
            id="rolling",
            images=[
                "ros_core",
                "ros_base",
                "desktop",
                "perception",
                # "simulation",
                # "desktop_full",
            ],
            architectures=["amd64", ["arm64", "v8"]],
            args={"rosdistro": "rolling", "ubuntu_image": "ubuntu:jammy"},
        )
    )
    return Config(top_level)


class Template:

    param_regex = re.compile(r"\${\s*([a-zA-Z0-9-_]+)\s*}")

    def __init__(self, parameters):
        self.parameters = tuple(parameters)

    def evaluate(self, parameters, exact_match_replacements):
        """Evaluate template where all parameters are expanded
        by the given dictionary and values, and all strings
        EXACTLY matching something in exact_match_replacements
        are also replaced."""
        raise NotImplementedError

    def has_exact_match(self, exact_match):
        sentinel_value = "__sloretz_was_here__"
        assert exact_match != sentinel_value
        evaluated = self.evaluate({}, {exact_match: sentinel_value})
        return not self == evaluated

    def __eq__(self, other):
        # print("---equality check---")
        # print(str(self))
        # print("--------------------")
        # print(str(other))
        # print("---end ---- check---")
        # result = str(self) == str(other)
        # print("Result", result)
        return str(self) == str(other)

    @classmethod
    def _extract_parameters(cls, text):
        """Returns a list of parameters that could be used to modify text."""
        return tuple(cls.param_regex.findall(text))

    @classmethod
    def _substitute_parameter(cls, text, param_name, value):
        sub_regex = r"\${\s*" + param_name + r"\s*}"
        return re.sub(sub_regex, str(value), text)

    @classmethod
    def _substitute_parameters(cls, text, parameters, exact_match_replacements=None):
        if exact_match_replacements:
            if text in exact_match_replacements:
                return exact_match_replacements[text]
        for name, value in parameters.items():
            text = cls._substitute_parameter(text, name, value)
        return text


class ImageTemplate(Template):
    """Represents a templated image definition to be built."""

    def __init__(
        self,
        id,
        *,
        name=None,
        registry=None,
        tag=None,
        build_context=None,
        build_args=None,
    ):
        if name is None:
            name = "${name}"
        if registry is None:
            registry = "${registry}"
        if tag is None:
            tag = "${tag}"
        if build_context is None:
            raise ParseError(f"Key {id} is missing required build: context:")
        if build_args is None:
            build_args = {}

        self.id = id
        self.name = name
        self.registry = registry
        self.tag = tag
        self.build_context = build_context
        self.build_args = tuple(build_args.items())

        parameters = []
        parameters.extend(self._extract_parameters(self.name))
        parameters.extend(self._extract_parameters(self.registry))
        parameters.extend(self._extract_parameters(self.tag))
        parameters.extend(self._extract_parameters(self.build_context))
        for name, value in self.build_args:
            parameters.extend(self._extract_parameters(name))
            parameters.extend(self._extract_parameters(value))

        super().__init__(parameters)

    def evaluate(self, parameters, exact_match_replacements):
        """Returns ImageTemplate with all parameters and exact_match_replacements expanded."""
        substituted_args = {}
        for name, value in self.build_args:
            name = self._substitute_parameters(
                name, parameters, exact_match_replacements
            )
            value = self._substitute_parameters(
                value, parameters, exact_match_replacements
            )
            substituted_args[name] = value
        return ImageTemplate(
            self.id,  # No funny business in the ID field
            name=self._substitute_parameters(
                self.name, parameters, exact_match_replacements
            ),
            registry=self._substitute_parameters(
                self.registry, parameters, exact_match_replacements
            ),
            tag=self._substitute_parameters(
                self.tag, parameters, exact_match_replacements
            ),
            build_context=self._substitute_parameters(
                self.build_context, parameters, exact_match_replacements
            ),
            build_args=substituted_args,
        )

    def __str__(self):
        yaml_dict = {}
        yaml_dict["registry"] = self.registry
        yaml_dict["name"] = self.name
        yaml_dict["tag"] = self.tag
        build_dict = {"context": self.build_context}
        if self.build_args:
            build_dict["args"] = dict(self.build_args)
        yaml_dict["build"] = build_dict
        return yaml.dump({self.id: yaml_dict})

    @classmethod
    def ParseFrom(cls, yaml_dict):
        """Given a parsed yaml dictionary, returns an ImageTemplate instance
        if the yaml dictionary is a valid template for one, else raises."""
        raise NotImplementedError


class GroupTemplate(Template):
    """Represents a templated group of images."""

    def __init__(self, id, *, images=None, architectures=None, args=None):

        if not images:
            raise ParseError(f"Key {id} must have at least one image specified")

        self.id = id
        self.images = tuple(images)

        self.architectures = []
        for arch in architectures:
            if isinstance(arch, str):
                # Arch without variant specified
                self.architectures.append((arch, None))
            elif len(arch) == 2:
                # Arch and variant specified
                self.architectures.append(tuple(arch))
            else:
                raise ParseError(f"Key {id} has invalid architecture {arch}")
        self.args = tuple(args.items())

        parameters = []
        for image in self.images:
            parameters.extend(self._extract_parameters(image))
        for arch in self.architectures:
            parameters.extend(self._extract_parameters(arch[0]))
            if arch[1]:
                parameters.extend(self._extract_parameters(arch[1]))
        for name, value in self.args:
            parameters.extend(self._extract_parameters(name))
            parameters.extend(self._extract_parameters(value))
        super().__init__(parameters)

    @classmethod
    def ParseFrom(cls, yaml_dict):
        """Given a parsed yaml dictionary, returns an ImageTemplate instance
        if the yaml dictionary is a valid template for one, else raises."""
        raise NotImplementedError

    def evaluate(self, parameters, exact_match_replacements):
        return self  # TODO implement this!
    
    def __str__(self):
        yaml_dict = {}
        yaml_dict["images"] = list(self.images)
        arch_list = []
        for arch, variant in self.architectures:
            if variant is None:
                arch_list.append(arch)
            else:
                arch_list.append([arch, variant])
        yaml_dict["architectures"] = arch_list
        yaml_dict["args"] = dict(self.args)
        return yaml.dump({self.id: yaml_dict})
