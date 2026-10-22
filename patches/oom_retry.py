"""Patch recognize_backend main.py (after lean_vram.py): treat CUDA out-of-memory as a wait-and-retry, not a reason to
fall back to CPU. Upstream's fallback matches any message containing "CUDA", so a single OOM while another GPU app
(e.g. Ollama) briefly holds VRAM moved the whole worker to CPU until the container restarted. Now an OOM during model
load or inference unloads the other cached models, frees PyTorch's cache, waits (RECOGNIZE_OOM_WAITS seconds,
default 30,60,120,300,600,900) and retries the same file. If VRAM is still short after the last wait, the task fails
instead of the file silently getting an empty result. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()

def sub(old, new):
    global s
    if s.count(old) != 1:
        sys.exit(f"oom_retry patch: anchor not found exactly once: {old!r}")
    s = s.replace(old, new)

sub("def _build_with_fallback(task_type: str):\n", '''OOM_WAITS = [int(w) for w in os.environ.get("RECOGNIZE_OOM_WAITS", "30,60,120,300,600,900").split(",") if w.strip()]


def _is_oom(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "out of memory" in msg or "failed to allocate memory" in msg


def _oom_retry(task_type: str, fn):
    """Run fn; on GPU out-of-memory, free other models' VRAM and retry after each wait in OOM_WAITS."""
    for wait in OOM_WAITS + [None]:
        try:
            return fn()
        except Exception as e:
            if wait is None or not _is_oom(e):
                raise
            with PROCESSOR_LOCK:
                for other in [t for t in PROCESSOR_CACHE if t != task_type]:
                    del PROCESSOR_CACHE[other]
            import gc
            gc.collect()
            _free_cuda_cache()
            LOGGER.warning("GPU out of memory in %s, retrying in %ss: %s", task_type, wait, str(e).splitlines()[0][:200])
            sleep(wait)


def _build_with_fallback(task_type: str):
''')
sub('''            if state["device"] != "cuda" or not is_cuda_runtime_error(e):
                raise
''', '''            if state["device"] != "cuda" or not is_cuda_runtime_error(e) or _is_oom(e):
                raise
''')
sub("    processor = get_processor(task_type)\n",
    "    processor = _oom_retry(task_type, lambda: get_processor(task_type))\n")
sub('''                    results.append(processor(path))
                except Exception as e:
''', '''                    results.append(_oom_retry(task_type, lambda: processor(path)))
                except Exception as e:
                    if _is_oom(e):
                        raise
''')
open(p, "w").write(s)
print("oom_retry patch applied")
