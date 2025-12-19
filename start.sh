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
fi

# 5. ComfyUI 백그라운드 실행
echo "🚀 Starting ComfyUI Server..."
python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch &

# 6. 부팅 대기 (10초)
echo "⏳ Waiting 10s for boot..."
sleep 10

# 7. 핸들러 실행
echo "🚀 Starting RunPod Handler..."
python -u /handler.py