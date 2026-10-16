"""Patch recognize_backend classifiers/video.py: grab the 16 sampled frames by seeking to each one instead of decoding
the whole video front to back (and decoding it twice when the container has no frame count). Upstream decodes every
frame on the CPU to keep 16, so long videos took up to ~50 s each with all cores busy and the GPU idle. Seeking decodes
only from the keyframe before each sample. Same frame indices as upstream; falls back to the upstream sequential
read if seeking fails. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

old = "def _read_frames(path: str, num_samples: int) -> np.ndarray:\n"
if s.count(old) != 1:
    sys.exit("video_seek patch: _read_frames not found exactly once")
s = s.replace(old, '''def _read_frames(path: str, num_samples: int) -> np.ndarray:
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
        if total <= num_samples:
            raise ValueError("short video, sequential read is cheap")
        start = stream.start_time or 0
        out = []
        for idx in _sample_indices(total, num_samples):
            target = idx / fps
            container.seek(start + int(target / tb), stream=stream, backward=True, any_frame=False)
            picked = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                picked = frame
                if float((frame.pts - start) * tb) >= target - 0.5 / fps:
                    break
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
