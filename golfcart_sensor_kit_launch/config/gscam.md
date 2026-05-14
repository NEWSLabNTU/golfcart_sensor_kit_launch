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

## image_transport plugin allowlist

By default `gscam` advertises `image_raw`, `image_raw/compressed`,
`image_raw/compressedDepth`, and `image_raw/theora` if the matching
`image_transport_plugins` debs are installed. The compressed/theora plugins
are *lazy* — they only encode when a subscriber connects — so they add no CPU
load while idle, but the extra topics clutter `ros2 topic list` and become a
silent CPU footgun if any tool subscribes to `/compressed`.

Restrict the advertised plugins per-camera in YAML:

```yaml
camera.image_raw.enable_pub_plugins: ["image_transport/raw"]
```

### Parameter name caveat

The parameter key is `<publisher_base_topic>.enable_pub_plugins` with `/`
replaced by `.`. gscam's internal publisher base is `camera/image_raw`
(visible in the unmapped topic list as `.../camera/image_raw/compressed`),
so the key is `camera.image_raw.enable_pub_plugins` — *not* a flat
`enable_pub_plugins`. A flat key parses without error but is silently
ignored.

Verify with:

```bash
ros2 param get /sensing/camera/<cam>/usb_camera_<cam> camera.image_raw.enable_pub_plugins
# → ['image_transport/raw']
```

## Per-camera publish CPU

At 1920×1280 UYVY @ 30 fps each cam consumes ~25 % of one Cortex-A78AE core
purely for `raw` publishing (gscam buffer → `sensor_msgs/Image` memcpy + DDS
serialize/fragment of 147 MB/s). Plugins are not the bulk; the raw path is.

CPU-reduction options if needed:

1. **Drop resolution/fps** in both `gscam_config` caps and the
   `image_width` / `image_height` / `framerate` rosparams (e.g. 1280×720 @
   15 fps ≈ 7 % CPU).
2. **Intra-process / shared memory** — run gscam and the subscriber inside
   one component container, or switch RMW to Cyclone + iceoryx to skip
   serialization.
3. **GPU-side JPEG** — encode with `nvjpegenc` inside `gscam_config` and
   publish only the compressed topic (requires consumer support).

## appsink stall under publish backpressure

Symptom: one or two of the three gscam nodes log a steady stream of
`Got data` / `Publishing the image` / `Getting data...` and then freeze on
`Getting data...` indefinitely. The process stays alive (sleeping at ~1 %
CPU) and `gst_app_sink_pull_sample` never returns. Standalone
`gst-launch-1.0 ... ! fpsdisplaysink` on the same device runs cleanly, so it
is not a v4l2/bandwidth/hardware issue.

Root cause: gscam's appsink has a small bounded queue with `drop=false`.
Any momentary slowness in the ROS publish path (DDS write, image_transport,
CPU spike on the publishing thread) fills the appsink, which then
back-pressures upstream and stalls `v4l2src` permanently. Which camera
loses the race is non-deterministic.

Fix: insert a leaky queue in `gscam_config` between `v4l2src` and gscam's
appsink so the capture stage is decoupled from the publish stage:

```yaml
gscam_config: "v4l2src device=/dev/v4l/by-path/...-index0 ! video/x-raw,format=UYVY,width=1920,height=1280,framerate=30/1 ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0"
```

`leaky=downstream` drops the oldest frame when the queue is full instead of
blocking the source, so a slow publish thread costs a dropped frame rather
than a permanently dead camera.
