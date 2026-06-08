"""HAM10000 skin lesion classification via EfficientNet-B0 + Grad-CAM overlay."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import timm
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

from .model_download import ensure_model_checkpoint

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n**Lưu ý:** Đây chỉ là kết quả sàng lọc từ AI trên ảnh da/dermoscopy, "
    "không phải chẩn đoán y khoa. Bạn nên đi khám bác sĩ da liễu để soi dermoscopy "
    "và sinh thiết nếu cần."
)

# Standard HAM10000 label order (alphabetical by class folder name).
_CLASS_NAMES = ("akiec", "bcc", "bkl", "df", "mel", "nv", "vasc")

_PLAIN_LABELS: dict[str, str] = {
    "akiec": "Dày sừng sun / tổn thương tiền ung thư da (AKIEC)",
    "bcc": "Ung thư tế bào đáy (BCC)",
    "bkl": "Tổn thương da lành tính kiểu sừng (BKL)",
    "df": "U xơ da (dermatofibroma)",
    "mel": "Melanoma (ung thư da đen)",
    "nv": "Nốt ruồi melanocytic (thường lành tính)",
    "vasc": "Tổn thương mạch máu da",
}

_HIGH_RISK = frozenset({"mel", "bcc", "akiec"})

_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class SkinLesionClassifier:
    """Classify dermoscopic skin lesions on HAM10000 taxonomy."""

    def __init__(self, model_path: str, overlay_output_path: str) -> None:
        self.model_path = model_path
        self.overlay_output_path = overlay_output_path
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model()

    def _load_model(self) -> torch.nn.Module:
        weights_path = ensure_model_checkpoint(self.model_path)
        model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=7)
        state = torch.load(weights_path, map_location=self.device, weights_only=False)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state)
        model = model.to(self.device)
        model.eval()
        logger.info("HAM10000 EfficientNet-B0 loaded from %s on %s", weights_path, self.device)
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
        return _CLASS_NAMES[best_idx], float(probs[best_idx]), scores

    def _grad_cam(self, tensor: torch.Tensor, target_idx: int, rgb: np.ndarray) -> np.ndarray:
        activations: list[torch.Tensor] = []
        gradients: list[torch.Tensor] = []
        target_layer = self.model.blocks[-1]

        def forward_hook(_module, _inputs, output) -> None:
            activations.append(output)

        def backward_hook(_module, _grad_input, grad_output) -> None:
            gradients.append(grad_output[0])

        handle_f = target_layer.register_forward_hook(forward_hook)
        handle_b = target_layer.register_full_backward_hook(backward_hook)
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
            return (cam_np - cam_np.min()) / (cam_np.max() - cam_np.min() + 1e-8)
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
            logger.warning("Failed to save skin lesion Grad-CAM overlay: %s", exc)
            plt.close("all")
            return False

    def predict(self, image_path: str, output_path: str | None = None) -> str:
        overlay_path = output_path or self.overlay_output_path
        try:
            tensor, rgb = self._preprocess(image_path)
            best_name, confidence, scores = self._predict_probs(tensor)
        except Exception as exc:  # noqa: BLE001
            logger.error("Skin lesion inference failed: %s", exc)
            return (
                "Không đọc được ảnh tổn thương da này. "
                "Bạn thử gửi lại ảnh rõ hơn (dermoscopy hoặc ảnh cận vùng tổn thương)."
                + _DISCLAIMER
            )

        target_idx = _CLASS_NAMES.index(best_name)
        cam = self._grad_cam(tensor, target_idx, rgb)
        overlay_ok = self._save_overlay(rgb, cam, overlay_path)

        label = _PLAIN_LABELS.get(best_name, best_name)
        certainty = "AI khá chắc" if confidence >= 0.55 else "AI hơi nghi ngờ"

        if best_name in _HIGH_RISK:
            intro = (
                f"AI nghi ngờ **{label}** ({certainty}: {confidence:.0%}).\n\n"
                "Đây là nhóm cần **theo dõi hoặc khám da liễu sớm** — AI chỉ gợi ý sàng lọc.\n\n"
                "Xác suất từng nhóm HAM10000:\n"
            )
        else:
            intro = (
                f"AI thấy ảnh **gần với {label}** nhất ({certainty}: {confidence:.0%}).\n\n"
                "Xác suất từng nhóm HAM10000:\n"
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        lines = [
            f"- **{_PLAIN_LABELS.get(name, name)}** — {score:.0%}"
            for name, score in ranked
        ]
        body = intro + "\n".join(lines)

        if overlay_ok:
            body += (
                "\n\nẢnh heatmap bên dưới cho thấy vùng AI chú ý nhất (Grad-CAM) — "
                "chỉ mang tính tham khảo."
            )

        if best_name == "mel":
            body += (
                "\n\n**Melanoma** là ung thư da nguy hiểm; nếu bạn lo ngại, "
                "hãy đặt lịch khám da liễu càng sớm càng tốt."
            )

        return body + _DISCLAIMER
