from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import BoundConfig, BoundImage


@dataclass(frozen=True)
class OCIImage:

    fully_qualified_name: str
    context: Path
    arguments: tuple[tuple[str, str]]
    arch: Optional[str]
    variant: Optional[str]


@dataclass(frozen=True)
class OCIManifest:

    fully_qualified_name: str
    images: tuple[str]


# OCIGraph is a dictionary where:
#  Key = OCIImage or Manifest
#  Value = set of things it depends on
type OCIGraph = dict[OCIImage | OCIManifest, set[OCIImage | OCIManifest]]


def graph_to_dot(graph: OCIGraph):
    output = ["digraph oci_graph {"]
    for node in graph.keys():
        output.append(f'  "{node.fully_qualified_name}";')
    for node, deps in graph.items():
        for dep in deps:
            output.append(
                f'  "{node.fully_qualified_name}" -> "{dep.fully_qualified_name}";'
            )
    output.append("}")
    return "\n".join(output)


def build_graph(bound_config: BoundConfig) -> OCIGraph:
    """
    Build a graph of OCI Images and Manifest that should be produced
    for the given config.

    If any image specifies which architectures to build, then the OCI
    graph will include an image for each architecture with a temporary
    tag followd by a manifest including them all.

    If an image has no architecture information, then the plan is a single
    image which has the given name.
    """

    oci_graph: OCIGraph = {}

    for image_id in bound_config.build_order:
        image: BoundImage = bound_config.get_image(image_id)
        _extend_oci_graph(oci_graph, bound_config, image)

    return oci_graph


def _extend_oci_graph(
    oci_graph: OCIGraph, bound_config: BoundConfig, image: BoundImage
) -> tuple[OCIImage]:
    for oi in oci_graph.keys():
        if image.fully_qualified_name == oi.fully_qualified_name:
            return tuple()

    # The images representing this BoundImage
    # Keep a record of it so they can be returned to be marked
    # as dependents of whoever called this method.
    oci_images: list[OCIImage] = []
    oci_manifest: Optional[OCIManifest] = None

    architectures = image.build_architectures
    if architectures is not None:
        # Make a bunch of arch specific images with temporary tags
        for arch, variant in architectures:
            # Need a temporary tag so that it can be added to a manifest
            if variant:
                tag_suffix = f"-{arch}-{variant}"
            else:
                tag_suffix = f"-{arch}"
            oci_image = OCIImage(
                fully_qualified_name=image.fully_qualified_name + tag_suffix,
                context=Path(image.build_context),
                arguments=tuple(image.build_args),
                arch=arch,
                variant=variant,
            )
            oci_graph[oci_image] = set()
            oci_images.append(oci_image)

        # One multi-arch manifest depends on all of the images
        oci_manifest = OCIManifest(
            fully_qualified_name=image.fully_qualified_name,
            images=tuple([i.fully_qualified_name for i in oci_images]),
        )
        oci_graph[oci_manifest] = set(oci_images)
    else:
        # Make a single OCI image with arch info unspecified
        oci_image = OCIImage(
            fully_qualified_name=image.fully_qualified_name,
            context=Path(image.build_context),
            arguments=tuple(image.build_args),
            arch=None,
            variant=None,
        )
        oci_images.append(oci_image)
        oci_graph[oci_image] = set()

    # Recursively add all dependents to the graph
    for dependent_id in bound_config.dependents_of(image.id):
        dependent_image: BoundImage = bound_config.get_image(dependent_id)
        dependent_oci_images = _extend_oci_graph(
            oci_graph, bound_config, dependent_image
        )
        for dependent in dependent_oci_images:
            # Make sure our dependents depend on us!
            if oci_manifest is not None:
                oci_graph[dependent].add(oci_manifest)
            else:
                oci_graph[dependent].update(oci_images)

    return oci_images
