# recognize_backend, optimized: fixes and resource limits on top of upstream
# nextcloud/recognize_backend v1.0.5. See README.md for what each patch does.
#
# Upstream publishes no public image, so build the base from its source first
# (build.sh does both steps):
#   docker build -t recognize_backend:1.0.5-base https://github.com/nextcloud/recognize_backend.git#v1.0.5
#   docker build --build-arg BASE=recognize_backend:1.0.5-base -t recognize-backend-optimized:1.0.5 .
ARG BASE=recognize_backend:1.0.5-base
FROM ${BASE}

# Upstream pins onnxruntime-gpu==1.18.1, whose PyPI wheel is the CUDA 11 build. The image is CUDA 12, so face
# recognition (insightface/ONNX) silently runs on CPU. Swap in the CUDA 12 build of 1.18.1 plus the cuDNN 9 it
# needs (the base only has cuDNN 8). torch is unaffected: it bundles its own CUDA libraries.
RUN python3 -m pip uninstall -y onnxruntime-gpu \
 && python3 -m pip install onnxruntime-gpu==1.18.1 \
      --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ \
 && python3 -m pip install "nvidia-cudnn-cu12>=9,<10" \
 && rm -rf /root/.cache
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/nvidia/cudnn/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64

# HEIC/HEIF (iPhone) photos: upstream Pillow can't open them. Register pillow-heif at interpreter start via a .pth file.
RUN python3 -m pip install pillow-heif && rm -rf /root/.cache \
 && echo 'import sys; exec("try:\\n import pillow_heif; pillow_heif.register_heif_opener()\\nexcept Exception: pass")' \
    > /usr/local/lib/python3.10/dist-packages/zz_heif_opener.pth

# Source patches. Each one checks its anchor in the upstream code and fails the build if upstream changed.
# Order matters: idle_unload before lean_vram (lean_vram builds on it).
COPY patches/ /tmp/patches/
RUN python3 /tmp/patches/prefetch.py /app/lib/main.py \
 && python3 /tmp/patches/idle_unload.py /app/lib/main.py \
 && python3 /tmp/patches/lean_vram.py /app/lib/main.py \
 && python3 /tmp/patches/video_seek.py /app/lib/classifiers/video.py \
 && python3 /tmp/patches/video_ahead.py /app/lib/classifiers/video.py \
 && python3 /tmp/patches/audio_clip.py /app/lib/classifiers/audio.py \
 && python3 /tmp/patches/fix_ocs_error.py /app/lib/ocs.py \
 && rm -rf /tmp/patches
