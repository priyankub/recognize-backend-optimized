"""Patch recognize_backend main.py: drop cached models after RECOGNIZE_IDLE_UNLOAD_SECONDS
(default 600) without tasks, so the shared RTX 3050 has VRAM for Memories/go-vod transcodes.
Models reload lazily (a few seconds) on the next task. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

def sub(old, new):
    global s
    if s.count(old) != 1:
        sys.exit(f"idle_unload patch: anchor not found exactly once: {old!r}")
    s = s.replace(old, new)

sub("PROCESSOR_LOCK = threading.Lock()\n", '''PROCESSOR_LOCK = threading.Lock()
IDLE_UNLOAD_SECONDS = int(os.environ.get("RECOGNIZE_IDLE_UNLOAD_SECONDS", "600"))
LAST_TASK_AT = [perf_counter()]


def unload_if_idle() -> None:
    if IDLE_UNLOAD_SECONDS <= 0:
        return
    with PROCESSOR_LOCK:
        if not PROCESSOR_CACHE or perf_counter() - LAST_TASK_AT[0] < IDLE_UNLOAD_SECONDS:
            return
        names = list(PROCESSOR_CACHE)
        PROCESSOR_CACHE.clear()
    import gc
    gc.collect()
    _free_cuda_cache()
    LOGGER.info("Idle for %ss, unloaded %s", IDLE_UNLOAD_SECONDS, ", ".join(names))
''')
sub("        interval = WAIT_INTERVAL\n", "        interval = WAIT_INTERVAL\n    unload_if_idle()\n    interval = min(interval, 60)\n")
sub("            output = process_task(task, task_type)\n",
    "            output = process_task(task, task_type)\n            LAST_TASK_AT[0] = perf_counter()\n")
open(p, "w").write(s)
print("idle_unload patch applied")
