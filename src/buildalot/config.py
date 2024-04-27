import collections
import copy
import graphlib
import re
from typing import Optional

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


class CliArgWouldOverrideError(RuntimeError):

    def __init__(self, problem_args):
        self.problem_args = problem_args
        super(
            f"CLI arguments {problem_args} would override Group arguments, but overriding was not allowed"
        )


class IdResolver:

    def __init__(self, identifier: str):
        self._identifier = identifier
        self._resolved_id: Optional[str] = None

    @property
    def identifier(self):
        return self._identifier

    def resolve(self, resolved_id: str):
        if self._resolved_id is not None:
            raise RuntimeError("cannot resolve id twice")
        self._resolved_id = resolved_id

    def __str__(self):
        if self._resolved_id is None:
            return f'IdResolver("{self._identifier}"){hex(id(self))}'
        else:
            return self._resolved_id
        
    def __deepcopy__(self,el):
        raise RuntimeError('IdResolver must not be copied!')

    def __copy__(self):
        raise RuntimeError('IdResolver must not be copied!')


class Config:

    def __init__(self, images_and_groups):
        # All top-level things, unsorted at this point
        self.images_and_groups = images_and_groups

        # Add all the nodes to the graph
        self.graph = {}
        for thing in images_and_groups:
            self.graph[thing.id] = set()
        for thing in images_and_groups:
            for other in images_and_groups:
                if other.uses_id(thing.id):
                    # Found an edge! Other thing needs this thing
                    self.graph[other.id].add(thing.id)

        ts = graphlib.TopologicalSorter(self.graph)
        self.build_order = tuple(ts.static_order())

    def parameters(self):
        params = set()
        for thing in self.images_and_groups:
            params.update(thing.parameters)
        return sorted(tuple(params))

    def get_top_level(self, top_level_id):
        for thing in self.images_and_groups:
            if thing.id == top_level_id:
                return thing

    def _get_all_dependencies(self, thing_id):
        """Return set of ids of all dependencies of the given id"""
        dependencies = set()
        for dep_id in self.graph[thing_id]:
            dependencies.add(dep_id)
            dependencies.update(self._get_all_dependencies(dep_id))
        return dependencies

    def partial_config(self, want_top_level_ids):
        """Return a config with just the wanted top level items."""
        # Partial config must include all transitive dependencies
        transitive_ids = set(want_top_level_ids)
        for want_id in want_top_level_ids:
            if want_id not in self.graph:
                raise IndexError(f"Config does not have id {want_id}")
            transitive_ids.update(self._get_all_dependencies(want_id))

        partial_top_level = []
        for want_id in transitive_ids:
            for have_item in self.images_and_groups:
                if have_item.id == want_id:
                    partial_top_level.append(have_item)
        return Config(partial_top_level)

    def _consolidate_args(self, cli_args, group_args, cli_args_override):
        args_in_both = []
        for cli_name in cli_args.keys():
            if cli_name in group_args and not cli_args_override:
                args_in_both.append(cli_name)
        if args_in_both:
            raise CliArgWouldOverrideError(args_in_both)
        args = {}
        args.update(cli_args)
        args.update(group_args)
        return args

    def bind(self, cli_args, cli_args_override=False):
        # Assert that there is only one group because I don't need
        # nor have the time to make it possible to build multiple top
        # level groups right now
        num_groups = 0
        for thing in self.build_order:
            if isinstance(thing, GroupTemplate):
                num_groups += 1
        if num_groups > 1:
            raise NotImplementedError
        if num_groups == 1 and not isinstance(self.build_order[-1], GroupTemplate):
            raise NotImplementedError

        id_resolvers = {}
        for image_or_group in self.images_and_groups:
            id_resolvers[image_or_group.id] = IdResolver(image_or_group.id)

        all_args = copy.deepcopy(cli_args)

        # Args propogate from top down, but ID needs to be resolved
        # from bottom up...
        # Could put placeholder ID while binding the first time,
        # Then go back through and update placeholders...

        # List of BoundImage or BoundGroup
        bound_image_or_groups = []
        for thing_id in reversed(self.build_order):
            thing = self.get_top_level(thing_id)
            bound_thing = thing.bind(all_args, id_resolvers)
            if isinstance(bound_thing, BoundGroup):
                # This code assumes there's only one group
                group_args = bound_thing.args
                all_args = self._consolidate_args(
                    cli_args, group_args, cli_args_override
                )
            bound_image_or_groups.append(bound_thing)

        for bound_image_or_group in bound_image_or_groups:
            if isinstance(bound_image_or_group, BoundImage):
                id_resolver = id_resolvers[bound_image_or_group.id]
                id_resolver.resolve(bound_image_or_group.fully_qualified_name)

        return BoundConfig(self.graph, self.build_order, bound_image_or_groups)


class BoundConfig:

    def __init__(self, graph, build_order, bound_items):

        self.__graph = copy.deepcopy(graph)
        self.__build_order = [i for i in build_order]
        self.__bound_items = [b for b in bound_items]

    def get_top_level(self, top_level_id):
        for thing in self.__bound_items:
            if thing.id == top_level_id:
                return thing

    def __str__(self):
        return "\n".join([str(thing) for thing in self.__bound_items])


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
    def _substitute_parameters(cls, text, parameters, exact_id_replacements=None):
        if exact_id_replacements:
            if text in exact_id_replacements:
                return exact_id_replacements[text]
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

    def uses_id(self, exact_id):
        # Allowed to use top-level ID in:
        #   * build_arg values
        if self.id == exact_id:
            return False
        for _, value in self.build_args:
            if value == exact_id:
                return True
            elif isinstance(value, IdResolver) and IdResolver.identifier == exact_id:
                return True
        return False

    def bind(self, given_args, exact_id_replacements):
        """Returns BoundImage with all parameters and exact_id_replacements expanded."""
        # Require all parameters to be bound
        for parameter in self.parameters:
            if parameter not in given_args:
                raise RuntimeError(
                    f"ImageTemplate.bind requires argument {parameter}, but it was not given"
                )
        # Forbid replacing our own ID
        if self.id in exact_id_replacements:
            exact_id_replacements = dict(exact_id_replacements.items())
            del exact_id_replacements[self.id]
        # Make a list of our own dependencies
        depends_on_ids = []
        for other_id in exact_id_replacements.keys():
            if self.uses_id(other_id):
                depends_on_ids.append(other_id)
        substituted_args = []
        for name, value in self.build_args:
            name = self._substitute_parameters(name, given_args)
            value = self._substitute_parameters(
                value, given_args, exact_id_replacements
            )
            substituted_args.append((name, value))
        return BoundImage(
            id=self.id,  # No funny business in the ID field
            registry=self._substitute_parameters(self.registry, given_args),
            name=self._substitute_parameters(self.name, given_args),
            tag=self._substitute_parameters(self.tag, given_args),
            build_context=self._substitute_parameters(self.build_context, given_args),
            build_args=substituted_args,
            depends_on_ids=depends_on_ids,
        )

    def __str__(self):
        yaml_dict = {}
        yaml_dict["registry"] = self.registry
        yaml_dict["name"] = self.name
        yaml_dict["tag"] = self.tag
        build_dict = {"context": self.build_context}
        if self.build_args:
            build_dict["args"] = {}
            for name, value in self.build_args:
                build_dict["args"][name] = str(value)

        yaml_dict["build"] = build_dict
        return yaml.dump({self.id: yaml_dict})

    @classmethod
    def ParseFrom(cls, yaml_dict):
        """Given a parsed yaml dictionary, returns an ImageTemplate instance
        if the yaml dictionary is a valid template for one, else raises."""
        raise NotImplementedError


class BoundImage:
    """
    ImageTemplate.bind produces a BoundImage by specifying
    all the arguments needed to build that image.

    At this point the BoundImage can be checked for more practical
    errors, like the build context not existing.
    """

    def __init__(
        self,
        id: str,
        *,
        registry: str,
        name: str,
        tag: str,
        build_context,
        build_args,
        depends_on_ids,
    ):
        self.__id = id
        self.__registry = registry.rstrip("/")
        self.__name = name
        self.__tag = tag
        self.__build_context = build_context
        self.__build_args = [(n, v) for n, v in build_args]
        self.__depends_on_ids = [i for i in depends_on_ids]

    @property
    def fully_qualified_name(self) -> str:
        return f"{self.__registry}/{self.__name}:{self.__tag}"

    @property
    def id(self) -> str:
        return self.__id

    @property
    def registry(self) -> str:
        return self.__registry

    @property
    def name(self) -> str:
        return self.__name

    @property
    def tag(self) -> str:
        return self.__tag

    @property
    def build_context(self):
        return self.__build_context

    @property
    def build_args(self):
        return dict(self.__build_args)

    @property
    def dependencies(self):
        return self.__depends_on_ids

    def __str__(self):
        yaml_dict = {}
        yaml_dict["registry"] = self.registry
        yaml_dict["name"] = self.name
        yaml_dict["tag"] = self.tag
        build_dict = {"context": self.build_context}
        if self.build_args:
            build_dict["args"] = {}
            for name, value in self.__build_args:
                build_dict["args"][name] = str(value)
        yaml_dict["build"] = build_dict
        return yaml.dump({self.id: yaml_dict})


class GroupTemplate(Template):
    """Represents a templated group of images."""

    def __init__(self, id, *, images=None, architectures=None, args=None):

        if not images:
            raise ParseError(f"Key {id} must have at least one image specified")

        self.id = id
        if images is None:
            images = []
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
        if args is None:
            args = {}
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

    def uses_id(self, exact_id):
        # Allowed to use top-level ID in:
        #   * images
        #   * arg values
        if self.id == exact_id:
            return False
        for image in self.images:
            if image == exact_id:
                return True
        for _, value in self.args:
            if value == exact_id:
                return True
        return False

    @classmethod
    def ParseFrom(cls, yaml_dict):
        """Given a parsed yaml dictionary, returns an ImageTemplate instance
        if the yaml dictionary is a valid template for one, else raises."""
        raise NotImplementedError

    def bind(self, given_args, exact_id_replacements):
        """Returns BoundGroup with all parameters and exact_id_replacements expanded."""
        # Require all parameters to be bound
        for parameter in self.parameters:
            if parameter not in given_args:
                raise RuntimeError(
                    f"ImageTemplate.bind requires argument {parameter}, but it was not given"
                )
        # Make a list of our own dependencies
        depends_on_ids = []
        for other_id in exact_id_replacements.keys():
            if self.uses_id(other_id):
                depends_on_ids.append(other_id)
        # Forbid replacing our own ID
        if self.id in exact_id_replacements:
            exact_id_replacements = dict(exact_id_replacements.items())
            del exact_id_replacements[self.id]
        substituted_images = []
        for image in self.images:
            substituted_images.append(
                self._substitute_parameters(image, given_args, exact_id_replacements)
            )
        substituted_architectures = []
        for arch, variant in self.architectures:
            arch = self._substitute_parameters(arch, given_args)
            if variant:
                variant = self._substitute_parameters(variant, given_args)
            substituted_architectures.append((arch, variant))
        substituted_args = []
        for name, value in self.args:
            name = self._substitute_parameters(name, given_args)
            value = self._substitute_parameters(
                value, given_args, exact_id_replacements
            )
            substituted_args.append((name, value))
        return BoundGroup(
            self.id,  # No funny business in the ID field
            images=substituted_images,
            architectures=substituted_architectures,
            args=substituted_args,
            depends_on_ids=depends_on_ids,
        )

    def __str__(self):
        yaml_dict = {}
        yaml_dict["images"] = [str(i) for i in self.images]
        arch_list = []
        for arch, variant in self.architectures:
            if variant is None:
                arch_list.append(arch)
            else:
                arch_list.append([arch, variant])
        yaml_dict["architectures"] = arch_list
        yaml_dict["args"] = dict(self.args)
        return yaml.dump({self.id: yaml_dict})


class BoundGroup:
    """
    GroupTemplate.bind produces a BoundGroup by specifying
    all the arguments needed to build that group of images.

    At this point the BoundGroup can be checked for more practical
    errors, like the build context not existing.
    """

    def __init__(
        self,
        id,
        *,
        images,
        architectures,
        args,
        depends_on_ids,
    ):
        self.__id = id
        self.__images = [i for i in images]
        self.__archiarchitectures = [(a, v) for a, v in architectures]
        self.__args = [(n, v) for n, v in args]
        self.__depends_on_ids = [d for d in depends_on_ids]

    @property
    def id(self):
        return self.__id

    @property
    def images(self):
        return self.__images

    @property
    def architectures(self):
        return self.__archiarchitectures

    @property
    def args(self):
        return dict(self.__args)

    @property
    def dependencies(self):
        return self.__depends_on_ids

    def __str__(self):
        yaml_dict = {}
        yaml_dict["images"] = [str(i) for i in self.images]
        arch_list = []
        for arch, variant in self.architectures:
            if variant is None:
                arch_list.append(arch)
            else:
                arch_list.append([arch, variant])
        yaml_dict["architectures"] = arch_list
        yaml_dict["args"] = dict(self.args)
        return yaml.dump({self.id: yaml_dict})
