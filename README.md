# recognize-backend-optimized

Fixes and resource limits for [nextcloud/recognize_backend](https://github.com/nextcloud/recognize_backend) v1.0.5,
the AppAPI ExApp that Recognize 13+ uses to tag photos, faces, video and audio. It's meant for a single consumer GPU
(written on an 8 GB RTX 3050) that other services share.

Upstream code is unchanged in the repository. The Dockerfile builds upstream's image from source, then applies small
patch scripts. Each patch checks that the upstream code it targets is still there and fails the build if it isn't,
so a new upstream version can't be patched silently and wrongly.

## What it changes

| Change | Problem upstream | Effect |
|---|---|---|
| onnxruntime-gpu CUDA 12 build + cuDNN 9 | The pinned PyPI wheel is the CUDA 11 build, so face recognition fell back to CPU without an error | Faces run on the GPU |
| `pillow-heif` | Pillow can't open HEIC/HEIF, so iPhone photos failed | HEIC photos are classified |
| `prefetch.py` | Files are downloaded and classified strictly one at a time; the GPU waits on HTTP | Next N files download in parallel (about 1.6x faster on multi-MB photos); temp files left by a restart are removed at startup |
| `idle_unload.py` | Models stay in VRAM forever | Models unload after a quiet period and reload on the next task |
| `lean_vram.py` | Every model ever loaded stays resident (images + faces + video ≈ 6.5 GB) | At most N models (LRU); video and audio models drop after each task; PyTorch's VRAM cache is freed per task |
| `video_seek.py` | Whole videos are decoded on the CPU to keep 16 frames (up to ~50 s per video) | Small clips are read front to back; larger ones seek and decode only the keyframe nearest each sample (4K: ~20-75 CPU-s down to ~2-6 per video) |
| `video_ahead.py` | Each video is decoded on the main thread just before classification, so the GPU waits | Videos are decoded and preprocessed in the download threads, N at a time, while the GPU works |
| `audio_clip.py` | Whole audio files are decoded into RAM; a 25 h audiobook grew the process to ~70 GB | Decodes only the first N seconds (the model looks at ~10 s) |
| `fix_ocs_error.py` | A failed file download raised `'LookupDict' object is not callable` | The real HTTP status is reported |
| `enabled_retry.py` | If Nextcloud was not up when the container started, the app never picked up tasks until restarted | The app keeps asking Nextcloud every minute until it reports the app as enabled |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `COMPUTE_DEVICE` | (upstream) | Set to `cuda`, or everything runs on the CPU |
| `RECOGNIZE_PREFETCH` | `8` | Files downloaded ahead of the one being classified |
| `RECOGNIZE_IDLE_UNLOAD_SECONDS` | `600` | Unload all models after this long without tasks; `0` keeps them |
| `RECOGNIZE_MAX_LOADED_MODELS` | `3` | Most models held at once, least recently used evicted |
| `RECOGNIZE_TRANSIENT_MODELS` | `video,audio` | Models unloaded right after each of their tasks |
| `RECOGNIZE_AUDIO_MAX_SECONDS` | `30` | Seconds of audio decoded per file; `0` decodes the whole file |
| `RECOGNIZE_VIDEO_DECODE_WORKERS` | `4` | Videos decoded ahead at once |
| `RECOGNIZE_VIDEO_SEQUENTIAL_MPIX` | `500` | Videos under this many frames x megapixels (~8 s of 1080p) are read front to back instead of seeking |

All upstream settings (`APP_ID`, `APP_SECRET`, `APP_PORT`, `NEXTCLOUD_URL`, …) work as upstream documents.

## Build

```sh
./build.sh                                   # -> recognize-backend-optimized:1.0.5
TAG=registry.example/recognize:1.0.5 ./build.sh
```

The base image is large (about 17 GB, CUDA + PyTorch); the overlay adds about 3 GB.

## Run

Run it like upstream's image, as a manually installed ExApp: start the container with the NVIDIA runtime and GPU access, then
register it with AppAPI on a `manual-install` daemon pointing at the container.

Recreating the container while it is working leaves its TaskProcessing rows at status 2 (running) for good. Stop it, then reset them:

```sql
UPDATE oc_taskprocessing_tasks SET status = 1, started_at = NULL, progress = 0
WHERE type LIKE 'recognize:%' AND status = 2;
```

## License

AGPL-3.0, like upstream.
