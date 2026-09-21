# Capture profiles

One directory here is one **capture path**: how pixels get from the oToCam sensor
to the JPEG encoder and into gmslcam's appsink. Everything else about a camera —
its device, geometry, codec, frame, topics — lives in `../camera_{left,right,rear}.yaml`
and does not change between profiles; the calibration URL is set in
`camera.launch.xml`.

The split exists because the capture path is the one part of the pipeline that
cannot be settled without the hardware, and the hardware is on the vehicle.

The profile is `camera.launch.xml`'s `capture_profile` argument, and only that —
the `CAMERA_CAPTURE_PROFILE` environment variable it also used to read is gone.
`just launch` reaches `camera.launch.xml` through two installed Autoware sensing
files that forward a fixed set of arguments, and `capture_profile` is not one of
them, so through `just launch` the argument's default is what runs. To try
another profile, launch this file directly:

```bash
ros2 launch golfcart_sensor_kit_launch camera.launch.xml \
    camera_model:=gmslcam capture_profile:=v4l2-mmap
```

To change what the vehicle runs, change the default in `camera.launch.xml`.

## Layout: one file per camera

```
camera_capture/<profile>/left.yaml
camera_capture/<profile>/right.yaml
camera_capture/<profile>/rear.yaml
```

each holding exactly one parameter:

```yaml
/**:
  ros__parameters:
    pipeline: "..."
```

It was one file per profile, keyed `/**/camera_left:` and friends. That key
shape is an rclcpp feature: rclcpp expands the `/**/` prefix into a regex, while
rclrs (which gmslcam is built on) matches node keys literally, `/**` or the
node's full name, and nothing else. A single-file profile loads without error and
configures nothing, leaving every node on gmslcam's built-in `v4l2src
io-mode=dmabuf` pipeline. Three files keyed `/**` are what both runtimes read.

## Which one

| profile | source element | encoder | use it when |
|---|---|---|---|
| `nvv4l2camerasrc` | `nvv4l2camerasrc` | NVJPG | **default.** Verified on the vehicle: ~8% of a core per camera. |
| `v4l2-dmabuf` | `v4l2src io-mode=4` | NVJPG | first fallback; measured at ~40% of a core, so the copy is real. |
| `v4l2-mmap` | `v4l2src io-mode=2` | NVJPG | fallback that definitely copies. Proves the rest of the stack when the two above fail. |
| `sim` | `v4l2src` on v4l2loopback | `jpegenc` (CPU) | no cameras attached, any machine. Pairs with `just sim cameras`. |
| `sim-nvjpeg` | `v4l2src` on v4l2loopback | NVJPG | the same, on a Jetson, through the hardware encoder. |
| `videotestsrc` | `videotestsrc` inside the node | `jpegenc` (CPU) | no devices, no sudo: launch, topics, frame ids, format and calibration wiring, anywhere. |

The ladder to walk on the vehicle is `nvv4l2camerasrc` → `v4l2-dmabuf` →
`v4l2-mmap`, and `scripts/check/camera_pipeline.sh` walks it for you against a
real device and reports which cleared.

## What is identical in the hardware profiles

```
... ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! nvjpegenc quality=90
    ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0
    ! appsink name=ros_sink emit-signals=false sync=false max-buffers=2 drop=true
```

- **`nvvidconv`** is the VIC block, 4:2:2 to 4:2:0. Measured: this and the
  encoder together sustain three 30 fps streams with zero drops and 4.1x
  headroom on an AGX Orin.
- **`nvjpegenc quality=90`** is the NVJPG block. Not below 85 on these cameras:
  JPEG ringing lands on the high-contrast marker edges that subpixel refinement
  measures, and corner error becomes pose error.
- **The appsink is in the string**, named `ros_sink`, because gmslcam looks it up
  by that name and pulls encoded buffers from it. `max-buffers=2 drop=true` is
  what makes a wedged consumer cost frames instead of back-pressuring NVJPG, the
  VIC and the camera. The leaky queue in front of it is kept from the measured
  pipeline: it decouples the encoder thread from the sink, and two JPEG buffers
  is about 800 kB.

No `jpegparse`: `nvjpegenc` emits `image/jpeg` and the appsink takes it as is,
verified running. gmslcam's own default pipeline inserts one; the profiles do
not, and the measured strings are what they are.

## The device paths

`left` is `platform-tegra-capture-vi-video-index12`, `right` is `index0`, `rear`
is `index10`: the mapping the 2026-08-21 fix established, now in every hardware
profile and in `../camera_<cam>.yaml`. The two `v4l2-*` fallbacks carried the
pre-fix mapping until the move to gmslcam; that is corrected, not remeasured.
