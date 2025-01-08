from buildalot.config import Config
from buildalot.config import Exclusion


_single_image = """
ros_core:
  name: "ros"
  tag: "${rosdistro}-ros-core"
  build:
    context: "ros2/ros-core"
    args:
      FROM: "${ubuntu_image}"
"""


def test_single_image():
    config = Config.parse_string(_single_image)
    assert set(config.parameters()) == set(["registry", "rosdistro", "ubuntu_image"])
    assert config.get_top_level("ros_core").id == "ros_core"


_image_and_group = """
ros_core:
  name: "ros"
  tag: "${rosdistro}-ros-core"
  build:
    context: "ros2/ros-core"
    args:
      FROM: "${ubuntu_image}"
humble:
  images:
    - ros_core
  architectures:
    - "amd64"
    - ["arm64", "v8"]
  parameters:
    rosdistro: "humble"
    ubuntu_image: "ubuntu:jammy"
"""


def test_image_and_group():
    config = Config.parse_string(_image_and_group)
    # Goup specifies ubuntu_image and rosdistro,but config allows CLI to override them
    assert set(config.parameters()) == set(["registry", "ubuntu_image", "rosdistro"])
    image = config.get_top_level("ros_core")
    assert image.id == "ros_core"

    group = config.get_top_level("humble")
    assert group.id == "humble"
    assert ("rosdistro", "humble") in group.provides_parameters


_minimum_image = """
some_image:
  build:
    context: "${some_path}"
"""


def test_minimum_image():
    config = Config.parse_string(_minimum_image)
    assert set(config.parameters()) == set(["registry", "name", "tag", "some_path"])
    assert config.get_top_level("some_image").id == "some_image"


_minimum_image_and_group = """
some_image:
  build:
    context: "${some_path}"
some_group:
  images:
    - some_image
"""


def test_minimum_image_and_group():
    config = Config.parse_string(_minimum_image_and_group)
    assert set(config.parameters()) == set(["registry", "name", "tag", "some_path"])
    assert config.get_top_level("some_image").id == "some_image"
    assert config.get_top_level("some_group").id == "some_group"


_image_and_group_with_exclusion = """
ros_core:
  name: "ros"
  tag: "ros-core"
  build:
    context: "ros2/ros-core"
    args:
      FROM: "ubuntu:jammy"
humble:
  images:
    - ros_core
  architectures:
    - "amd64"
    - ["arm64", "v8"]
  exclude:
    - architecture: "amd64"
      images:
        - ros_core
jazzy:
  images:
    - ros_core
  architectures:
    - "amd64"
    - ["arm64", "v8"]
  exclude:
    - architecture: ["arm64", "v8"]
      images:
        - ros_core
"""


def test_image_and_group_with_exclusion():
    config = Config.parse_string(_image_and_group_with_exclusion)
    image = config.get_top_level("ros_core")
    assert image.id == "ros_core"

    humble = config.get_top_level("humble")
    assert humble.exclusions == tuple([Exclusion(image_id="ros_core", arch="amd64")])
    jazzy = config.get_top_level("jazzy")
    assert jazzy.exclusions == tuple(
        [Exclusion(image_id="ros_core", arch="arm64", variant="v8")]
    )
