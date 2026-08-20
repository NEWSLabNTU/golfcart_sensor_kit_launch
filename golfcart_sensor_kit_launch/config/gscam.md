# gscam notes

What the three GMSL camera YAMLs in this directory actually carry, and the
things about gscam 2.0.2 that are worth knowing before changing them.

Rewritten 2026-08-21. The previous version described an
`RGBA -> videoconvert -> RGB` pipeline with `image_encoding: rgb8`, and a
`platform-3610000.usb-...` USB conversion-kit rig. Neither had been true for a
while: the cameras are oToCam GMSL units on `tegra-capture-vi`, and the pipeline
encodes JPEG in hardware with no CPU conversion in it. It was also the source of
the "one CPU colour conversion per camera" claim, which is why the correction is
recorded here rather than quietly applied.

## Where things live

| file | holds |
|---|---|
| `camera_{left,right,rear}.yaml` | everything that does not depend on the capture path: name, frame, geometry, calibration URL, encoding |
| `camera_capture/<profile>.yaml` | `gscam_config` alone, for all three cameras, keyed by node name |
| `camera_{left,right,rear}_calibration.yaml` | intrinsics |

`camera.launch.xml` loads the camera file and then the profile, so the profile
supplies the pipeline. Selected by `CAMERA_CAPTURE_PROFILE`; see
`camera_capture/README.md` and `config/sensors.conf`.

A bare `ros2 run gscam gscam_node --params-file camera_left.yaml` therefore has
no pipeline and will not start. Pass the profile as a second `--params-file`.

## The pipeline

```
<source> ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12
         ! nvjpegenc quality=90
         ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0
```

gscam appends `! appsink` itself. **No `jpegparse`**: `nvjpegenc` emits
`image/jpeg`, which is exactly what the appsink asks for with
`image_encoding: "jpeg"`. Verified running at 30 Hz.

The trailing leaky queue is the only part that is not obvious. gscam 2.0.2
builds its appsink with no `max-buffers` and no `drop`, which is its documented
permanent-stall bug, and neither property can be reached from `gscam_config`.
With the queue there, a wedged appsink costs frames instead of back-pressuring
NVJPG, the VIC and the camera.

## gscam 2.0.2 accepted `image_encoding` values

Only four. Anything else logs `Unsupported image encoding: ...`, leaves the
appsink caps unset, and the pipeline dies with `Failed to PAUSE stream`:

| `image_encoding` | appsink caps |
| ---------------- | ----------------------------- |
| `rgb8`           | `video/x-raw,format=RGB`      |
| `mono8`          | `video/x-raw,format=GRAY8`    |
| `yuv422`         | `video/x-raw,format=UYVY`     |
| `jpeg`           | `image/jpeg`                  |

`bgr8`, `yuv422_yuy2`, `bgra8` and friends are **not** supported in 2.0.2.

**We use `jpeg`.** With it gscam publishes `sensor_msgs/CompressedImage` and
nothing else, so there is no raw `image_raw` topic at all: a consumer
subscribing to one waits forever and presents as a camera that sees nothing.

## What gscam writes into CompressedImage.format

`jpeg`. The bare form, with no `;`, and no statement of channel order.
Confirmed by running it.

That is legal, it is what every bag in this project contains, and consumers must
implement the channel-count fallback to read it. The contract and the Rust
implementation live in the superproject, not here: `docs/roadmaps/2-camera-image-pipeline.md`
and `src/common/rclrs_image_transport/`. Not linked, because this package is a
submodule and the link would dangle in a standalone checkout.

## camera_info IS published

Checked 2026-08-20 by running these YAMLs with these remaps: gscam loads the
calibration from `camera_info_url` and publishes `camera_info` at the frame
rate, 30 Hz. An earlier note in `config/recording/master_topics.txt` claiming it
publishes none was wrong, and the topics are now recorded.

`camera_info_rescale: true` matters if the calibration was taken at a different
resolution than the stream.

## Dead parameters

`video_device`, `auto_exposure`, `auto_white_balance`, `brightness`, `contrast`
and `saturation` are `usb_cam` parameters. gscam declares none of them and reads
none of them. They are left in place only because removing them is a change with
no benefit; do not add more, and do not expect editing them to do anything.

`image_width`, `image_height` and `framerate` are in the same category: the
geometry comes from the caps in `gscam_config`. Change the pipeline, not these.

## nvvidconv output formats (Jetson, non-NVMM)

`I420, UYVY, YUY2, YVYU, NV12, NV16, NV24, GRAY8, BGRx, RGBA, Y42B, Y444`

Notably **no `RGB` and no `RGBx`**, which is why the old `rgb8` pipeline needed a
CPU `videoconvert` and why the JPEG path does not.

`nvjpegenc` takes `{I420, NV12}` in NVMM, and `{I420, YV12, GRAY8}` in system
memory. Read that pair before proposing a grayscale JPEG at the source: `GRAY8`
is sysmem-only, so mono would leave NVMM and hand back the import copy.

## Device paths

`/dev/v4l/by-path/platform-tegra-capture-vi-video-index{0,10,12}` for
left, right and rear. They live in the capture profile now, in one place.

`by-id` does not work here and did not on the old USB rig either: the units
report identical product strings with no unique serial, so `/dev/v4l/by-id/`
collapses and cannot tell three cameras apart.
