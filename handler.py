import runpod
from runpod.serverless.utils import rp_upload
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
import websocket
import uuid
import tempfile
import socket
import traceback

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Websocket reconnection behaviour (can be overridden through environment variables)
# NOTE: more attempts and diagnostics improve debuggability whenever ComfyUI crashes mid-job.
#   • WEBSOCKET_RECONNECT_ATTEMPTS sets how many times we will try to reconnect.
#   • WEBSOCKET_RECONNECT_DELAY_S sets the sleep in seconds between attempts.
#
# If the respective env-vars are not supplied we fall back to sensible defaults ("5" and "3").
WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))

# Extra verbose websocket trace logs (set WEBSOCKET_TRACE=true to enable)
if os.environ.get("WEBSOCKET_TRACE", "false").lower() == "true":
    # This prints low-level frame information to stdout which is invaluable for diagnosing
    # protocol errors but can be noisy in production – therefore gated behind an env-var.
    websocket.enableTrace(True)

# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"
# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

# Default workflow for video generation with nudity removal and WAN video creation
DEFAULT_WORKFLOW = {
    "63": {
      "inputs": {
        "frame_rate": [
          "457",
          0
        ],
        "loop_count": 0,
        "filename_prefix": "video/%date:yyyy-MM-dd%/%date:hhmmss%",
        "format": "video/h265-mp4",
        "pix_fmt": "yuv420p10le",
        "crf": [
          "458",
          0
        ],
        "save_metadata": false,
        "pingpong": false,
        "save_output": true,
        "images": [
          "709",
          0
        ]
      },
      "class_type": "VHS_VideoCombine",
      "_meta": {
        "title": "Video Combine 🎥🅥🅗🅢"
      }
    },
    "419": {
      "inputs": {
        "ckpt_name": "DasiwaWAN22I2V14BLightspeedV7_midnightflirtHighV7.safetensors"
      },
      "class_type": "CheckpointLoaderSimple",
      "_meta": {
        "title": "Load Checkpoint High"
      }
    },
    "420": {
      "inputs": {
        "ckpt_name": "DasiwaWAN22I2V14BLightspeedV7_midnightflirtLowV7.safetensors"
      },
      "class_type": "CheckpointLoaderSimple",
      "_meta": {
        "title": "Load Checkpoint Low"
      }
    },
    "421": {
      "inputs": {
        "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "type": "wan",
        "device": "default"
      },
      "class_type": "CLIPLoader",
      "_meta": {
        "title": "CLIP 로드"
      }
    },
    "422": {
      "inputs": {
        "PowerLoraLoaderHeaderWidget": {
          "type": "PowerLoraLoaderHeaderWidget"
        },
        "lora_1": {
          "on": false,
          "lora": "NSFW-22-L-e8.safetensors",
          "strength": 1.2
        },
        "lora_2": {
          "on": true,
          "lora": "I2V-WAN2.2-EdibleAnus-LowNoise-1.1_-000060.safetensors",
          "strength": 1
        },
        "lora_3": {
          "on": false,
          "lora": "PussyLoRA_LowNoise_Wan2.2_HearmemanAI.safetensors",
          "strength": 1
        },
        "lora_4": {
          "on": false,
          "lora": "Wan22_CumV2_Low.safetensors",
          "strength": 1
        },
        "➕ Add Lora": "",
        "model": [
          "716",
          0
        ]
      },
      "class_type": "Power Lora Loader (rgthree)",
      "_meta": {
        "title": "Power Lora Loader (rgthree)"
      }
    },
    "425": {
      "inputs": {
        "shift": 5,
        "model": [
          "436",
          0
        ]
      },
      "class_type": "ModelSamplingSD3",
      "_meta": {
        "title": "Sigma Shift High"
      }
    },
    "426": {
      "inputs": {
        "shift": 5,
        "model": [
          "422",
          0
        ]
      },
      "class_type": "ModelSamplingSD3",
      "_meta": {
        "title": "Sigma Shift Low"
      }
    },
    "436": {
      "inputs": {
        "PowerLoraLoaderHeaderWidget": {
          "type": "PowerLoraLoaderHeaderWidget"
        },
        "lora_1": {
          "on": false,
          "lora": "NSFW-22-H-e8.safetensors",
          "strength": 1.2
        },
        "lora_2": {
          "on": true,
          "lora": "I2V-WAN2.2-EdibleAnus-HighNoise-1.1_-000050.safetensors",
          "strength": 1
        },
        "lora_3": {
          "on": false,
          "lora": "PussyLoRA_HighNoise_Wan2.2_HearmemanAI.safetensors",
          "strength": 1
        },
        "lora_4": {
          "on": false,
          "lora": "Wan22_CumV2_High.safetensors",
          "strength": 1
        },
        "➕ Add Lora": "",
        "model": [
          "715",
          0
        ]
      },
      "class_type": "Power Lora Loader (rgthree)",
      "_meta": {
        "title": "Power Lora Loader (rgthree)"
      }
    },
    "446": {
      "inputs": {
        "value": 1
      },
      "class_type": "PrimitiveFloat",
      "_meta": {
        "title": "CFG"
      }
    },
    "447": {
      "inputs": {
        "value": 2
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "Step to swap"
      }
    },
    "449": {
      "inputs": {
        "text": "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
        "clip": [
          "421",
          0
        ]
      },
      "class_type": "CLIPTextEncode",
      "_meta": {
        "title": "Negative (standard WAN)"
      }
    },
    "451": {
      "inputs": {
        "text": "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形deformed hands, deformed fingers, extra fingers, missing fingers, fused fingers, mutated hands, bad anatomy, unnatural entry, sudden appearance, jerky motion, penis in mouth, oral contact的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走, futanari, dickgirl, futanari penis, female with penis, hermaphrodite, intersex, shemale, ladyboy, dual genitalia, penis on female, balls on woman, male genitals on female, extra penis, gender mix, transgender genitalia, newhalf, trap penis",
        "clip": [
          "421",
          0
        ]
      },
      "class_type": "CLIPTextEncode",
      "_meta": {
        "title": "Negative"
      }
    },
    "452": {
      "inputs": {
        "text": "First-person POV scene with a nude woman (main character from reference), realistic proportions, detailed anatomy. She starts standing facing the camera directly, full body visible in wide shot, seductive smile with intense eye contact. Slowly and teasingly turns around to face away from the camera, hips swaying gently. Then gradually bends forward at the waist, arching her back, spreading legs slightly for balance, explicitly revealing and showing her visible genitals and anus from behind in close-up detail as she bends deeper. Hands on knees or thighs for support, head turned slightly to look back at camera with playful or inviting expression if visible. Smooth slow motion, natural lighting, bedroom setting, high detail anatomy and skin texture, face not obscured or covered, 15-20 seconds. drip water from pussy",
        "clip": [
          "421",
          0
        ]
      },
      "class_type": "CLIPTextEncode",
      "_meta": {
        "title": "CLIP 텍스트 인코딩 (프롬프트)"
      }
    },
    "455": {
      "inputs": {
        "vae_name": "wan_2.1_vae.safetensors"
      },
      "class_type": "VAELoader",
      "_meta": {
        "title": "VAE 로드"
      }
    },
    "457": {
      "inputs": {
        "value": 16
      },
      "class_type": "PrimitiveFloat",
      "_meta": {
        "title": "FPS"
      }
    },
    "458": {
      "inputs": {
        "value": 19
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "CRF"
      }
    },
    "470": {
      "inputs": {
        "seed": -1
      },
      "class_type": "Seed (rgthree)",
      "_meta": {
        "title": "Seed (rgthree)"
      }
    },
    "524": {
      "inputs": {
        "value": 113
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "Frames"
      }
    },
    "534": {
      "inputs": {
        "value": 560
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "Width - start resolution"
      }
    },
    "535": {
      "inputs": {
        "value": 720
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "Height - start resolution"
      }
    },
    "570": {
      "inputs": {
        "value": 4
      },
      "class_type": "PrimitiveInt",
      "_meta": {
        "title": "Steps_total"
      }
    },
    "621": {
      "inputs": {
        "any_01": [
          "687",
          0
        ]
      },
      "class_type": "Any Switch (rgthree)",
      "_meta": {
        "title": "Any Switch (rgthree)"
      }
    },
    "644": {
      "inputs": {
        "options": "Intermediate and Utility",
        "filenames": [
          "63",
          0
        ]
      },
      "class_type": "VHS_PruneOutputs",
      "_meta": {
        "title": "Prune Outputs 🎥🅥🅗🅢"
      }
    },
    "652": {
      "inputs": {
        "nag_scale": 11,
        "nag_alpha": 0.25,
        "nag_tau": 2.373,
        "input_type": "default",
        "model": [
          "426",
          0
        ],
        "conditioning": [
          "654",
          0
        ]
      },
      "class_type": "WanVideoNAG",
      "_meta": {
        "title": "WanVideoNAG Low"
      }
    },
    "653": {
      "inputs": {
        "nag_scale": 11,
        "nag_alpha": 0.25,
        "nag_tau": 2.373,
        "input_type": "default",
        "model": [
          "425",
          0
        ],
        "conditioning": [
          "654",
          0
        ]
      },
      "class_type": "WanVideoNAG",
      "_meta": {
        "title": "WanVideoNAG High"
      }
    },
    "654": {
      "inputs": {
        "conditioning_to": [
          "449",
          0
        ],
        "conditioning_from": [
          "451",
          0
        ]
      },
      "class_type": "ConditioningConcat",
      "_meta": {
        "title": "조건 (연결)"
      }
    },
    "684": {
      "inputs": {
        "width": 1280,
        "height": 1280,
        "resize_mode": "Keep AR",
        "divisible_by": 16,
        "max_batch_size": 3,
        "sinc_window": 3,
        "pad_color": "0, 0, 0",
        "crop_position": "center",
        "precision": "fp32",
        "image": [
          "763",
          0
        ]
      },
      "class_type": "BatchResizeWithLanczos",
      "_meta": {
        "title": "🐇 Batch Resize w/ Lanczos"
      }
    },
    "685": {
      "inputs": {
        "width": [
          "534",
          0
        ],
        "height": [
          "535",
          0
        ],
        "length": [
          "524",
          0
        ],
        "batch_size": 1,
        "positive": [
          "452",
          0
        ],
        "negative": [
          "451",
          0
        ],
        "vae": [
          "455",
          0
        ],
        "start_image": [
          "684",
          0
        ]
      },
      "class_type": "WanImageToVideo",
      "_meta": {
        "title": "WAN 비디오 생성 (이미지 → 비디오)"
      }
    },
    "686": {
      "inputs": {
        "add_noise": "disable",
        "noise_seed": [
          "470",
          0
        ],
        "steps": [
          "570",
          0
        ],
        "cfg": [
          "446",
          0
        ],
        "sampler_name": "euler",
        "scheduler": "simple",
        "start_at_step": [
          "447",
          0
        ],
        "end_at_step": 10000,
        "return_with_leftover_noise": "disable",
        "model": [
          "652",
          0
        ],
        "positive": [
          "685",
          0
        ],
        "negative": [
          "685",
          1
        ],
        "latent_image": [
          "688",
          0
        ]
      },
      "class_type": "KSamplerAdvanced",
      "_meta": {
        "title": "KSampler (Low)"
      }
    },
    "687": {
      "inputs": {
        "samples": [
          "686",
          0
        ],
        "vae": [
          "455",
          0
        ]
      },
      "class_type": "VAEDecode",
      "_meta": {
        "title": "VAE 디코드"
      }
    },
    "688": {
      "inputs": {
        "add_noise": "enable",
        "noise_seed": [
          "470",
          0
        ],
        "steps": [
          "570",
          0
        ],
        "cfg": [
          "446",
          0
        ],
        "sampler_name": "euler",
        "scheduler": "simple",
        "start_at_step": 0,
        "end_at_step": [
          "447",
          0
        ],
        "return_with_leftover_noise": "enable",
        "model": [
          "653",
          0
        ],
        "positive": [
          "685",
          0
        ],
        "negative": [
          "685",
          1
        ],
        "latent_image": [
          "685",
          2
        ]
      },
      "class_type": "KSamplerAdvanced",
      "_meta": {
        "title": "KSampler (High)"
      }
    },
    "709": {
      "inputs": {
        "width": [
          "710",
          0
        ],
        "height": [
          "711",
          0
        ],
        "resize_mode": "Keep AR",
        "divisible_by": 16,
        "max_batch_size": 3,
        "sinc_window": 3,
        "pad_color": "0, 0, 0",
        "crop_position": "center",
        "precision": "fp32",
        "image": [
          "621",
          0
        ]
      },
      "class_type": "BatchResizeWithLanczos",
      "_meta": {
        "title": "🐇 Batch Resize w/ Lanczos"
      }
    },
    "710": {
      "inputs": {
        "a": [
          "534",
          0
        ],
        "b": 2,
        "operation": "multiply"
      },
      "class_type": "easy mathInt",
      "_meta": {
        "title": "Math width"
      }
    },
    "711": {
      "inputs": {
        "a": [
          "535",
          0
        ],
        "b": 2,
        "operation": "multiply"
      },
      "class_type": "easy mathInt",
      "_meta": {
        "title": "Math height"
      }
    },
    "715": {
      "inputs": {
        "any_01": [
          "419",
          0
        ]
      },
      "class_type": "Any Switch (rgthree)",
      "_meta": {
        "title": "Any Switch (rgthree)"
      }
    },
    "716": {
      "inputs": {
        "any_01": [
          "420",
          0
        ]
      },
      "class_type": "Any Switch (rgthree)",
      "_meta": {
        "title": "Any Switch (rgthree)"
      }
    },
    "728": {
      "inputs": {
        "image": "input_image.png"
      },
      "class_type": "LoadImage",
      "_meta": {
        "title": "이미지 로드"
      }
    },
    "743": {
      "inputs": {
        "images": [
          "763",
          0
        ]
      },
      "class_type": "PreviewImage",
      "_meta": {
        "title": "이미지 미리보기"
      }
    },
    "759": {
      "inputs": {
        "strength": 1,
        "model": [
          "760",
          0
        ]
      },
      "class_type": "CFGNorm",
      "_meta": {
        "title": "CFGNorm"
      }
    },
    "760": {
      "inputs": {
        "shift": 3,
        "model": [
          "777",
          0
        ]
      },
      "class_type": "ModelSamplingAuraFlow",
      "_meta": {
        "title": "모델 샘플링 (AuraFlow)"
      }
    },
    "761": {
      "inputs": {
        "pixels": [
          "765",
          0
        ],
        "vae": [
          "775",
          0
        ]
      },
      "class_type": "VAEEncode",
      "_meta": {
        "title": "VAE 인코드"
      }
    },
    "762": {
      "inputs": {
        "prompt": "clothes, clothing, underwear, lingerie, bikini, swimsuit, bra, panties, shirt, dress, pants, fabric on body, covered genitals, censored, mosaic, bars, pixelated, blurred nudity, partial clothing, accessories covering body, deformed face, altered face, changed expression, background change, new background elements, pose change, cropped body, partial view, low quality, artifacts",
        "clip": [
          "776",
          0
        ],
        "vae": [
          "775",
          0
        ],
        "image1": [
          "765",
          0
        ]
      },
      "class_type": "TextEncodeQwenImageEditPlus",
      "_meta": {
        "title": "TextEncodeQwenImageEditPlus"
      }
    },
    "763": {
      "inputs": {
        "samples": [
          "764",
          0
        ],
        "vae": [
          "775",
          0
        ]
      },
      "class_type": "VAEDecode",
      "_meta": {
        "title": "VAE 디코드"
      }
    },
    "764": {
      "inputs": {
        "seed": 926020317898849,
        "steps": 4,
        "cfg": 1,
        "sampler_name": "euler",
        "scheduler": "simple",
        "denoise": 1,
        "model": [
          "759",
          0
        ],
        "positive": [
          "767",
          0
        ],
        "negative": [
          "762",
          0
        ],
        "latent_image": [
          "761",
          0
        ]
      },
      "class_type": "KSampler",
      "_meta": {
        "title": "KSampler"
      }
    },
    "765": {
      "inputs": {
        "upscale_method": "area",
        "megapixels": 1,
        "image": [
          "728",
          0
        ]
      },
      "class_type": "ImageScaleToTotalPixels",
      "_meta": {
        "title": "총 픽셀 수에 맞춰 이미지 크기 조정"
      }
    },
    "767": {
      "inputs": {
        "prompt": "Edit the existing image precisely: Keep the main character's face, expression, features, makeup, hair, and head angle exactly the same as the original. Preserve the entire original background 100% unchanged - no alterations, additions, or removals. Maintain the exact same pose, body position, arm placement, stance, and camera angle as the original.\n\nRemove all clothing completely from the character, revealing full nudity with realistic skin continuing seamlessly underneath where clothes were. No clothing, underwear, accessories, or any fabric remains on the body. Ultra-detailed skin texture, pores, natural body contours, consistent lighting and shadows from the original image, photorealistic, high resolution, no artifacts on skin.",
        "clip": [
          "776",
          0
        ],
        "vae": [
          "775",
          0
        ],
        "image1": [
          "765",
          0
        ]
      },
      "class_type": "TextEncodeQwenImageEditPlus",
      "_meta": {
        "title": "TextEncodeQwenImageEditPlus"
      }
    },
    "775": {
      "inputs": {
        "vae_name": "qwen_image_vae.safetensors"
      },
      "class_type": "VAELoader",
      "_meta": {
        "title": "VAE 로드"
      }
    },
    "776": {
      "inputs": {
        "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "type": "qwen_image",
        "device": "default"
      },
      "class_type": "CLIPLoader",
      "_meta": {
        "title": "CLIP 로드"
      }
    },
    "777": {
      "inputs": {
        "lora_name": "Qwen-Edit-2509-Multiple-angles.safetensors",
        "strength_model": 1,
        "model": [
          "778",
          0
        ]
      },
      "class_type": "LoraLoaderModelOnly",
      "_meta": {
        "title": "LoRA 로드 (모델 전용)"
      }
    },
    "778": {
      "inputs": {
        "lora_name": "Qwen_Snofs_1_3.safetensors",
        "strength_model": 0.7,
        "model": [
          "779",
          0
        ]
      },
      "class_type": "LoraLoaderModelOnly",
      "_meta": {
        "title": "LoRA 로드 (모델 전용)"
      }
    },
    "779": {
      "inputs": {
        "lora_name": "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
        "strength_model": 1,
        "model": [
          "780",
          0
        ]
      },
      "class_type": "LoraLoaderModelOnly",
      "_meta": {
        "title": "LoRA 로드 (모델 전용)"
      }
    },
    "780": {
      "inputs": {
        "unet_name": "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
        "weight_dtype": "default"
      },
      "class_type": "UNETLoader",
      "_meta": {
        "title": "확산 모델 로드"
      }
    }
}

# ---------------------------------------------------------------------------
# Helper: quick reachability probe of ComfyUI HTTP endpoint (port 8188)
# ---------------------------------------------------------------------------


def _comfy_server_status():
    """Return a dictionary with basic reachability info for the ComfyUI HTTP server."""
    try:
        resp = requests.get(f"http://{COMFY_HOST}/", timeout=5)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def _attempt_websocket_reconnect(ws_url, max_attempts, delay_s, initial_error):
    """
    Attempts to reconnect to the WebSocket server after a disconnect.

    Args:
        ws_url (str): The WebSocket URL (including client_id).
        max_attempts (int): Maximum number of reconnection attempts.
        delay_s (int): Delay in seconds between attempts.
        initial_error (Exception): The error that triggered the reconnect attempt.

    Returns:
        websocket.WebSocket: The newly connected WebSocket object.

    Raises:
        websocket.WebSocketConnectionClosedException: If reconnection fails after all attempts.
    """
    print(
        f"worker-comfyui - Websocket connection closed unexpectedly: {initial_error}. Attempting to reconnect..."
    )
    last_reconnect_error = initial_error
    for attempt in range(max_attempts):
        # Log current server status before each reconnect attempt so that we can
        # see whether ComfyUI is still alive (HTTP port 8188 responding) even if
        # the websocket dropped. This is extremely useful to differentiate
        # between a network glitch and an outright ComfyUI crash/OOM-kill.
        srv_status = _comfy_server_status()
        if not srv_status["reachable"]:
            # If ComfyUI itself is down there is no point in retrying the websocket –
            # bail out immediately so the caller gets a clear "ComfyUI crashed" error.
            print(
                f"worker-comfyui - ComfyUI HTTP unreachable – aborting websocket reconnect: {srv_status.get('error', 'status '+str(srv_status.get('status_code')))}"
            )
            raise websocket.WebSocketConnectionClosedException(
                "ComfyUI HTTP unreachable during websocket reconnect"
            )

        # Otherwise we proceed with reconnect attempts while server is up
        print(
            f"worker-comfyui - Reconnect attempt {attempt + 1}/{max_attempts}... (ComfyUI HTTP reachable, status {srv_status.get('status_code')})"
        )
        try:
            # Need to create a new socket object for reconnect
            new_ws = websocket.WebSocket()
            new_ws.connect(ws_url, timeout=10)  # Use existing ws_url
            print(f"worker-comfyui - Websocket reconnected successfully.")
            return new_ws  # Return the new connected socket
        except (
            websocket.WebSocketException,
            ConnectionRefusedError,
            socket.timeout,
            OSError,
        ) as reconn_err:
            last_reconnect_error = reconn_err
            print(
                f"worker-comfyui - Reconnect attempt {attempt + 1} failed: {reconn_err}"
            )
            if attempt < max_attempts - 1:
                print(
                    f"worker-comfyui - Waiting {delay_s} seconds before next attempt..."
                )
                time.sleep(delay_s)
            else:
                print(f"worker-comfyui - Max reconnection attempts reached.")

    # If loop completes without returning, raise an exception
    print("worker-comfyui - Failed to reconnect websocket after connection closed.")
    raise websocket.WebSocketConnectionClosedException(
        f"Connection closed and failed to reconnect. Last error: {last_reconnect_error}"
    )


def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input - use default if not provided
    workflow = job_input.get("workflow")
    if workflow is None:
        print("worker-comfyui - No workflow provided, using default video generation workflow")
        workflow = DEFAULT_WORKFLOW.copy()

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # If using default workflow and images are provided, update the LoadImage node
    if workflow is DEFAULT_WORKFLOW and images and len(images) > 0:
        # Update the LoadImage node (728) to use the first uploaded image
        # The image will be uploaded and available as the first image's name
        if "728" in workflow:
            workflow["728"]["inputs"]["image"] = images[0]["name"]
            print(f"worker-comfyui - Updated default workflow to use input image: {images[0]['name']}")

    # Return validated data and no error
    return {"workflow": workflow, "images": images}, None


def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 50
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 500

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """

    print(f"worker-comfyui - Checking API server at {url}...")
    for i in range(retries):
        try:
            response = requests.get(url, timeout=5)

            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                print(f"worker-comfyui - API is reachable")
                return True
        except requests.Timeout:
            pass
        except requests.RequestException as e:
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"worker-comfyui - Failed to connect to server at {url} after {retries} attempts."
    )
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.

    Returns:
        dict: A dictionary indicating success or error.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"worker-comfyui - Uploading {len(images)} image(s)...")

    for image in images:
        try:
            name = image["name"]
            image_data_uri = image["image"]  # Get the full string (might have prefix)

            # --- Strip Data URI prefix if present ---
            if "," in image_data_uri:
                # Find the comma and take everything after it
                base64_data = image_data_uri.split(",", 1)[1]
            else:
                # Assume it's already pure base64
                base64_data = image_data_uri
            # --- End strip ---

            blob = base64.b64decode(base64_data)  # Decode the cleaned data

            # Prepare the form data
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }

            # POST request to upload the image
            response = requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=30
            )
            response.raise_for_status()

            responses.append(f"Successfully uploaded {name}")
            print(f"worker-comfyui - Successfully uploaded {name}")

        except base64.binascii.Error as e:
            error_msg = f"Error decoding base64 for {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.Timeout:
            error_msg = f"Timeout uploading {image.get('name', 'unknown')}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.RequestException as e:
            error_msg = f"Error uploading {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except Exception as e:
            error_msg = (
                f"Unexpected error uploading {image.get('name', 'unknown')}: {e}"
            )
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)

    if upload_errors:
        print(f"worker-comfyui - image(s) upload finished with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"worker-comfyui - image(s) upload complete")
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def get_available_models():
    """
    Get list of available models from ComfyUI

    Returns:
        dict: Dictionary containing available models by type
    """
    try:
        response = requests.get(f"http://{COMFY_HOST}/object_info", timeout=10)
        response.raise_for_status()
        object_info = response.json()

        # Extract available checkpoints from CheckpointLoaderSimple
        available_models = {}
        if "CheckpointLoaderSimple" in object_info:
            checkpoint_info = object_info["CheckpointLoaderSimple"]
            if "input" in checkpoint_info and "required" in checkpoint_info["input"]:
                ckpt_options = checkpoint_info["input"]["required"].get("ckpt_name")
                if ckpt_options and len(ckpt_options) > 0:
                    available_models["checkpoints"] = (
                        ckpt_options[0] if isinstance(ckpt_options[0], list) else []
                    )

        return available_models
    except Exception as e:
        print(f"worker-comfyui - Warning: Could not fetch available models: {e}")
        return {}


def queue_workflow(workflow, client_id):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed
        client_id (str): The client ID for the websocket connection

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow

    Raises:
        ValueError: If the workflow validation fails with detailed error information
    """
    # Include client_id in the prompt payload
    payload = {"prompt": workflow, "client_id": client_id}
    data = json.dumps(payload).encode("utf-8")

    # Use requests for consistency and timeout
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"http://{COMFY_HOST}/prompt", data=data, headers=headers, timeout=30
    )

    # Handle validation errors with detailed information
    if response.status_code == 400:
        print(f"worker-comfyui - ComfyUI returned 400. Response body: {response.text}")
        try:
            error_data = response.json()
            print(f"worker-comfyui - Parsed error data: {error_data}")

            # Try to extract meaningful error information
            error_message = "Workflow validation failed"
            error_details = []

            # ComfyUI seems to return different error formats, let's handle them all
            if "error" in error_data:
                error_info = error_data["error"]
                if isinstance(error_info, dict):
                    error_message = error_info.get("message", error_message)
                    if error_info.get("type") == "prompt_outputs_failed_validation":
                        error_message = "Workflow validation failed"
                else:
                    error_message = str(error_info)

            # Check for node validation errors in the response
            if "node_errors" in error_data:
                for node_id, node_error in error_data["node_errors"].items():
                    if isinstance(node_error, dict):
                        for error_type, error_msg in node_error.items():
                            error_details.append(
                                f"Node {node_id} ({error_type}): {error_msg}"
                            )
                    else:
                        error_details.append(f"Node {node_id}: {node_error}")

            # Check if the error data itself contains validation info
            if error_data.get("type") == "prompt_outputs_failed_validation":
                error_message = error_data.get("message", "Workflow validation failed")
                # For this type of error, we need to parse the validation details from logs
                # Since ComfyUI doesn't seem to include detailed validation errors in the response
                # Let's provide a more helpful generic message
                available_models = get_available_models()
                if available_models.get("checkpoints"):
                    error_message += f"\n\nThis usually means a required model or parameter is not available."
                    error_message += f"\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                else:
                    error_message += "\n\nThis usually means a required model or parameter is not available."
                    error_message += "\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(error_message)

            # If we have specific validation errors, format them nicely
            if error_details:
                detailed_message = f"{error_message}:\n" + "\n".join(
                    f"• {detail}" for detail in error_details
                )

                # Try to provide helpful suggestions for common errors
                if any(
                    "not in list" in detail and "ckpt_name" in detail
                    for detail in error_details
                ):
                    available_models = get_available_models()
                    if available_models.get("checkpoints"):
                        detailed_message += f"\n\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                    else:
                        detailed_message += "\n\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(detailed_message)
            else:
                # Fallback to the raw response if we can't parse specific errors
                raise ValueError(f"{error_message}. Raw response: {response.text}")

        except (json.JSONDecodeError, KeyError) as e:
            # If we can't parse the error response, fall back to the raw text
            raise ValueError(
                f"ComfyUI validation failed (could not parse error response): {response.text}"
            )

    # For other HTTP errors, raise them normally
    response.raise_for_status()
    return response.json()


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    # Use requests for consistency and timeout
    response = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_image_data(filename, subfolder, image_type):
    """
    Fetch image bytes from the ComfyUI /view endpoint.

    Args:
        filename (str): The filename of the image.
        subfolder (str): The subfolder where the image is stored.
        image_type (str): The type of the image (e.g., 'output').

    Returns:
        bytes: The raw image data, or None if an error occurs.
    """
    print(
        f"worker-comfyui - Fetching image data: type={image_type}, subfolder={subfolder}, filename={filename}"
    )
    data = {"filename": filename, "subfolder": subfolder, "type": image_type}
    url_values = urllib.parse.urlencode(data)
    try:
        # Use requests for consistency and timeout
        response = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=60)
        response.raise_for_status()
        print(f"worker-comfyui - Successfully fetched image data for {filename}")
        return response.content
    except requests.Timeout:
        print(f"worker-comfyui - Timeout fetching image data for {filename}")
        return None
    except requests.RequestException as e:
        print(f"worker-comfyui - Error fetching image data for {filename}: {e}")
        return None
    except Exception as e:
        print(
            f"worker-comfyui - Unexpected error fetching image data for {filename}: {e}"
        )
        return None


def handler(job):
    """
    Handles a job using ComfyUI via websockets for status and image retrieval.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    job_input = job["input"]
    job_id = job["id"]

    # Make sure that the input is valid
    validated_data, error_message = validate_input(job_input)
    if error_message:
        return {"error": error_message}

    # Extract validated data
    workflow = validated_data["workflow"]
    input_images = validated_data.get("images")

    # Make sure that the ComfyUI HTTP API is available before proceeding
    if not check_server(
        f"http://{COMFY_HOST}/",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    ):
        return {
            "error": f"ComfyUI server ({COMFY_HOST}) not reachable after multiple retries."
        }

    # Upload input images if they exist
    if input_images:
        upload_result = upload_images(input_images)
        if upload_result["status"] == "error":
            # Return upload errors
            return {
                "error": "Failed to upload one or more input images",
                "details": upload_result["details"],
            }

    ws = None
    client_id = str(uuid.uuid4())
    prompt_id = None
    output_data = []
    errors = []

    try:
        # Establish WebSocket connection
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"
        print(f"worker-comfyui - Connecting to websocket: {ws_url}")
        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=10)
        print(f"worker-comfyui - Websocket connected")

        # Queue the workflow
        try:
            queued_workflow = queue_workflow(workflow, client_id)
            prompt_id = queued_workflow.get("prompt_id")
            if not prompt_id:
                raise ValueError(
                    f"Missing 'prompt_id' in queue response: {queued_workflow}"
                )
            print(f"worker-comfyui - Queued workflow with ID: {prompt_id}")
        except requests.RequestException as e:
            print(f"worker-comfyui - Error queuing workflow: {e}")
            raise ValueError(f"Error queuing workflow: {e}")
        except Exception as e:
            print(f"worker-comfyui - Unexpected error queuing workflow: {e}")
            # For ValueError exceptions from queue_workflow, pass through the original message
            if isinstance(e, ValueError):
                raise e
            else:
                raise ValueError(f"Unexpected error queuing workflow: {e}")

        # Wait for execution completion via WebSocket
        print(f"worker-comfyui - Waiting for workflow execution ({prompt_id})...")
        execution_done = False
        while True:
            try:
                out = ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message.get("type") == "status":
                        status_data = message.get("data", {}).get("status", {})
                        print(
                            f"worker-comfyui - Status update: {status_data.get('exec_info', {}).get('queue_remaining', 'N/A')} items remaining in queue"
                        )
                    elif message.get("type") == "executing":
                        data = message.get("data", {})
                        if (
                            data.get("node") is None
                            and data.get("prompt_id") == prompt_id
                        ):
                            print(
                                f"worker-comfyui - Execution finished for prompt {prompt_id}"
                            )
                            execution_done = True
                            break
                    elif message.get("type") == "execution_error":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            error_details = f"Node Type: {data.get('node_type')}, Node ID: {data.get('node_id')}, Message: {data.get('exception_message')}"
                            print(
                                f"worker-comfyui - Execution error received: {error_details}"
                            )
                            errors.append(f"Workflow execution error: {error_details}")
                            break
                else:
                    continue
            except websocket.WebSocketTimeoutException:
                print(f"worker-comfyui - Websocket receive timed out. Still waiting...")
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                try:
                    # Attempt to reconnect
                    ws = _attempt_websocket_reconnect(
                        ws_url,
                        WEBSOCKET_RECONNECT_ATTEMPTS,
                        WEBSOCKET_RECONNECT_DELAY_S,
                        closed_err,
                    )

                    print(
                        "worker-comfyui - Resuming message listening after successful reconnect."
                    )
                    continue
                except (
                    websocket.WebSocketConnectionClosedException
                ) as reconn_failed_err:
                    # If _attempt_websocket_reconnect fails, it raises this exception
                    # Let this exception propagate to the outer handler's except block
                    raise reconn_failed_err

            except json.JSONDecodeError:
                print(f"worker-comfyui - Received invalid JSON message via websocket.")

        if not execution_done and not errors:
            raise ValueError(
                "Workflow monitoring loop exited without confirmation of completion or error."
            )

        # Fetch history even if there were execution errors, some outputs might exist
        print(f"worker-comfyui - Fetching history for prompt {prompt_id}...")
        history = get_history(prompt_id)

        if prompt_id not in history:
            error_msg = f"Prompt ID {prompt_id} not found in history after execution."
            print(f"worker-comfyui - {error_msg}")
            if not errors:
                return {"error": error_msg}
            else:
                errors.append(error_msg)
                return {
                    "error": "Job processing failed, prompt ID not found in history.",
                    "details": errors,
                }

        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})

        if not outputs:
            warning_msg = f"No outputs found in history for prompt {prompt_id}."
            print(f"worker-comfyui - {warning_msg}")
            if not errors:
                errors.append(warning_msg)

        print(f"worker-comfyui - Processing {len(outputs)} output nodes...")
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['images'])} image(s)"
                )
                for image_info in node_output["images"]:
                    filename = image_info.get("filename")
                    subfolder = image_info.get("subfolder", "")
                    img_type = image_info.get("type")

                    # skip temp images
                    if img_type == "temp":
                        print(
                            f"worker-comfyui - Skipping image {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping image in node {node_id} due to missing filename: {image_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    image_bytes = get_image_data(filename, subfolder, img_type)

                    if image_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".png"

                        if os.environ.get("BUCKET_ENDPOINT_URL"):
                            try:
                                with tempfile.NamedTemporaryFile(
                                    suffix=file_extension, delete=False
                                ) as temp_file:
                                    temp_file.write(image_bytes)
                                    temp_file_path = temp_file.name
                                print(
                                    f"worker-comfyui - Wrote image bytes to temporary file: {temp_file_path}"
                                )

                                print(f"worker-comfyui - Uploading {filename} to S3...")
                                s3_url = rp_upload.upload_image(job_id, temp_file_path)
                                os.remove(temp_file_path)  # Clean up temp file
                                print(
                                    f"worker-comfyui - Uploaded {filename} to S3: {s3_url}"
                                )
                                # Append dictionary with filename and URL
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "s3_url",
                                        "data": s3_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = f"Error uploading {filename} to S3: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    try:
                                        os.remove(temp_file_path)
                                    except OSError as rm_err:
                                        print(
                                            f"worker-comfyui - Error removing temp file {temp_file_path}: {rm_err}"
                                        )
                        else:
                            # Return as base64 string
                            try:
                                base64_image = base64.b64encode(image_bytes).decode(
                                    "utf-8"
                                )
                                # Append dictionary with filename and base64 data
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_image,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch image data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # Check for other output types
            other_keys = [k for k in node_output.keys() if k != "images"]
            if other_keys:
                warn_msg = (
                    f"Node {node_id} produced unhandled output keys: {other_keys}."
                )
                print(f"worker-comfyui - WARNING: {warn_msg}")
                print(
                    f"worker-comfyui - --> If this output is useful, please consider opening an issue on GitHub to discuss adding support."
                )

    except websocket.WebSocketException as e:
        print(f"worker-comfyui - WebSocket Error: {e}")
        print(traceback.format_exc())
        return {"error": f"WebSocket communication error: {e}"}
    except requests.RequestException as e:
        print(f"worker-comfyui - HTTP Request Error: {e}")
        print(traceback.format_exc())
        return {"error": f"HTTP communication error with ComfyUI: {e}"}
    except ValueError as e:
        print(f"worker-comfyui - Value Error: {e}")
        print(traceback.format_exc())
        return {"error": str(e)}
    except Exception as e:
        print(f"worker-comfyui - Unexpected Handler Error: {e}")
        print(traceback.format_exc())
        return {"error": f"An unexpected error occurred: {e}"}
    finally:
        if ws and ws.connected:
            print(f"worker-comfyui - Closing websocket connection.")
            ws.close()

    final_result = {}

    if output_data:
        final_result["images"] = output_data

    if errors:
        final_result["errors"] = errors
        print(f"worker-comfyui - Job completed with errors/warnings: {errors}")

    if not output_data and errors:
        print(f"worker-comfyui - Job failed with no output images.")
        return {
            "error": "Job processing failed",
            "details": errors,
        }
    elif not output_data and not errors:
        print(
            f"worker-comfyui - Job completed successfully, but the workflow produced no images."
        )
        final_result["status"] = "success_no_images"
        final_result["images"] = []

    print(f"worker-comfyui - Job completed. Returning {len(output_data)} image(s).")
    return final_result


if __name__ == "__main__":
    print("worker-comfyui - Starting handler...")
    runpod.serverless.start({"handler": handler})
