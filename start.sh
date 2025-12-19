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
    # 가상환경에서 필수 패키지 설치 상태 확인 (재설치는 최소화)
    echo "🔍 Checking ComfyUI venv packages..."

    # 필수 패키지들 확인 및 설치
    echo "🔍 Checking for PIL/Pillow..."
    python -c "from PIL import Image; print('✅ PIL available')" 2>/dev/null || {
        echo "❌ PIL not found in venv, installing..."
        pip install Pillow
    }

    # ComfyUI-Manager 등 custom nodes에서 자주 사용하는 패키지들
    echo "🔍 Checking for huggingface_hub..."
    python -c "import huggingface_hub; print('✅ huggingface_hub available')" 2>/dev/null || {
        echo "❌ huggingface_hub not found, installing..."
        pip install huggingface_hub
    }

    echo "🔍 Checking for other common packages..."
    python -c "import transformers, diffusers, accelerate; print('✅ ML packages available')" 2>/dev/null || {
        echo "❌ Some ML packages missing, installing..."
        pip install transformers diffusers accelerate
    }

    # ComfyUI의 torch/cuda 버전 확인 (필수 패키지)
    echo "🔍 Checking torch installation..."
    if python -c "import torch; print(f'✅ Torch {torch.__version__} available, CUDA: {torch.cuda.is_available()}')" 2>/dev/null; then
        echo "✅ Torch ready - no installation needed"
    else
        echo "⚠️  Torch not found in .venv-cu128"
        echo "💡 This venv might be incomplete. Consider reinstalling ComfyUI with proper dependencies."
        echo "🔄 Attempting minimal torch install..."
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet
        python -c "import torch; print(f'✅ Torch {torch.__version__} installed')" || {
            echo "❌ Torch installation failed - ComfyUI cannot run without torch"
            exit 1
        }
    fi
fi

# 5. ComfyUI 백그라운드 실행
echo "🚀 Starting ComfyUI Server...."
python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch &

# 6. 부팅 대기 (10초)
echo "⏳ Waiting 10s for boot..."
sleep 10

# 7. 핸들러 실행
echo "🚀 Starting RunPod Handler..."
python -u /handler.py