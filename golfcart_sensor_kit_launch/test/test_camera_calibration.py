# Copyright 2026 NEWSLab, National Taiwan University
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

"""Sanity checks on the camera intrinsics, of the kind a reader will not perform.

Every defect these look for was live in this repository and survived months of
being looked at, because a plausible-looking matrix reads as a calibration
whatever it says. See docs/roadmaps/3-indoor-a-camera-calibration.md.
"""

import itertools
from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / 'config'
CAMERAS = ['camera_left', 'camera_right', 'camera_rear']

# The three checks below all fail today, on defects phase 3A has open and which
# only a recalibration can clear. They are marked strict, so the day somebody
# fixes the intrinsics these tests start failing for passing unexpectedly, and
# whoever did the work deletes the marker. A known defect that announces its own
# repair is worth more than one recorded in a document nobody reads twice.
KNOWN_BAD = pytest.mark.xfail(
    strict=True,
    reason='phase 3A: one calibration cloned across three cameras, captured at a '
           'resolution the file does not declare, with a distortion model that '
           'contradicts its own coefficients',
)


def load(camera):
    with open(CONFIG / f'{camera}_calibration.yaml') as handle:
        return yaml.safe_load(handle)


@pytest.mark.parametrize('camera', CAMERAS)
def test_declares_its_own_name(camera):
    assert load(camera)['camera_name'] == camera


@pytest.mark.parametrize('a,b', list(itertools.combinations(CAMERAS, 2)))
@KNOWN_BAD
def test_two_cameras_never_share_intrinsics(a, b):
    """Three lenses cannot have one calibration.

    This is exactly what happened: one real calibration was written into all
    three files in a single commit, and the files were byte-identical apart
    from camera_name for two months. Cloned intrinsics are worse than absent
    ones, because a placeholder announces itself and a plausible matrix on the
    wrong camera does not.
    """
    matrix_a = load(a)['camera_matrix']['data']
    matrix_b = load(b)['camera_matrix']['data']
    assert matrix_a != matrix_b, (
        f'{a} and {b} have identical camera_matrix values. '
        'Each lens needs its own calibration.'
    )


@pytest.mark.parametrize('camera', CAMERAS)
@KNOWN_BAD
def test_principal_point_is_near_the_centre_of_the_declared_image(camera):
    """cx and cy should sit near the middle of the image the file declares.

    A principal point far from centre is possible on a real lens and is much
    more often a sign that the intrinsics were computed at one resolution and
    written into a file declaring another. That happened here: cx was 712 on a
    file claiming 1920 wide, which is what a 1440-wide calibration looks like,
    and it put a systematic 14 degree bearing error into every observation.

    A tenth of the frame is loose enough for any sane lens and tight enough to
    catch a resolution mismatch, which is off by a quarter or more.
    """
    data = load(camera)
    width = data['image_width']
    height = data['image_height']
    fx, _, cx, _, fy, cy, *_ = data['camera_matrix']['data']

    assert abs(cx - width / 2) < width * 0.1, (
        f'{camera}: cx is {cx:.1f} on a {width}-wide image, {abs(cx - width / 2):.0f} px '
        'off centre. Check the resolution the calibration was captured at.'
    )
    assert abs(cy - height / 2) < height * 0.1, (
        f'{camera}: cy is {cy:.1f} on a {height}-high image.'
    )
    assert fx > 0 and fy > 0, f'{camera}: focal lengths must be positive'


@pytest.mark.parametrize('camera', CAMERAS)
@KNOWN_BAD
def test_distortion_coefficients_match_the_model_they_claim(camera):
    """A rational_polynomial fit whose rational terms are all zero is not one.

    OpenCV's order is k1 k2 p1 p2 [k3 [k4 k5 k6 [s1 s2 s3 s4]]]. This file
    declared rational_polynomial with k4 through k6 zero and the thin-prism
    terms carrying the values, which means either the label or the ordering is
    wrong. Both were worth knowing and neither was visible by reading.
    """
    data = load(camera)
    model = data['distortion_model']
    coefficients = data['distortion_coefficients']['data']

    assert len(coefficients) == data['distortion_coefficients']['cols']

    if model == 'plumb_bob':
        assert len(coefficients) == 5, f'{camera}: plumb_bob takes 5 coefficients'
    elif model == 'rational_polynomial':
        assert len(coefficients) >= 8, f'{camera}: rational_polynomial takes at least 8'
        rational = coefficients[5:8]
        assert any(value != 0.0 for value in rational), (
            f'{camera}: declares rational_polynomial but k4, k5 and k6 are all zero, '
            'so the fit is not rational. Check the coefficient ordering, or the model name.'
        )
    else:
        pytest.fail(f'{camera}: unrecognised distortion model {model!r}')
