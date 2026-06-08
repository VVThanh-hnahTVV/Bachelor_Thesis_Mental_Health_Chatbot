"""Brain MRI tumor screening via fine-tuned ResNet18 + Grad-CAM overlay."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.models as models
from PIL import Image
from torchvision import transforms

from .model_download import ensure_model_checkpoint

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n**Lưu ý:** Đây chỉ là kết quả sàng lọc từ AI trên **một lát cắt 2D**, "
    "không phải chẩn đoán y khoa. Bác sĩ chẩn đoán hình ảnh cần xem toàn bộ "
    "chuỗi MRI và hỏi thêm triệu chứng."
)

_CLASS_NAMES = ("glioma", "meningioma", "notumor", "pituitary")

_PLAIN_LABELS: dict[str, str] = {
    "glioma": "U glioma (tuyến thần kinh đệm)",
    "meningioma": "U màng não (meningioma)",
    "notumor": "Không phát hiện khối u rõ",
    "pituitary": "U tuyến yên (pituitary)",
}

_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class BrainTumorAgent:
    """Classify brain MRI slices and highlight suspicious regions with Grad-CAM."""

    def __init__(self, model_path: str, overlay_output_path: str) -> None:
        self.model_path = model_path
        self.overlay_output_path = overlay_output_path
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model()

    def _load_model(self) -> torch.nn.Module:
        weights_path = ensure_model_checkpoint(self.model_path)
        model = models.resnet18(weights=None)
        model.fc = torch.nn.Linear(model.fc.in_features, len(_CLASS_NAMES))
        state = torch.load(weights_path, map_location=self.device, weights_only=True)
        model.load_state_dict(state)
        model = model.to(self.device)
        model.eval()
        logger.info("Brain tumor model loaded from %s on %s", weights_path, self.device)
        return model

    def _preprocess(self, image_path: str) -> tuple[torch.Tensor, np.ndarray]:
        pil = Image.open(image_path).convert("RGB")
        rgb = np.array(pil)
        tensor = _TRANSFORM(pil).unsqueeze(0).to(self.device)
        return tensor, rgb

    def _predict_probs(self, tensor: torch.Tensor) -> tuple[str, float, dict[str, float]]:
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

        scores = {name: float(probs[i]) for i, name in enumerate(_CLASS_NAMES)}
        best_idx = int(np.argmax(probs))
        best_name = _CLASS_NAMES[best_idx]
        return best_name, float(probs[best_idx]), scores

    def _grad_cam(self, tensor: torch.Tensor, target_idx: int, rgb: np.ndarray) -> np.ndarray:
        activations: list[torch.Tensor] = []
        gradients: list[torch.Tensor] = []

        def forward_hook(_module, _inputs, output) -> None:
            activations.append(output)

        def backward_hook(_module, _grad_input, grad_output) -> None:
            gradients.append(grad_output[0])

        handle_f = self.model.layer4.register_forward_hook(forward_hook)
        handle_b = self.model.layer4.register_full_backward_hook(backward_hook)
        try:
            self.model.zero_grad(set_to_none=True)
            output = self.model(tensor)
            score = output[0, target_idx]
            score.backward()

            grads = gradients[0]
            fmaps = activations[0]
            weights = grads.mean(dim=(2, 3), keepdim=True)
            cam = (weights * fmaps).sum(dim=1, keepdim=True)
            cam = F.relu(cam)
            cam = F.interpolate(cam, size=(rgb.shape[0], rgb.shape[1]), mode="bilinear", align_corners=False)
            cam_np = cam.squeeze().detach().cpu().numpy()
            cam_np = (cam_np - cam_np.min()) / (cam_np.max() - cam_np.min() + 1e-8)
            return cam_np
        finally:
            handle_f.remove()
            handle_b.remove()

    def _save_overlay(self, rgb: np.ndarray, cam: np.ndarray, output_path: str) -> bool:
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            heatmap = plt.cm.jet(cam)[..., :3]
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.axis("off")
            ax.imshow(rgb)
            ax.imshow(heatmap, alpha=0.42)
            plt.savefig(out, bbox_inches="tight", pad_inches=0)
            plt.close(fig)
            return out.is_file()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save brain tumor Grad-CAM overlay: %s", exc)
            plt.close("all")
            return False

    def predict(self, image_path: str) -> str:
        try:
            tensor, rgb = self._preprocess(image_path)
            best_name, confidence, scores = self._predict_probs(tensor)
        except Exception as exc:  # noqa: BLE001
            logger.error("Brain MRI inference failed: %s", exc)
            return (
                "Không đọc được ảnh MRI này. "
                "Bạn thử gửi lại ảnh rõ hơn (lát cắt MRI não, đủ tương phản)."
                + _DISCLAIMER
            )

        target_idx = _CLASS_NAMES.index(best_name)
        cam = self._grad_cam(tensor, target_idx, rgb)
        overlay_ok = self._save_overlay(rgb, cam, self.overlay_output_path)

        label = _PLAIN_LABELS.get(best_name, best_name)
        if confidence >= 0.55:
            certainty = "AI khá chắc"
        else:
            certainty = "AI hơi nghi ngờ"

        if best_name == "notumor":
            intro = (
                f"AI **không thấy dấu hiệu khối u rõ** trên lát cắt MRI này ({certainty}: {confidence:.0%}).\n\n"
                "Các khả năng AI cân nhắc thêm:\n"
            )
        else:
            intro = (
                f"AI nghi ngờ **{label}** trên lát cắt MRI này ({certainty}: {confidence:.0%}).\n\n"
                "Xác suất từng nhóm:\n"
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        lines = [
            f"- **{_PLAIN_LABELS.get(name, name)}** — {score:.0%}"
            for name, score in ranked
        ]
        body = intro + "\n".join(lines)

        if overlay_ok and best_name != "notumor":
            body += (
                "\n\nẢnh bên dưới highlight vùng AI chú ý nhất (Grad-CAM) — "
                "chỉ mang tính tham khảo, không phải viền khối u chính xác."
            )
        elif overlay_ok:
            body += (
                "\n\nẢnh heatmap bên dưới cho thấy vùng AI tập trung khi đọc phim — "
                "không có nghĩa là phát hiện khối u."
            )

        return body + _DISCLAIMER
