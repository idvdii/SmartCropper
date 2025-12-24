import os
import numpy as np
import onnxruntime as ort
from PIL import Image

class AIUpscaler:
    def __init__(self, model_path="4x-UltraSharp.onnx"):
        self.model_path = model_path
        self.session = None
        self.is_ready = False
        
        if os.path.exists(self.model_path):
            try:
                # 优先尝试 GPU 加速，没有则用 CPU
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                self.session = ort.InferenceSession(self.model_path, providers=providers)
                self.is_ready = True
                # === 修复：去掉 Emoji，改用普通字符防止报错 ===
                print(f"[OK] AI Model Loaded: {self.model_path}") 
            except Exception as e:
                # === 修复：去掉 Emoji ===
                print(f"[Error] Failed to load model: {e}")
                # 降级尝试纯 CPU
                try:
                    self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
                    self.is_ready = True
                    print(f"[Info] Fallback to CPU success")
                except:
                    pass
        else:
            # === 修复：去掉 Emoji ===
            print(f"[Error] Model not found: {self.model_path}")

    def process(self, pil_image):
        if not self.is_ready:
            return pil_image

        try:
            # 1. 预处理
            img = np.array(pil_image).astype(np.float32) / 255.0
            # 补齐 alpha 通道处理
            if img.ndim == 3 and img.shape[2] == 4:
                img = img[:, :, :3]
            # 兼容灰度图
            if img.ndim == 2:
                img = np.stack((img,)*3, axis=-1)
                
            img = img.transpose((2, 0, 1)) # HWC -> CHW
            img = np.expand_dims(img, axis=0) # Batch dimension

            # 2. 推理
            input_name = self.session.get_inputs()[0].name
            output = self.session.run(None, {input_name: img})[0]

            # 3. 后处理
            output = output.squeeze(0).transpose((1, 2, 0)) # CHW -> HWC
            output = np.clip(output * 255.0, 0, 255).astype(np.uint8)
            
            return Image.fromarray(output)
        except Exception as e:
            print(f"[Error] AI Processing failed: {e}")
            return pil_image

# 单例模式
_instance = None
def get_upscaler():
    global _instance
    if _instance is None:
        _instance = AIUpscaler()
    return _instance