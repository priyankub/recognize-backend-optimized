"""Patch recognize_backend main.py: download the next RECOGNIZE_PREFETCH (default 8) task files in parallel while
the current one is classified. Upstream downloads and classifies strictly one file at a time, so with multi-MB
photos the GPU sat ~90% idle waiting on HTTP. Results stay in input order. Fails the build if upstream changed."""
import hashlib
import sys

p = sys.argv[1]
s = open(p).read()
a = s.index("def process_task(")
b = s.index("def wait_for_task(")
if hashlib.sha256(s[a:b].encode()).hexdigest() != "8ab9f4bcfce2f2fdd87178a78441f0e3130d45a3b889eb84d73dadb417068786":
    sys.exit("prefetch patch: upstream process_task changed, review the patch")

new = '''PREFETCH = max(1, int(os.environ.get("RECOGNIZE_PREFETCH", "8")))
_THREAD_NC = threading.local()


def _thread_nc() -> NextcloudApp:
    """One NextcloudApp (HTTP session) per download thread."""
    if not hasattr(_THREAD_NC, "nc"):
        _THREAD_NC.nc = NextcloudApp()
    return _THREAD_NC.nc


def process_task(task: dict, task_type: str) -> dict:
    """Run a task: download input files (PREFETCH in parallel), classify in order, return ``{"output": [...]}``."""
    from concurrent.futures import ThreadPoolExecutor

    nc = NextcloudApp()
    processor = get_processor(task_type)
    file_ids = task.get("input", {}).get("input")
    if not isinstance(file_ids, list):
        raise ValueError(f"Unexpected input shape: {task.get('input')!r}")

    results: list[str] = []
    total = max(1, len(file_ids))
    futures: dict = {}
    next_i = 0

    def fetch(file_id):
        return get_file(_thread_nc(), task["id"], int(file_id))

    with ThreadPoolExecutor(max_workers=PREFETCH) as pool:
        try:
            for i, file_id in enumerate(file_ids):
                while next_i < len(file_ids) and next_i < i + PREFETCH:
                    futures[next_i] = pool.submit(fetch, file_ids[next_i])
                    next_i += 1
                try:
                    path = futures.pop(i).result()
                except Exception as e:
                    LOGGER.error("Failed to download file %s for task %s: %s", file_id, task["id"], e)
                    results.append("")
                    continue
                try:
                    results.append(processor(path))
                except Exception as e:
                    LOGGER.error(
                        "Processor failed on file %s (task %s): %s\\n%s",
                        file_id,
                        task["id"],
                        e,
                        "".join(traceback.format_exception(e)),
                    )
                    results.append("")
                finally:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                try:
                    nc.providers.task_processing.set_progress(task["id"], (i + 1) / total)
                except Exception as e:
                    LOGGER.warning("Failed to report progress for task %s: %s", task["id"], e)
        finally:
            # On an abort, don't leave prefetched temp files behind.
            for fut in futures.values():
                fut.cancel()
            for fut in futures.values():
                if not fut.cancelled():
                    try:
                        os.remove(fut.result())
                    except Exception:
                        pass

    return {"output": results}


'''
open(p, "w").write(s[:a] + new + s[b:])
print("prefetch patch applied")
