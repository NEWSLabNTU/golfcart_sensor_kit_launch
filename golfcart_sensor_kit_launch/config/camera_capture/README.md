# Capture profiles

One file here is one **capture path**: how pixels get from the oToCam sensor to
`nvjpegenc`. Everything else about a camera — its name, frame, geometry,
calibration URL, encoding — lives in `../camera_{left,right,rear}.yaml` and does
not change between profiles.

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
    camera_model:=gscam capture_profile:=v4l2-mmap
```

To change what the vehicle runs, change the default in `camera.launch.xml`.

`camera.launch.xml` loads `../camera_<cam>.yaml` first and then the profile, so
the profile's `gscam_config` wins. Each profile carries all three cameras, keyed
by node name:

```yaml
/**/camera_left:
  ros__parameters:
    gscam_config: "..."
```

## Which one

| profile | source element | use it when |
|---|---|---|
| `nvv4l2camerasrc` | `nvv4l2camerasrc` | **default.** The zero-copy target: it either negotiates or it does not. |
| `v4l2-dmabuf` | `v4l2src io-mode=4` | byte-for-byte what shipped before profiles existed. First fallback. |
| `v4l2-mmap` | `v4l2src io-mode=2` | fallback that definitely copies. Use when the two above fail, to prove the rest of the stack. |
| `sim` | `v4l2src` on v4l2loopback | no cameras attached. Pairs with `just sim cameras`. |

The ladder to walk on the vehicle is `nvv4l2camerasrc` → `v4l2-dmabuf` →
`v4l2-mmap`, and `scripts/check/camera_pipeline.sh` walks it for you against a
real device and reports which cleared.

## What is identical in all of them

```
... ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! nvjpegenc quality=90
    ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0
```

- **`nvvidconv`** is the VIC block, 4:2:2 to 4:2:0. Measured: this and the
  encoder together sustain three 30 fps streams with zero drops and 4.1x
  headroom on an AGX Orin.
- **`nvjpegenc quality=90`** is the NVJPG block. Not below 85 on these cameras:
  JPEG ringing lands on the high-contrast marker edges that subpixel refinement
  measures, and corner error becomes pose error.
- **The trailing leaky queue** is not decoration. gscam 2.0.2 builds its own
  appsink with no `max-buffers`/`drop`, which is its documented permanent-stall
  bug, and those properties cannot be reached from `gscam_config`. With the
  queue there, a wedged appsink costs frames instead of back-pressuring NVJPG,
  the VIC and the camera. Two JPEG buffers is about 800 kB.

gscam appends `! appsink` itself. No `jpegparse` is needed — `nvjpegenc` emits
`image/jpeg` and that is what gscam's appsink asks for, verified running.

## The device paths

The three `by-path` names are the same in every profile except `sim`, and they
are the reason the device does not appear in `camera.launch.xml` any more: it
used to be declared there as `left_camera_device` and friends, which nothing
read, while the real path sat inside the `gscam_config` string. One place now.
