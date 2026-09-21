# gmslcam notes

What the three GMSL camera YAMLs in this directory carry, and the things about
gmslcam (`src/sensor_component/external/gmslcam` in the superproject, a Rust node
on rclrs 0.7) that are worth knowing before changing them.

Replaces `gscam.md`, 2026-09-21, when the driver changed. Facts below that were
verified against the previous driver and still hold are marked as such.

## Where things live

| file | holds |
|---|---|
| `camera_{left,right,rear}.yaml` | everything that does not depend on the capture path: device, geometry, codec, frame, topic names |
| `camera_capture/<profile>/{left,right,rear}.yaml` | `pipeline` alone, one file per camera |
| `camera_{left,right,rear}_calibration.yaml` | intrinsics |
| `../launch/camera.launch.xml` | the `camera_info_url` for each node, and the `capture_profile` default |

`camera.launch.xml` starts ONE gmslcam process for all three cameras. Its
process node is a transient host that reads `cameras: [rear, left, right]` and,
per key, `<key>.enabled`, `<key>.params_files` (the camera file, then the
profile's file for that camera) and `<key>.overrides` (`camera_info_url`), then
creates one camera node per key in `<host namespace>/<key>` and leaves the
graph. The three sources set disjoint parameters, so load order does not matter.
The per-camera files reach each node as node-local arguments; passed to the
process instead, rclrs would merge three `/**` files into every node and every
camera would be the last one. See `camera_capture/README.md` for why a profile
is a directory.

## Parameters gmslcam declares

Per camera node: `device`, `width`, `height`, `fps`, `codec`, `bitrate`,
`iframe_interval`, `frame_id`, `image_topic`, `camera_info_topic`,
`camera_info_url`, `pipeline`, `frames_per_sample`. On the host, read once at
startup: `cameras` and `<key>.{enabled,node_name,namespace,params_files,overrides}`.
Nothing else: an unknown key in a parameter file is ignored without a warning,
so a typo configures nothing rather than failing.

`bitrate` and `iframe_interval` are for the H.264/H.265 codecs and do nothing
under `codec: jpeg`. `device`, `width`, `height` and `fps` are read by the
**default** pipeline only; once a profile supplies `pipeline`, the caps in that
string decide the geometry, and the YAML values must simply agree with them
(they also seed the `CameraInfo` width and height when no calibration loads).

## The pipeline

A profile string ends in the appsink gmslcam pulls from:

```
<source> ! <caps> ! ... ! appsink name=ros_sink emit-signals=false sync=false max-buffers=2 drop=true
```

The name `ros_sink` is looked up; a string without it fails at startup with
`pipeline missing appsink named ros_sink`. `max-buffers=2 drop=true` is the
stall protection the previous driver could not express and needed a leaky queue
for; the hardware profiles keep that queue too, as measured.

**Do not run `nvjpegenc` and `nvv4l2h26xenc` in one process**: there is a
reported freeze on AGX Orin. This is why `codec` is JPEG in every camera file
rather than left at gmslcam's `h265` default, over and above the format
contract.

## What gmslcam writes into CompressedImage.format

`jpeg`. The bare form, with no `;` and no statement of channel order, from
`compressed_format()` in its `main.rs`. It is byte-for-byte what the previous
driver wrote, so every bag in this project still reads with the same consumer
code, and the channel-count fallback in the Rust transport crate remains the
main path. The contract lives in the superproject:
`docs/roadmaps/2-camera-image-pipeline.md`.

## Timestamps

`header.stamp` is the host clock at the moment gmslcam pulls the encoded buffer
from the appsink, on both the image and the `CameraInfo`. It is not the V4L2
capture time: the previous driver, with `use_gst_timestamps: true`, stamped from
the buffer PTS; gmslcam does not read the PTS at all. The difference is the
encode latency, milliseconds, and it is the same on every frame.
`do-timestamp=true` in the nvv4l2camerasrc profile is kept from the measured
string and now affects only GStreamer's own bookkeeping.

## camera_info IS published

Alongside every image, at the frame rate, with the same stamp and frame id.
gmslcam parses the calibration file itself (`image_width`, `image_height`,
`camera_name`, `camera_matrix`, `distortion_model`, `distortion_coefficients`,
`rectification_matrix`, `projection_matrix`: the `camera_calibration_parsers`
layout the three files already use) and publishes it with only the header
replaced. Nothing rescales anything: the `width`, `height`, `k`, `d`, `r` and
`p` in the file go out exactly as written.

That matters for one specific mistake. Change the capture resolution in a
profile and forget to recalibrate, and the images get bigger while `k` does not;
every pose computed from them is wrong by the ratio, and self-consistently so.
The published `width` and `height` are the evidence, because they still describe
the old size. `golfcart_aruco_detector` compares them against the frames it
receives and suppresses detections when they disagree.

`camera_info_url` accepts `file://<path>` or a bare absolute path. It does
**not** accept `package://`; that is an error at startup, which is why the URL is
built with `$(find-pkg-share)` in `camera.launch.xml` rather than written in the
YAML.

## The viewer copy: rviz/ topics and frames_per_sample

Every camera node also publishes `rviz/image_raw/compressed` and
`rviz/camera_info` (that is, `rviz/<image_topic>` and
`rviz/<camera_info_topic>`), every `frames_per_sample`-th encoded frame: same
bytes, same header as the frame it samples, the pair with one stamp. The count
is per encoded frame, not per second, so at 30 fps `2` is 15 fps and `3` is
10 fps; the camera YAMLs set `2`. It is lazy: on each candidate frame the node
asks the middleware how many subscribers the rviz image topic has and publishes
the pair only if that is at least one, so with nothing looking the topics exist
and stay silent. Subscribing to `rviz/camera_info` alone therefore yields
nothing; the image topic is the gate. The node logs `rviz sampler active` /
`idle` on the transitions, and its per-30-frame line counts sampled frames.
`frames_per_sample` is read live, so
`ros2 param set /sensing/camera/left/camera_left frames_per_sample 3` takes
effect on the next frame. `golfcart.rviz` reads the `rviz/` topics; every other
consumer, and every recording, reads the full-rate pair.

## Node name, namespace, topics

Camera nodes are named `camera_<key>` in `<host namespace>/<key>`, so under
the `sensing/camera` namespace the launch pushes they are
`/sensing/camera/left/camera_left` and siblings, one process for all three
(`pgrep -a gmslcam` shows one). Topics are the `image_topic` and
`camera_info_topic` parameters, resolved against that namespace, so no `<remap>`
is needed and none is present. QoS is `keep_last(5)`, reliable, volatile, on all
four publishers. Run alone, with no `cameras` parameter, the process is one
camera node named by its own `__node:=` remap, as the sim `configs` output shows.

## Output

gmslcam prints one line per 30 published frames to stdout, per camera, with the
sampled-for-rviz count beside it. At 30 fps that is a line a second per camera
in the launch log. It is the driver's, not ours.

## nvvidconv output formats (Jetson, non-NVMM)

Still true, still worth knowing:

`I420, UYVY, YUY2, YVYU, NV12, NV16, NV24, GRAY8, BGRx, RGBA, Y42B, Y444`

Notably **no `RGB` and no `RGBx`**, which is why the JPEG path needs no CPU
`videoconvert` on the Jetson (the `sim` and `videotestsrc` profiles have one,
because they encode in software).

`nvjpegenc` takes `{I420, NV12}` in NVMM, and `{I420, YV12, GRAY8}` in system
memory. Read that pair before proposing a grayscale JPEG at the source: `GRAY8`
is sysmem-only, so mono would leave NVMM and hand back the import copy.

## Device paths

`/dev/v4l/by-path/platform-tegra-capture-vi-video-index{12,0,10}` for left,
right and rear, as fixed on 2026-08-21. They appear in `camera_<cam>.yaml` as
`device` and inside the profile pipeline; the two must agree.

`by-id` does not work here: the units report identical product strings with no
unique serial, so `/dev/v4l/by-id/` collapses and cannot tell three cameras
apart.
