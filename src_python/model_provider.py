"""Unified Model Provider Abstraction

Amaç:
  - LM Studio (HTTP /v1/chat/completions)
  - llama.cpp local server (same OpenAI style)
  - Ollama (HTTP /api/chat) veya /api/generate
  - Statik GGUF dosyasını doğrudan llama-cpp-python üzerinden yükleyip RAM içi inference

Notlar:
  - Vision (Qwen VL) için image + text birlikte gönderme desteği.
  - Fallback sırası: llama-cpp (in-process) -> LM Studio -> Ollama.
  - Konfigürasyon .env / settings.json üzerinden.
"""

from typing import List, Dict, Optional
import os
import base64
import json
import requests
from pathlib import Path

try:
    from llama_cpp import Llama  # optional
except Exception:
    Llama = None

from logger import logger


class ModelProvider:
    def __init__(self,
                 model_name: Optional[str] = None,
                 backend_preference: Optional[List[str]] = None,
                 vision_enabled: bool = True):
        self.model_name = model_name or os.getenv("LLM_MODEL", "Qwen3-VL-8B-Instruct-GGUF")
        self.backend_preference = backend_preference or [
            "llama_cpp", "lmstudio", "ollama"
        ]
        self.vision_enabled = vision_enabled

        # Environment / config
        self.lmstudio_base = os.getenv("LM_STUDIO_IP", "http://localhost:1234")
        if not self.lmstudio_base.endswith("/v1"):
            self.lmstudio_base = self.lmstudio_base.rstrip("/") + "/v1"  # Ensure /v1 suffix
        self.ollama_base = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.gguf_path = os.getenv("GGUF_MODEL_PATH", "models/" + self.model_name + ".gguf")

        self.active_backend = None
        self.llama_instance = None

        self._auto_init()

    def _auto_init(self):
        for backend in self.backend_preference:
            try:
                if backend == "llama_cpp" and self._init_llama_cpp():
                    self.active_backend = backend
                    logger.info(f"Model backend seçildi: {backend}")
                    return
                if backend == "lmstudio" and self._check_lmstudio():
                    self.active_backend = backend
                    logger.info(f"Model backend seçildi: {backend}")
                    return
                if backend == "ollama" and self._check_ollama():
                    self.active_backend = backend
                    logger.info(f"Model backend seçildi: {backend}")
                    return
            except Exception as e:
                logger.warning(f"Backend init error ({backend}): {e}")

        logger.error("Hiçbir backend aktif hale getirilemedi. İnference başarısız olabilir.")

    def _init_llama_cpp(self) -> bool:
        if Llama is None:
            return False
        path = Path(self.gguf_path)
        if not path.exists():
            return False
        try:
            self.llama_instance = Llama(
                model_path=str(path),
                n_ctx=4096,
                logits_all=False,
                n_threads=int(os.getenv("LLAMA_THREADS", "8")),
                verbose=False
            )
            return True
        except Exception as e:
            logger.warning(f"llama.cpp yükleme hatası: {e}")
            return False

    def _check_lmstudio(self) -> bool:
        try:
            r = requests.get(f"{self.lmstudio_base}/v1/models", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _check_ollama(self) -> bool:
        try:
            r = requests.get(f"{self.ollama_base}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # PUBLIC INFERENCE API
    # ------------------------------------------------------------------
    def chat(self,
             messages: List[Dict],
             images: Optional[List[bytes]] = None,
             max_tokens: int = 512,
             temperature: float = 0.1) -> str:
        if self.active_backend == "llama_cpp":
            return self._chat_llama_cpp(messages)
        if self.active_backend == "lmstudio":
            return self._chat_lmstudio(messages, images, max_tokens, temperature)
        if self.active_backend == "ollama":
            return self._chat_ollama(messages, images, max_tokens, temperature)
        raise RuntimeError("Hiçbir backend aktif değil.")

    # llama-cpp: sadece text (vision yok / Qwen VL görüntü desteği kısıtlı)
    def _chat_llama_cpp(self, messages: List[Dict]) -> str:
        if not self.llama_instance:
            raise RuntimeError("llama.cpp instance yok")
        prompt = self._openai_messages_to_prompt(messages)
        out = self.llama_instance(prompt=prompt, max_tokens=512, temperature=0.1)
        return out.get("choices", [{}])[0].get("text", "") if isinstance(out, dict) else str(out)

    def _openai_messages_to_prompt(self, messages: List[Dict]) -> str:
        lines = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # vision content + text (llama.cpp'de sadece text'e indirgeme)
                text_parts = []
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n".join(text_parts)
            lines.append(f"[{role.upper()}]\n{content}\n")
        return "\n".join(lines)

    def _chat_lmstudio(self,
                       messages: List[Dict],
                       images: Optional[List[bytes]],
                       max_tokens: int,
                       temperature: float) -> str:
        # OpenAI-style
        lm_msgs = []
        for m in messages:
            lm_content = []
            if isinstance(m.get("content"), list):
                for part in m["content"]:
                    if part.get("type") == "text":
                        lm_content.append({"type": "text", "text": part["text"]})
                    elif part.get("type") in ("image", "image_url") and self.vision_enabled:
                        lm_content.append(part)
            else:
                lm_content = m.get("content")
            lm_msgs.append({"role": m.get("role", "user"), "content": lm_content})

        # Ekstra görüntü varsa ekle (kullanıcı sadece bytes yolladıysa)
        if images:
            b64_images = [base64.b64encode(im).decode() for im in images]
            for b64 in b64_images:
                lm_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    }]
                })

        payload = {
            "model": self.model_name,
            "messages": lm_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        try:
            r = requests.post(f"{self.lmstudio_base}/chat/completions", json=payload, timeout=90)
            r.raise_for_status()
            result = r.json()
            
            # Debug: Log response structure if choices missing
            if "choices" not in result or len(result["choices"]) == 0:
                logger.error(f"LM Studio unexpected response format: {result}")
                raise KeyError("Response missing 'choices' key or empty choices array")
            
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            # Better timeout messaging
            error_msg = str(e)
            if "Read timed out" in error_msg or "timeout" in error_msg.lower():
                logger.error(f"⏱️ LM Studio timeout (90s) - Model: {self.model_name}. Check if model is loaded and GPU is available.")
            else:
                logger.error(f"LM Studio request failed: {e}")
            raise RuntimeError(f"LM Studio request failed: {e}")

    def _chat_ollama(self,
                      messages: List[Dict],
                      images: Optional[List[bytes]],
                      max_tokens: int,
                      temperature: float) -> str:
        # Ollama vision desteği sınırlı; text fallback
        prompt_parts = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        prompt_parts.append(part.get("text", ""))
            else:
                prompt_parts.append(str(content))
        prompt = "\n".join(prompt_parts)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        r = requests.post(f"{self.ollama_base}/api/generate", json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")


def quick_test():
    provider = ModelProvider()
    resp = provider.chat([
        {"role": "system", "content": [{"type": "text", "text": "You are a contract parser."}]},
        {"role": "user", "content": [{"type": "text", "text": "Extract parties from: This Agreement between Telenity and ABC Mobile."}]}
    ])
    print("RESPONSE:\n", resp)


if __name__ == "__main__":
    try:
        quick_test()
    except Exception as e:
        print("Model provider test failed:", e)