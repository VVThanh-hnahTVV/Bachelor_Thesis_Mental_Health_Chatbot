"""Chest X-ray multi-label screening via TorchXRayVision."""

from __future__ import annotations

import logging

import numpy as np
import skimage.io
import torch
import torchxrayvision as xrv
import torchvision

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n**Lưu ý:** Đây chỉ là kết quả sàng lọc từ AI, không phải chẩn đoán y khoa. "
    "Bác sĩ cần xem lại phim và hỏi thêm triệu chứng."
)

_PLAIN_LABELS: dict[str, str] = {
    "Atelectasis": "Xẹp một phần phổi",
    "Consolidation": "Vùng phổi đặc/mờ (có thể do viêm)",
    "Infiltration": "Vùng phổi bị thâm nhiễm/mờ",
    "Pneumothorax": "Nghi ngờ tràn khí màng phổi",
    "Edema": "Nghi ngờ phù phổi",
    "Emphysema": "Dấu hiệu khí phế thũng",
    "Fibrosis": "Dấu hiệu xơ phổi",
    "Effusion": "Có thể có dịch quanh phổi",
    "Pneumonia": "Gợi ý viêm phổi",
    "Pleural_Thickening": "Màng phổi dày hơn bình thường",
    "Cardiomegaly": "Tim có vẻ to hơn bình thường",
    "Nodule": "Nốt/nhú nhỏ bất thường trên phổi",
    "Mass": "Khối bất thường trên phổi",
    "Hernia": "Hình ảnh bất thường vùng cơ hoành",
    "Lung Lesion": "Tổn thương trên phổi",
    "Fracture": "Nghi ngờ gãy xương",
    "Lung Opacity": "Phổi có vùng mờ bất thường",
    "Enlarged Cardiomediastinum": "Vùng tim/trung thất có vẻ to",
}

_MAX_FINDINGS_SHOWN = 5


class TorchXRayVisionClassifier:
    def __init__(
        self,
        weights: str = "densenet121-res224-all",
        threshold: float = 0.5,
        device: torch.device | None = None,
    ) -> None:
        self.weights = weights
        self.fallback_threshold = threshold
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        logger.info(
            "Loading TorchXRayVision model weights=%s device=%s",
            weights,
            self.device,
        )
        self.model = xrv.models.DenseNet(weights=weights)
        self.model = self.model.to(self.device)
        self.model.eval()
        self.transform = torchvision.transforms.Compose([
            xrv.datasets.XRayCenterCrop(),
            xrv.datasets.XRayResizer(224),
        ])
        self._pathology_thresholds = self._build_threshold_map()

    def _build_threshold_map(self) -> dict[str, float]:
        thresholds: dict[str, float] = {}
        op_threshs = getattr(self.model, "op_threshs", None)
        pathologies = list(self.model.pathologies)
        if op_threshs is not None:
            arr = np.asarray(op_threshs).flatten()
            for i, name in enumerate(pathologies):
                if i < len(arr) and not np.isnan(arr[i]):
                    thresholds[name] = float(arr[i])
        return thresholds

    def _threshold_for(self, pathology: str) -> float:
        return self._pathology_thresholds.get(pathology, self.fallback_threshold)

    def _preprocess(self, image_path: str) -> torch.Tensor:
        img = skimage.io.imread(image_path)
        img = xrv.datasets.normalize(img, 255)
        if img.ndim == 3:
            img = img.mean(2)
        img = img[None, ...]
        img = self.transform(img)
        return torch.from_numpy(img).unsqueeze(0).to(self.device)

    def predict_scores(self, image_path: str) -> dict[str, float]:
        tensor = self._preprocess(image_path)
        with torch.no_grad():
            outputs = self.model(tensor).cpu().numpy()[0]
        return {
            name: float(score)
            for name, score in zip(self.model.pathologies, outputs)
        }

    def predict(self, image_path: str) -> str:
        try:
            scores = self.predict_scores(image_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Chest X-ray inference failed: %s", exc)
            return (
                "Không đọc được ảnh X-quang này. "
                "Bạn thử gửi lại ảnh rõ hơn (phim ngực thẳng, đủ sáng)."
                + _DISCLAIMER
            )

        flagged: list[tuple[str, float, float]] = []
        for name, score in scores.items():
            thresh = self._threshold_for(name)
            if score >= thresh:
                flagged.append((name, score, thresh))

        flagged.sort(key=lambda x: x[1], reverse=True)

        if flagged:
            count = len(flagged)
            if count >= 4:
                intro = (
                    f"AI thấy phim X-quang có **{count} dấu hiệu cần chú ý**. "
                    "Khi báo nhiều mục cùng lúc, thường là ảnh khó đọc hoặc một vùng "
                    "khiến AI gắn nhiều nhãn — **chưa chắc** là mắc nhiều bệnh riêng biệt.\n\n"
                    "Các điểm AI nghi ngờ mạnh nhất:\n"
                )
            else:
                intro = "AI thấy phim X-quang có các dấu hiệu sau:\n\n"

            shown = flagged[:_MAX_FINDINGS_SHOWN]
            lines = [
                f"- **{_PLAIN_LABELS.get(name, name)}** — AI khá chắc ({score:.0%})"
                if score >= 0.55
                else f"- **{_PLAIN_LABELS.get(name, name)}** — AI hơi nghi ngờ ({score:.0%})"
                for name, score, _thresh in shown
            ]
            extra = ""
            if count > _MAX_FINDINGS_SHOWN:
                extra = (
                    f"\n\n_…và {count - _MAX_FINDINGS_SHOWN} dấu hiệu khác. "
                    "Hỏi mình \"giải thích chi tiết\" nếu bạn muốn xem đầy đủ._"
                )
            body = intro + "\n".join(lines) + extra
        else:
            top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            lines = [
                f"- {_PLAIN_LABELS.get(name, name)} ({score:.0%})"
                for name, score in top
            ]
            body = (
                "AI **không phát hiện** dấu hiệu bất thường rõ trên phim này.\n\n"
                "Một vài chỉ số cao nhất (vẫn dưới ngưỡng cảnh báo):\n"
                + "\n".join(lines)
            )

        return body + _DISCLAIMER
