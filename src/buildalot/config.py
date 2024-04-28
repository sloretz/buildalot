import collections
import copy
import graphlib
import re
from typing import Optional

import yaml


PARAM_REGEX = re.compile(r"\${\s*([a-zA-Z0-9-_]+)\s*}")


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
            return self._identifier
        else:
            return self._resolved_id

    def __repr__(self):
        return f"<IdResolver:{self._identifier}>"

    def __deepcopy__(self, el):
        raise RuntimeError("IdResolver must not be copied!")

    def __copy__(self):
        raise RuntimeError("IdResolver must not be copied!")


class BoundValue:

    def __init__(self, source_name, value):
        self.__source_name = source_name
        self.__value = value

    @property
    def source_name(self):
        return self.__source_name

    @property
    def value(self):
        return self.__value

    def __eq__(self, other):
        return self.__value == other

    def __str__(self):
        return str(self.__value)

    def __repr__(self):
        return f'<BoundValue(source_name="{self.source_name}", value="{self.value}">'


class BindSource:
    """Architectures and arguments that get bound to Image."""

    def __init__(
        self,
        *,
        source_name: str,
        architectures: Optional[list[tuple[str, Optional[str]]]],
        arguments: list[tuple[str, str]],
    ):
        self.__source_name = source_name
        self.__architectures = None if architectures is None else tuple(architectures)
        self.__arguments = tuple(arguments)

    @property
    def source_name(self):
        return self.__source_name

    @property
    def architectures(self):
        return self.__architectures

    @property
    def arguments(self):
        return self.__arguments


class BindChain:

    def __init__(self, *links):
        self._links = [l for l in links]

    def add_child_source(self, binding: BindSource):
        self._links.append(binding)

    @property
    def architectures(self):
        """Return architectures to build for a multiarch image, or None if only native arch should be used."""
        # First to specify architectures wins
        for binding in self._links:
            if binding.architectures is not None:
                value = []
                for arch, variant in binding.architectures:
                    value.append(
                        (
                            BoundValue(source_name=binding.source_name, value=arch),
                            BoundValue(source_name=binding.source_name, value=variant),
                        )
                    )
                return tuple(value)

    def argument_value(self, name):
        """Return value of arghument."""
        # First to specify argument wins
        for binding in self._links:
            for arg_name, value in binding.arguments:
                if arg_name == name:
                    return BoundValue(source_name=binding.source_name, value=value)
        sources = [l.source_name for l in self._links]
        raise ValueError(f'Argument "{name}" was not provided by: {sources}')


class BoundFormatString(BoundValue):

    @classmethod
    def FromStringAndChain(cls, string: str, bind_chain: BindChain):
        values = {}
        format_string = string
        for arg_name in PARAM_REGEX.findall(string):
            values[arg_name] = bind_chain.argument_value(arg_name)
            sub_regex = r"\${\s*" + arg_name + r"\s*}"
            format_string = re.sub(sub_regex, "{" + arg_name + "}", format_string)
        if values:
            return cls(format_string, values)
        # No values to format, return string unmodified
        return string

    @property
    def value(self):
        return str(self)

    def __init__(self, format_string: str, values: dict[str, BoundValue]):
        self.__format_string = format_string
        self.__values = values

    def __str__(self) -> str:
        str_values = {}
        for arg_name, arg_value in self.__values.items():
            str_values[arg_name] = str(arg_value)
        return self.__format_string.format(**str_values)

    def __repr__(self) -> str:
        repr_values = {}
        for arg_name, arg_value in self.__values.items():
            repr_values[arg_name] = repr(arg_value)
        return (
            "<BoundFormatString:"
            + repr(self.__format_string.format(**repr_values))
            + ">"
        )

    def __eq__(self, other):
        return str(self) == other


class Config:

    def __init__(self, images_and_groups):
        # All top-level things, unsorted at this point
        self.images = [i for i in images_and_groups if isinstance(i, ImageTemplate)]
        self.groups = [g for g in images_and_groups if isinstance(g, GroupTemplate)]
        self.id_resolvers = {}

        # Add all the nodes to the graph
        self.graph = {}
        for image_or_group in images_and_groups:
            self.graph[image_or_group.id] = set()
        for image_or_group in images_and_groups:
            for other in images_and_groups:
                if other.uses_id(image_or_group.id):
                    # Found an edge! Other thing needs this thing
                    self.graph[other.id].add(image_or_group.id)

        # Create IdResolvers for images
        for image in self.images:
            self.id_resolvers[image.id] = IdResolver(image.id)

        # Inject IdResolvers for images (groups can't depend on groups...yet)
        for image in self.images:
            for dep_id in self.graph[image.id]:
                image.inject_resolver(self.id_resolvers[dep_id])

        ts = graphlib.TopologicalSorter(self.graph)
        self.build_order = tuple(ts.static_order())

    def __str__(self):
        return "\n".join([str(i) for i in self.images] + [str(g) for g in self.groups])

    def parameters(self):
        params = set()
        for thing in self.images + self.groups:
            params.update(thing.parameters)
        return sorted(tuple(params))

    def get_top_level(self, top_level_id):
        for image in self.images + self.groups:
            if image.id == top_level_id:
                return image

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
            image_or_group = self.get_top_level(want_id)
            if image_or_group is not None:
                partial_top_level.append(image_or_group)

        return Config(partial_top_level)

    def bind(self, bind_source: BindSource):
        # Assert that there is only one group because I don't need
        # nor have the time to make it possible to build multiple top
        # level groups right now
        if len(self.groups) > 1:
            raise NotImplementedError

        bind_chain = BindChain(bind_source)

        if self.groups:
            # Assume all images are bound by the group
            group: GroupTemplate = self.groups[0]
            bind_chain.add_child_source(group.bind(bind_chain))

        # List of BoundImage
        bound_images = []
        for thing_id in reversed(self.build_order):
            for image in self.images:
                if thing_id == image.id:
                    bound_images.append(image.bind(bind_chain))

        for image in bound_images:
            id_resolver = self.id_resolvers[image.id]
            id_resolver.resolve(image.fully_qualified_name)

        image_graph = {}
        for image in bound_images:
            image_graph[image.id] = tuple(self.graph[image.id])

        return BoundConfig(image_graph, bound_images)


class BoundConfig:

    def __init__(self, graph, bound_images):
        ts = graphlib.TopologicalSorter(graph)
        self.__graph = copy.deepcopy(graph)
        self.__build_order = tuple(ts.static_order())
        self.__bound_images = [b for b in bound_images]

    @property
    def build_order(self):
        return tuple(self.__build_order)

    def dependencies_of(self, image_id):
        return tuple(self.__graph[image_id])

    def get_image(self, image_id):
        for image in self.__bound_images:
            if image.id == image_id:
                return image

    def __str__(self):
        return "\n".join([str(image) for image in self.__bound_images])

    def __repr__(self):
        return "\n".join([repr(image) for image in self.__bound_images])


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

    def __init__(self, parameters):
        self.parameters = tuple(parameters)

    def __eq__(self, other):
        return str(self) == str(other)

    @classmethod
    def _extract_parameters(cls, text):
        """Returns a list of parameters that could be used to modify text."""
        return tuple(PARAM_REGEX.findall(text))


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
            raise ParseError(f"Image {id} is missing required build: context:")
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
        if self.id == exact_id:
            return False
        for _, value in self.build_args:
            if value == exact_id:
                return True
            elif isinstance(value, IdResolver) and value.identifier == exact_id:
                return True
        return False

    def inject_resolver(self, id_resolver: IdResolver):
        if self.id == id_resolver.identifier:
            return
        injected_args = []
        for name, value in self.build_args:
            if value == id_resolver.identifier:
                # new never-been-resolved ID
                value = id_resolver
            elif (
                isinstance(value, IdResolver)
                and value.identifier == id_resolver.identifier
            ):
                # Already resolved, replace existing resolver
                value = id_resolver
            injected_args.append((name, value))
        self.build_args = injected_args

    def bind(self, bind_chain: BindChain):
        """Returns BoundImage with all parameters and exact_id_replacements expanded."""
        substituted_args = []
        for name, value in self.build_args:
            name = BoundFormatString.FromStringAndChain(name, bind_chain)
            if isinstance(value, str):
                value = BoundFormatString.FromStringAndChain(value, bind_chain)
            else:
                assert isinstance(value, IdResolver)
            substituted_args.append((name, value))
        return BoundImage(
            id=self.id,  # No funny business in the ID field
            registry=BoundFormatString.FromStringAndChain(self.registry, bind_chain),
            name=BoundFormatString.FromStringAndChain(self.name, bind_chain),
            tag=BoundFormatString.FromStringAndChain(self.tag, bind_chain),
            build_context=BoundFormatString.FromStringAndChain(
                self.build_context, bind_chain
            ),
            build_architectures=bind_chain.architectures,
            build_args=substituted_args,
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
        return yaml.dump({self.id: yaml_dict}, width=float("inf"))

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
        build_architectures,
        build_args,
    ):
        self.__id = id
        self.__registry = registry
        self.__name = name
        self.__tag = tag
        self.__build_context = build_context
        self.__build_architectures = build_architectures
        self.__build_args = [(n, v) for n, v in build_args]

    @property
    def fully_qualified_name(self) -> str:
        registry = str(self.__registry).rstrip("/")
        name = str(self.__name)
        tag = str(self.__tag)
        return f"{registry}/{name}:{tag}"

    @property
    def id(self) -> str:
        return self.__id

    @property
    def registry(self) -> str:
        return str(self.__registry)

    @property
    def name(self) -> str:
        return str(self.__name)

    @property
    def tag(self) -> str:
        return str(self.__tag)

    @property
    def build_context(self):
        return str(self.__build_context)

    @property
    def build_architectures(self):
        arches = self.__build_architectures
        if isinstance(arches, BoundValue):
            arches = [(a, v) for a, v in arches.value]
        for a, v in arches:
            if isinstance(a, BoundValue):
                a = a.value
            if isinstance(v, BoundValue):
                v = v.value
            yield (a, v)

    @property
    def build_args(self):
        build_args = []
        for key, value in self.__build_args:
            if isinstance(key, BoundValue):
                key = key.value
            if isinstance(value, BoundValue):
                value = value.value
            build_args.append((key, value))
        return build_args

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
                build_dict["args"][str(name)] = str(value)
        arches = []
        for a, v in self.build_architectures:
            if v is None:
                arches.append(a)
            else:
                arches.append([a, v])
        if arches:
            build_dict["architectures"] = arches

        yaml_dict["build"] = build_dict
        return yaml.dump({self.id: yaml_dict}, width=float("inf"))

    def __repr__(self):

        def maybe_repr(value):
            if isinstance(value, str):
                return value
            return repr(value)

        yaml_dict = {}
        yaml_dict["registry"] = maybe_repr(self.__registry)
        yaml_dict["name"] = maybe_repr(self.__name)
        yaml_dict["tag"] = maybe_repr(self.__tag)
        build_dict = {"context": maybe_repr(self.__build_context)}
        if self.build_args:
            build_dict["args"] = {}
            for name, value in self.__build_args:
                build_dict["args"][maybe_repr(name)] = maybe_repr(value)
        arches = []
        for a, v in self.__build_architectures:
            if v is None:
                arches.append(maybe_repr(a))
            else:
                arches.append([maybe_repr(a), maybe_repr(v)])
        if arches:
            build_dict["architectures"] = arches
        yaml_dict["build"] = build_dict
        return yaml.dump({self.id: yaml_dict}, width=float("inf"))


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

    def bind(self, bind_chain: BindChain) -> BindSource:
        """Returns a new Binding chained from the given binding."""
        substituted_architectures = []
        for arch, variant in self.architectures:
            arch = BoundFormatString.FromStringAndChain(arch, bind_chain)
            if variant:
                variant = BoundFormatString.FromStringAndChain(variant, bind_chain)
            substituted_architectures.append((arch, variant))
        substituted_args = []
        for name, value in self.args:
            name = BoundFormatString.FromStringAndChain(name, bind_chain)
            value = BoundFormatString.FromStringAndChain(value, bind_chain)
            substituted_args.append((name, value))
        return BindSource(
            source_name=self.id,
            architectures=substituted_architectures,
            arguments=substituted_args,
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
        return yaml.dump({self.id: yaml_dict}, width=float("inf"))
