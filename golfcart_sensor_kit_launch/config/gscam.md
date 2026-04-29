# gscam USB camera notes

## gscam 2.0.2 accepted `image_encoding` values

Only four values are allowed — anything else logs `Unsupported image encoding: ...`
and leaves appsink caps unset, causing the pipeline to fail with
`Failed to PAUSE stream`:

| `image_encoding` | appsink caps                  |
| ---------------- | ----------------------------- |
| `rgb8`           | `video/x-raw,format=RGB`      |
| `mono8`          | `video/x-raw,format=GRAY8`    |
| `yuv422`         | `video/x-raw,format=UYVY`     |
| `jpeg`           | `image/jpeg`                  |

`bgr8`, `yuv422_yuy2`, `bgra8`, etc. are **not** supported in 2.0.2.

## `nvvidconv` output formats (Jetson, non-NVMM)

`I420, UYVY, YUY2, YVYU, NV12, NV16, NV24, GRAY8, BGRx, RGBA, Y42B, Y444`

Notably **no `RGB` and no `RGBx`**. To produce `RGB` for gscam, append
`videoconvert`. The minimum-CPU feed to `videoconvert` is `RGBA` (just strips
the alpha byte — no color-space math, no channel swap), which is cheaper than
`BGRx` (swap + strip).

## Chosen pipeline (all three YAMLs)

```
v4l2src device=/dev/videoN
  ! video/x-raw,format=UYVY,width=1920,height=1280,framerate=30/1
  ! nvvidconv
  ! video/x-raw,format=RGBA
  ! videoconvert
  ! video/x-raw,format=RGB
```
paired with `image_encoding: rgb8`.

Native sensor mode is UYVY 1920x1280 @ 30 fps (not 1080).

## Ability GMSL2-USB3.0 Conversion Kit device layout

Each adapter exposes two `/dev/video*` nodes:

- even index (`video0`, `video2`, `video4`) → **capture**, lists `UYVY`
- odd index  (`video1`, `video3`, `video5`) → **metadata**, empty format list

Pointing gscam at an odd node yields
`Device '...' is not a capture device.` followed by `Failed to PAUSE stream`.

### `by-id` pitfall

All three units report the same USB product string
(`Ability_GMSL2-USB3.0_Conversion_Kit_C1-Master`) with no unique serial,
so `/dev/v4l/by-id/` collapses to a single symlink pair and cannot
disambiguate the three adapters. The suffix there (`-video-index0`,
`-video-index1`) refers to the **two nodes of one device**, not three cameras.

### `by-path` works

`/dev/v4l/by-path/` keys off the USB port and is stable per-cabling:

```
platform-3610000.usb-usb-0:2.2:1.0-video-index0 -> video0   (capture, left)
platform-3610000.usb-usb-0:2.3:1.0-video-index0 -> video2   (capture, rear)
platform-3610000.usb-usb-0:2.4:1.0-video-index0 -> video4   (capture, right)
```

The trailing digit of the USB port (`2.2` / `2.3` / `2.4`) is the stable
by-path identifier for each camera. The YAMLs use the `by-path` symlinks so
that physical assignment stays correct regardless of enumeration order.

## Current YAML → device mapping

| YAML                     | by-path symlink                                                  | resolves to   |
| ------------------------ | ---------------------------------------------------------------- | ------------- |
| `usb_camera_left.yaml`   | `/dev/v4l/by-path/platform-3610000.usb-usb-0:2.2:1.0-video-index0` | `/dev/video0` |
| `usb_camera_rear.yaml`   | `/dev/v4l/by-path/platform-3610000.usb-usb-0:2.3:1.0-video-index0` | `/dev/video2` |
| `usb_camera_right.yaml`  | `/dev/v4l/by-path/platform-3610000.usb-usb-0:2.4:1.0-video-index0` | `/dev/video4` |

Physical left/right/rear assignment confirmed by viewing each stream.

## Reproducing the pipeline standalone

```bash
gst-launch-1.0 v4l2src device=/dev/video4 num-buffers=1 \
  ! 'video/x-raw,format=UYVY,width=1920,height=1280,framerate=30/1' \
  ! nvvidconv ! 'video/x-raw,format=RGBA' \
  ! videoconvert ! 'video/x-raw,format=RGB' \
  ! fakesink
```

Expected: `Got EOS from element "pipeline0".`

## Running the node

Run from the repo root (`~/2026-golf-cart`) so the relative path resolves:

```bash
ros2 run gscam gscam_node --ros-args \
  --params-file src/sensor_kit/golfcart_sensor_kit_launch/golfcart_sensor_kit_launch/config/usb_camera_right.yaml
```

The earlier `Couldn't parse params file` / `unknown ROS arguments` errors came
from running in the wrong working directory or a stray invisible character in
the shell input (e.g. `●` at the start of a pasted command) — not from the
YAML itself.
