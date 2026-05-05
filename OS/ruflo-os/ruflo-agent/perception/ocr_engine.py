from PIL import Image
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

class OCREngine:
    """Multi-engine OCR pipeline (EasyOCR + Tesseract)."""

    def __init__(self):
        self.easyocr_reader = None
        self.tesseract_available = False
        self._init_engines()

    def _init_engines(self):
        try:
            import easyocr
            self.easyocr_reader = easyocr.Reader(['en'])
            logger.info("EasyOCR initialized")
        except ImportError:
            logger.warning("EasyOCR not available")

        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self.tesseract_available = True
            logger.info("Tesseract available")
        except ImportError:
            logger.warning("pytesseract not available")

    def extract_text(self, image: Image.Image, region: Optional[tuple] = None) -> str:
        """Extract text from image or region."""
        if region:
            image = image.crop(region)

        text = ""
        # Try EasyOCR first
        if self.easyocr_reader:
            try:
                result = self.easyocr_reader.readtext(image)
                text = " ".join([res[1] for res in result])
                logger.info("EasyOCR text extracted", length=len(text))
                return text
            except Exception as e:
                logger.error("EasyOCR failed", error=str(e))

        # Fallback to Tesseract
        if self.tesseract_available:
            try:
                import pytesseract
                text = pytesseract.image_to_string(image)
                logger.info("Tesseract text extracted", length=len(text))
                return text
            except Exception as e:
                logger.error("Tesseract failed", error=str(e))

        return text

    def extract_text_with_boxes(self, image: Image.Image) -> list:
        """Extract text with bounding boxes."""
        if not self.easyocr_reader:
            return []
        try:
            result = self.easyocr_reader.readtext(image)
            return [
                {"text": res[1], "bbox": res[0], "confidence": res[2]}
                for res in result
            ]
        except Exception as e:
            logger.error("EasyOCR with boxes failed", error=str(e))
            return []