import graphlib

from .work import ExecuteCommand, Retry, Work, WorkGraph
from .oci import OCIGraph, OCIImage, OCIManifest


def _image_build(oci_image: OCIImage) -> Work:
    working_directory = oci_image.context
    cmd = [
        "buildah",
        "bud",
        "-t",
        oci_image.fully_qualified_name,
    ]
    for arg_name, arg_value in oci_image.arguments:
        cmd.append("--build-arg")
        cmd.append(f"{arg_name}={arg_value}")
    if oci_image.arch is not None:
        cmd.append("--arch")
        cmd.append(oci_image.arch)
        if oci_image.variant is not None:
            cmd.append("--variant")
            cmd.append(oci_image.variant)
    return Retry(ExecuteCommand(cmd, working_directory=working_directory))


def _image_push(oci_image: OCIImage) -> Work:
    cmd = [
        "buildah",
        "push",
        oci_image.fully_qualified_name,
    ]
    return Retry(ExecuteCommand(cmd))


def _manifest_create(oci_manifest: OCIManifest) -> Work:
    cmd = [
        "buildah",
        "manifest",
        "create",
        oci_manifest.fully_qualified_name,
    ]
    return ExecuteCommand(cmd)


def _manifest_add(oci_manifest: OCIManifest) -> list[Work]:
    new_work: list[Work] = []
    for image_fqn in oci_manifest.images:
        cmd = [
            "buildah",
            "manifest",
            "add",
            oci_manifest.fully_qualified_name,
            image_fqn,
        ]
        new_work.append(ExecuteCommand(cmd))
    return new_work


def _manifest_push(oci_manifest: OCIManifest) -> Work:
    cmd = [
        "buildah",
        "manifest",
        "push",
        "--all",
        oci_manifest.fully_qualified_name,
    ]
    return Retry(ExecuteCommand(cmd))


def build_graph(oci_graph: OCIGraph, push: bool = False) -> WorkGraph:
    images_to_not_push: set[str] = set()
    if push:
        # Only push an image if no manifest depends on it
        for oci_thing in oci_graph.keys():
            if isinstance(oci_thing, OCIManifest):
                for image_fqn in oci_thing.images:
                    images_to_not_push.add(image_fqn)

    ts = graphlib.TopologicalSorter(oci_graph)
    oci_order = ts.static_order()
    work_graph: WorkGraph = {}

    # Map OCI Image or OCI Manifest to top-level Work that was produced
    oci_to_work: dict[OCIImage | OCIManifest, list[Work]] = {}

    for oci_thing in oci_order:
        # Get prerequsite work for OCI Deps
        prerequisite_work: list[Work] = []
        for oci_dep in oci_graph[oci_thing]:
            assert oci_dep in oci_to_work
            prerequisite_work.extend(oci_to_work[oci_dep])

        if isinstance(oci_thing, OCIImage):
            new_work: list[Work] = []
            new_work.append(_image_build(oci_thing))
            if push and oci_thing.fully_qualified_name not in images_to_not_push:
                new_work.append(_image_push(oci_thing))
            # Image build gets the depependency on prerequisite work
            work_graph[new_work[0]] = prerequisite_work
            if len(new_work) > 1:
                # Image push depends on Image build
                work_graph[new_work[1]] = [new_work[0]]
            # Downstream depends on last piece of work be it build or push
            oci_to_work[oci_thing] = [new_work[-1]]
        elif isinstance(oci_thing, OCIManifest):
            new_work: list[Work] = []
            new_work.append(_manifest_create(oci_thing))
            new_work.extend(_manifest_add(oci_thing))
            if push:
                new_work.append(_manifest_push(oci_thing))
            # Manifest create gets the depependency on prerequisite work
            work_graph[new_work[0]] = prerequisite_work
            # Each image add depends on manifest creation
            for img_add_work in new_work[1 : -1 if push else None]:
                work_graph[img_add_work] = [new_work[0]]
            if push:
                # Push work depends on all image add work
                work_graph[new_work[-1]] = new_work[1:-1]
                # Downstream depends on manifest being pushed
                oci_to_work[oci_thing] = [new_work[-1]]
            else:
                # Downstream depends on all image additions
                oci_to_work[oci_thing] = new_work[1:]
        else:
            raise RuntimeError(
                f"OCI graph contained non-image or manifest: {oci_thing}"
            )

    return work_graph
