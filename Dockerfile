# RunPod 공식 베이스 이미지 (Python, CUDA 세팅됨)
# CUDA 12.8.1 - PyTorch cu121/cu126 호환됨
FROM runpod/base:1.0.3-cuda1281-ubuntu2404
    
# 1. ComfyUI 구동에 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 2. RunPod 핸들러용 기본 라이브러리 설치
# .venv-cu128를 우선 사용하므로 최소한만 설치
RUN pip install --no-cache-dir \
    runpod \
    requests \
    websocket-client

# 3. 파일 복사
# (로컬에 있는 start.sh와 handler.py를 이미지 안으로 넣음)
COPY start.sh /start.sh
COPY handler.py /handler.py

# 4. 권한 설정 및 윈도우 줄바꿈 제거 (필수!)
RUN sed -i 's/\r$//' /start.sh && chmod +x /start.sh
RUN sed -i 's/\r$//' /handler.py && chmod +x /handler.py

# 5. 시작 명령어 (핸들러만 실행하면 안 되고, start.sh를 실행해야 함)
CMD ["/start.sh"]