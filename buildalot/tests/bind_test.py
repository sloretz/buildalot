from buildalot.config import BindChain
from buildalot.config import BindSource
from buildalot.config import Exclusion


def test_source_with_exclusions():
    bs = BindSource(
        source_name="foobar",
        architectures=[("amd64", None), ("arm", "v7"), ("arm64", "v8")],
        arguments=[],
        exclusions=[Exclusion(image_id="no_amd_image", arch="amd64")],
    )

    bc = BindChain(bs)

    assert ("amd64", None) in bc.architectures_for_image("any_other_image")
    assert len(bc.architectures_for_image("any_other_image")) == 3
    assert not ("amd64", None) in bc.architectures_for_image("no_amd_image")
    assert len(bc.architectures_for_image("no_amd_image")) == 2
