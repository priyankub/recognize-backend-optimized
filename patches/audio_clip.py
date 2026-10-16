"""Patch recognize_backend classifiers/audio.py: decode only the first RECOGNIZE_AUDIO_MAX_SECONDS (default 30) of each
file. Upstream librosa.load()s the whole file; MP3/M4A go through audioread, which decodes everything into RAM before
resampling, so a 25 h audiobook (1.4 GB MP3) grew the process to ~70 GB and got it OOM-killed (2026-10-15). AST only
looks at the first ~10 s anyway. 0 = whole file (upstream). Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()
old = "        wav, _ = librosa.load(path, sr=TARGET_SAMPLE_RATE, mono=True)\n"
if s.count(old) != 1:
    sys.exit("audio_clip patch: librosa.load not found exactly once")
s = s.replace(old, '''        max_seconds = float(os.environ.get("RECOGNIZE_AUDIO_MAX_SECONDS", "30"))
        wav, _ = librosa.load(
            path, sr=TARGET_SAMPLE_RATE, mono=True, duration=max_seconds if max_seconds > 0 else None
        )
''')
open(p, "w").write(s)
print("audio_clip patch applied")
