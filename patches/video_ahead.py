"""Patch recognize_backend classifiers/video.py: decode and preprocess videos ahead, in the download threads, while
the GPU classifies the current one. Upstream (and the prefetch patch alone) decodes each video on the main thread right
before classifying it, so a video task kept ~1 CPU decode busy and left the GPU idle most of the time.

Adds prepare(path), which prefetch.py calls after each download. At most RECOGNIZE_VIDEO_DECODE_WORKERS (default 4)
videos decode at once. The classifier picks up the prepared tensors; a file that wasn't prepared is decoded in place
as before. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

old_run = '''        frames = _read_frames(path, NUM_FRAMES)
        # transformers expects a list of frames per video; pass list-of-arrays.
        inputs = processor(list(frames), return_tensors="pt")
'''
old_build = "def build():\n"
for old in (old_run, old_build):
    if s.count(old) != 1:
        sys.exit("video_ahead patch: anchor not found exactly once: " + old.strip().splitlines()[0])

s = s.replace(old_run, '''        inputs = _take_inputs(path)
''')
s = s.replace(old_build, '''DECODE_WORKERS = max(1, int(os.environ.get("RECOGNIZE_VIDEO_DECODE_WORKERS", "4")))
_DECODE_SLOTS = threading.BoundedSemaphore(DECODE_WORKERS)
_PREPARED: dict = {}  # path -> processor inputs, or the exception decoding raised
_PREPARED_MAX = 64
_LOCK = threading.Lock()
_IMAGE_PROCESSOR: list = []


def _image_processor():
    with _LOCK:
        if not _IMAGE_PROCESSOR:
            from transformers import VideoMAEImageProcessor

            _IMAGE_PROCESSOR.append(VideoMAEImageProcessor.from_pretrained(DEFAULT_MODEL))
        return _IMAGE_PROCESSOR[0]


def _make_inputs(path: str):
    # transformers expects a list of frames per video; pass list-of-arrays.
    return _image_processor()(list(_read_frames(path, NUM_FRAMES)), return_tensors="pt")


def prepare(path: str) -> None:
    """Decode and preprocess a downloaded video ahead of classification (runs in a download thread)."""
    with _DECODE_SLOTS:
        try:
            result = _make_inputs(path)
        except Exception as e:
            result = e
    with _LOCK:
        _PREPARED[path] = result
        while len(_PREPARED) > _PREPARED_MAX:  # entries of aborted tasks
            del _PREPARED[next(iter(_PREPARED))]


def _take_inputs(path: str):
    with _LOCK:
        result = _PREPARED.pop(path, None)
    if result is None:
        return _make_inputs(path)
    if isinstance(result, Exception):
        raise result
    return result


def build():
''')
s = s.replace("import os\n", "import os\nimport threading\n", 1)
open(p, "w").write(s)
print("video_ahead patch applied")
