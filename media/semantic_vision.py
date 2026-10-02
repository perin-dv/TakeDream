"""Real CLIP inference. Heavy imports and weights are loaded only on demand."""
import os
from pathlib import Path

from core.processing import ProcessingError, check_cancelled


DEFAULT_MODEL = "openai/clip-vit-base-patch32"
DEFAULT_REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
# These are visual descriptions, not filename rules or fabricated detections.
TAG_PROMPTS = {
    "bride_prep": "a bride getting ready for her wedding",
    "groom_prep": "a groom getting ready in a suit for his wedding",
    "makeup": "a makeup artist applying makeup to a bride's face",
    "hair": "a hairdresser styling a bride's hair",
    "dress_detail": "a close-up detail of a white wedding dress",
    "shoe_detail": "a close-up of wedding shoes",
    "bouquet_detail": "a close-up of a bridal bouquet of flowers",
    "ring_detail": "a close-up of wedding rings",
    "invitation_detail": "a close-up of a printed wedding invitation",
    "ceremony_wide": "a wide establishing view of a wedding ceremony and altar",
    "bride_entrance": "a bride walking down the aisle at a wedding",
    "groom_waiting": "a groom standing waiting at the altar",
    "vows": "a bride and groom speaking wedding vows to each other",
    "ring_exchange": "a bride and groom putting wedding rings on each other's fingers",
    "kiss": "a bride and groom kissing each other",
    "couple_praying": "a bride and groom praying together",
    "officiant": "a wedding officiant speaking alone at the altar",
    "applause": "wedding guests clapping their hands",
    "ceremony_exit": "a bride and groom leaving their wedding ceremony together",
    "couple_portrait": "a romantic portrait of a bride and groom together",
    "couple_closeup": "a close-up of the faces of a bride and groom together",
    "holding_hands": "a close-up of a bride and groom holding hands",
    "embrace": "a bride and groom embracing each other",
    "smiling_couple": "a bride and groom smiling together",
    "emotional_reaction": "a person crying tears of joy at a wedding",
    "party": "a wedding reception party with a crowd of guests",
    "dance": "people dancing at a wedding reception",
    "guests_reaction": "wedding guests watching the ceremony without the bride and groom",
    "family_moment": "a bride or groom hugging their family at a wedding",
    "children": "children playing at a wedding without the bride and groom",
    "decor_detail": "a close-up of wedding table decorations without people",
    "shaky_camera": "an unsteady tilted badly composed wedding video frame",
    "whip_pan": "a streaked wedding video frame during a fast camera pan",
    "motion_blur": "a blurry smeared wedding video frame",
    "low_value_frame": "an empty obstructed dark wedding video frame with no clear subject",
    "strong_closing_candidate": "a cinematic emotional final image of a bride and groom together",
    "strong_opening_candidate": "a beautifully composed cinematic establishing image of a wedding",
    "hero_shot_candidate": "a cinematic romantic portrait of a bride and groom in beautiful light",
}
BACKGROUND_PROMPTS = (
    "a photo unrelated to a wedding",
    "an empty black video frame",
    "an indistinct blurry image with no clear subject",
)


class CLIPVisionModel:
    def __init__(self, name=None, device=None, revision=None):
        self.name = name or os.getenv("TAKEDREAM_VISION_MODEL", DEFAULT_MODEL)
        self.device = device or os.getenv("TAKEDREAM_VISION_DEVICE", "cpu")
        self.revision = revision or os.getenv("TAKEDREAM_VISION_REVISION", DEFAULT_REVISION if self.name == DEFAULT_MODEL else "main")
        self._model = None

    @property
    def identity(self):
        return {"name": self.name, "device": self.device, "revision": self.revision,
                "backend": "transformers-clip", "scoring": "relative-softmax-v1"}

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
        except ImportError as error:
            raise ProcessingError("Visão semântica requer requirements-vision.txt. Instale as dependências de visão local.") from error
        try:
            self._torch = torch
            if self.device == "cpu":
                torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            options = {"revision": self.revision, "trust_remote_code": False}
            self._processor = CLIPProcessor.from_pretrained(self.name, use_fast=False, **options)
            model = CLIPModel.from_pretrained(self.name, **options).to(self.device).eval()
            prompts = [f"A photo of {text}." for text in TAG_PROMPTS.values()] + list(BACKGROUND_PROMPTS)
            tokens = self._processor(text=prompts, return_tensors="pt", padding=True).to(self.device)
            with torch.inference_mode():
                features = model.get_text_features(**tokens)
                self._text = features / features.norm(dim=-1, keepdim=True)
            self._resolved_revision = getattr(model.config, "_commit_hash", None)
            self._model = model
        except Exception as error:
            raise ProcessingError(f"Não foi possível carregar o modelo visual {self.name} em {self.device}: {error}") from error

    def analyze(self, frame_paths, *, cancel=None):
        check_cancelled(cancel)
        self._load()
        check_cancelled(cancel)
        from PIL import Image
        images = []
        try:
            for path in frame_paths:
                with Image.open(Path(path)) as image:
                    images.append(image.convert("RGB"))
            inputs = self._processor(images=images, return_tensors="pt").to(self.device)
            with self._torch.inference_mode():
                features = self._model.get_image_features(**inputs)
                features = features / features.norm(dim=-1, keepdim=True)
                similarities = features @ self._text.T
                # Relative support among prompts. It is NOT a calibrated probability.
                support = (similarities * 30.0).softmax(dim=-1).mean(dim=0)
                cosines = similarities.mean(dim=0)
                embedding = features.mean(dim=0)
                embedding = embedding / embedding.norm()
            check_cancelled(cancel)
            scores = {}
            for index, tag in enumerate(TAG_PROMPTS):
                # Scale relative support to useful [0,1] ranking strength while
                # requiring actual positive image/text similarity.
                score = min(1.0, float(support[index]) * 8.0)
                score *= max(0.0, min(1.0, (float(cosines[index]) - 0.12) / 0.12))
                scores[tag] = round(score, 4)
            return {"scores": scores, "embedding": [round(float(x), 6) for x in embedding.cpu().tolist()],
                    "resolved_revision": self._resolved_revision,
                    "background_score": round(float(support[-3:].sum()), 4)}
        finally:
            for image in images:
                image.close()
