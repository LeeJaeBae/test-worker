#!/bin/bash
echo "### SMART START SCRIPT BOOTED ###"

# 1. ComfyUI가 있을만한 경로 후보 리스트
CANDIDATES=(
    "/runpod-volume/runpod-slim/ComfyUI"
    "/workspace/runpod-slim/ComfyUI"
    "/workspace/ComfyUI"
    "/ComfyUI"
)

COMFYUI_DIR=""

# 2. 경로 탐색 루프
for path in "${CANDIDATES[@]}"; do
    if [ -d "$path" ]; then
        echo "✅ FOUND ComfyUI at: $path"
        COMFYUI_DIR="$path"
        break
    else
        echo "Searching... not found at $path"
    fi
done

# 3. 못 찾았을 경우 디버깅 모드 진입
if [ -z "$COMFYUI_DIR" ]; then
    echo "🚨 ERROR: Could not find ComfyUI in any standard location!"
    echo "Listing root directories for debugging:"
    ls -d /*
    echo "Listing /workspace (if exists):"
    ls -R /workspace 2>/dev/null || echo "No /workspace"
    echo "Listing /runpod-volume (if exists):"
    ls -R /runpod-volume 2>/dev/null || echo "No /runpod-volume"
    
    # 로그 확인할 시간 벌기 (1시간 대기)
    sleep 3600
    exit 1
fi

cd "$COMFYUI_DIR"

# 4. 가상환경(VENV) 활성화 시도
# 보통 같은 폴더 안에 .venv 또는 .venv-cu128 등으로 존재
VENV_FOUND=false
for venv_name in ".venv-cu128" ".venv" "venv"; do
    if [ -f "$COMFYUI_DIR/$venv_name/bin/activate" ]; then
        echo "✅ Activating VENV: $venv_name"
        source "$COMFYUI_DIR/$venv_name/bin/activate"
        VENV_FOUND=true
        break
    fi
done

if [ "$VENV_FOUND" = false ]; then
    echo "⚠️  WARNING: No VENV found. Using System Python."
else
    # .venv-cu128 우선 사용 (깔끔한 접근)
    echo "🔍 Checking .venv-cu128 packages..."

    # venv 패키지 확인
    VENV_PACKAGES_OK=""
    # ComfyUI requires torchsde for k-diffusion samplers; missing it will crash ComfyUI at startup.
    python -c "import torch, einops, torchsde; from PIL import Image; print('venv packages OK')" 2>/dev/null && VENV_PACKAGES_OK="yes"

    if [ -n "$VENV_PACKAGES_OK" ]; then
        echo "✅ .venv-cu128 is ready - using venv packages"
        echo "🎉 Fast startup with complete venv!"
    else
        echo "❌ .venv-cu128 incomplete - installing to venv..."
        echo "📦 Installing packages to .venv-cu128..."
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet
        pip install einops Pillow numpy scipy --quiet
        pip install huggingface_hub transformers diffusers accelerate --quiet
        pip install torchsde --quiet

        echo "🔍 Verifying venv installation..."
        python -c "
import torch, einops
import torchsde
from PIL import Image
print(f'✅ Torch {torch.__version__} installed (CUDA: {torch.cuda.is_available()})')
print('✅ einops installed')
print('✅ PIL installed')
print('✅ torchsde installed')
print('🎉 .venv-cu128 ready!')
" || {
            echo "❌ Installation failed"
            exit 1
        }
    fi
fi

# 5. ComfyUI 백그라운드 실행
echo "🚀 Starting ComfyUI Server...."
python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch &
COMFYUI_PID=$!
echo "📊 ComfyUI PID: $COMFYUI_PID"

# 잠시 기다렸다가 상태 확인
sleep 3
if kill -0 $COMFYUI_PID 2>/dev/null; then
    echo "✅ ComfyUI started successfully (PID: $COMFYUI_PID)"
else
    echo "❌ ComfyUI failed to start"
    exit 1
fi

# 6. 부팅 대기 (10초)
echo "⏳ Waiting 10s for boot..."
sleep 10

# 6.1 ComfyUI 실제 HTTP 응답 확인 (프로세스는 살아있어도 import 에러로 곧 죽을 수 있음)
echo "🔍 Verifying ComfyUI HTTP endpoint (http://127.0.0.1:8188/)..."
COMFY_HTTP_OK=""
for i in $(seq 1 30); do
    # Use stdlib only (urllib) so it works even if requests isn't installed in venv.
    python - <<'PY' 2>/dev/null && COMFY_HTTP_OK="yes" && break
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8188/", timeout=2).read()
print("ok")
PY

    # Also bail early if the process already died
    if ! kill -0 "$COMFYUI_PID" 2>/dev/null; then
        echo "❌ ComfyUI process exited during boot wait."
        break
    fi
    echo "…not ready yet ($i/30)"
    sleep 1
done

if [ -z "$COMFY_HTTP_OK" ]; then
    echo "❌ ComfyUI HTTP not reachable; refusing to start handler."
    echo "🔎 Showing last 200 lines from ComfyUI stdout (if available in container logs)."
    exit 1
fi
echo "✅ ComfyUI HTTP is reachable."

# 7. 핸들러 실행
echo "🚀 Starting RunPod Handler..."
python -u /handler.py