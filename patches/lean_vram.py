"""Patch recognize_backend main.py (after idle_unload.py): unload the video and audio models right after their task
(RECOGNIZE_TRANSIENT_MODELS), keep at most RECOGNIZE_MAX_LOADED_MODELS (default 3) loaded, evicting the least
recently used, and return PyTorch's cached-but-free VRAM after every task. Upstream keeps every model it ever loaded
(images + faces + video ~6.5 GB on the 3050), which starved Ollama captioning during the backfill. The image and face
models (~1.5 GB together) stay loaded, since those batches alternate and reloading the image model costs ~1-2 min.
Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

def sub(old, new):
    global s
    if s.count(old) != 1:
        sys.exit(f"lean_vram patch: anchor not found exactly once: {old!r}")
    s = s.replace(old, new)

sub('''        if task_type in PROCESSOR_CACHE:
            return PROCESSOR_CACHE[task_type]
        processor = _build_with_fallback(task_type)
''', '''        if task_type in PROCESSOR_CACHE:
            PROCESSOR_CACHE[task_type] = PROCESSOR_CACHE.pop(task_type)  # mark most recently used
            return PROCESSOR_CACHE[task_type]
        evicted = []
        while PROCESSOR_CACHE and len(PROCESSOR_CACHE) >= MAX_LOADED_MODELS:
            oldest = next(iter(PROCESSOR_CACHE))
            del PROCESSOR_CACHE[oldest]
            evicted.append(oldest)
        if evicted:
            import gc
            gc.collect()
            _free_cuda_cache()
            LOGGER.info("Unloaded %s to make room for %s", ", ".join(evicted), task_type)
        processor = _build_with_fallback(task_type)
''')
sub("LAST_TASK_AT = [perf_counter()]\n",
    'LAST_TASK_AT = [perf_counter()]\nMAX_LOADED_MODELS = max(1, int(os.environ.get("RECOGNIZE_MAX_LOADED_MODELS", "3")))\nTRANSIENT_MODELS = {\n    t.strip() for t in os.environ.get("RECOGNIZE_TRANSIENT_MODELS", "video,audio").split(",") if t.strip()\n}\n\n\ndef after_task(task_type: str) -> None:\n    """Drop rarely used models (video, audio) straight away and hand cached VRAM back."""\n    if task_type.split(":")[1] in TRANSIENT_MODELS:\n        with PROCESSOR_LOCK:\n            PROCESSOR_CACHE.pop(task_type, None)\n        import gc\n        gc.collect()\n    _free_cuda_cache()\n')
sub("            LAST_TASK_AT[0] = perf_counter()\n",
    "            LAST_TASK_AT[0] = perf_counter()\n            after_task(task_type)\n")
open(p, "w").write(s)
print("lean_vram patch applied")
