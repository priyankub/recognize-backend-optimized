"""Patch recognize_backend classifiers/video.py: read the 16 sampled frames cheaply instead of decoding the whole video
front to back (and decoding it twice when the container has no frame count). Upstream decodes every frame on the CPU
to keep 16, so long videos took up to ~50 s each with all cores busy and the GPU idle.

* Small clips (frames x pixels under RECOGNIZE_VIDEO_SEQUENTIAL_MPIX, default 500, about 8 s of 1080p) are read
  front to back as upstream does. That is the cheapest way to get the exact frames.
* Everything else seeks to each sample and decodes keyframes only, taking the keyframe at or before the sample when it
  is within max(1 s, half the spacing between samples). Otherwise it decodes on to the exact sampled frame. Measured on
  this workload: 3 s 4K clip 18 -> 2 CPU-s, 8 s 4K60 HEVC 78 -> 5 CPU-s (48 front to back).

Falls back to the upstream sequential read if seeking fails. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

old = "def _read_frames(path: str, num_samples: int) -> np.ndarray:\n"
if s.count(old) != 1:
    sys.exit("video_seek patch: _read_frames not found exactly once")
s = s.replace(old, '''SEQUENTIAL_MPIX = float(os.environ.get("RECOGNIZE_VIDEO_SEQUENTIAL_MPIX", "500"))


def _read_frames(path: str, num_samples: int) -> np.ndarray:
    try:
        return _read_frames_seek(path, num_samples)
    except Exception:
        return _read_frames_sequential(path, num_samples)


def _read_frames_seek(path: str, num_samples: int) -> np.ndarray:
    import av

    container = av.open(path)
    try:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        rate = stream.average_rate or stream.guessed_rate
        tb = stream.time_base
        if not rate or not tb:
            raise ValueError("no frame rate or time base")
        fps = float(rate)
        total = stream.frames or 0
        if total == 0:
            if stream.duration:
                seconds = float(stream.duration * tb)
            elif container.duration:
                seconds = container.duration / av.time_base
            else:
                raise ValueError("no frame count or duration")
            total = int(seconds * fps)
        ctx = stream.codec_context
        if total <= num_samples or total * ctx.width * ctx.height < SEQUENTIAL_MPIX * 1e6:
            raise ValueError("small video, sequential read is cheaper")
        tolerance = max(1.0, 0.5 * total / num_samples / fps)
        start = stream.start_time or 0
        out = []
        for idx in _sample_indices(total, num_samples):
            target = idx / fps
            container.seek(start + int(target / tb), stream=stream, backward=True, any_frame=False)
            ctx.skip_frame = "NONKEY"
            keyframes_only = True
            picked = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                picked = frame
                t = float((frame.pts - start) * tb)
                if keyframes_only:
                    if target - t <= tolerance:
                        break
                    ctx.skip_frame = "DEFAULT"  # keyframe too far back: decode on to the exact frame
                    keyframes_only = False
                if t >= target - 0.5 / fps:
                    break
            ctx.skip_frame = "DEFAULT"
            if picked is None:
                raise ValueError("seek decoded nothing")
            out.append(picked.to_ndarray(format="rgb24"))
    finally:
        container.close()
    return np.stack(out, axis=0)


def _read_frames_sequential(path: str, num_samples: int) -> np.ndarray:
''')
open(p, "w").write(s)
print("video_seek patch applied")
