from .image_classifier import ImageClassifier
from .chest_xray_agent.torchxrayvision_inference import TorchXRayVisionClassifier
from .brain_tumor_agent.brain_tumor_inference import BrainTumorAgent
from .skin_lesion_agent.skin_lesion_inference import SkinLesionClassifier

class ImageAnalysisAgent:
    """
    Agent responsible for processing image uploads and classifying them as medical or non-medical, and determining their type.
    """
    
    def __init__(self, config):
        self.image_classifier = ImageClassifier(vision_model=config.medical_cv.llm)
        self.chest_xray_agent = TorchXRayVisionClassifier(
            weights=config.medical_cv.chest_xray_weights,
            threshold=config.medical_cv.chest_xray_threshold,
        )
        self.brain_tumor_agent = BrainTumorAgent(
            model_path=config.medical_cv.brain_tumor_model_path,
            overlay_output_path=config.medical_cv.brain_tumor_overlay_output_path,
        )
        self.skin_lesion_agent = SkinLesionClassifier(
            model_path=config.medical_cv.skin_lesion_model_path,
            overlay_output_path=config.medical_cv.skin_lesion_segmentation_output_path,
        )
        self.skin_lesion_overlay_output_path = config.medical_cv.skin_lesion_segmentation_output_path
    
    # classify image
    def analyze_image(self, image_path: str) -> str:
        """Classifies images as medical or non-medical and determines their type."""
        return self.image_classifier.classify_image(image_path)
    
    # chest x-ray agent
    def classify_chest_xray(self, image_path: str) -> str:
        return self.chest_xray_agent.predict(image_path)
    
    def classify_brain_tumor(self, image_path: str) -> str:
        return self.brain_tumor_agent.predict(image_path)
    
    def classify_skin_lesion(self, image_path: str) -> str:
        return self.skin_lesion_agent.predict(image_path, self.skin_lesion_overlay_output_path)
