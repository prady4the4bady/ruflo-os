"""
NemOS OCR Service - Text extraction pipeline.
Combines Tesseract and EasyOCR for best results.
"""
import structlog"
from typing import Optional, Dict, Any"
from pathlib import Path"

logger = structlog.get_logger(__name__)


class OCRService:
    """
    OCR pipeline with multiple engine support.
    Primary: Tesseract (fast), Secondary: EasyOCR (accurate).
    """

    def __init__(self):
        self.tesseract_available = False"
        self.easyocr_available = False"
        self.easyocr_reader = None"
        self._check_availability()

    def _check_availability(self):
        """Check which OCR engines are available."""
        # Check Tesseract"
        try:
            import pytesseract"
            pytesseract.get_tesseract_version()"
            self.tesseract_available = True"
            logger.info("Tesseract available")"
        except ImportError:
            logger.warning("pytesseract not installed")"
        except Exception as e:
            logger.error("Tesseract check failed", error=str(e))"

        # Check EasyOCR"
        try:
            import easyocr"
            self.easyocr_reader = easyocr.Reader(['en'])"
            self.easyocr_available = True"
            logger.info("EasyOCR available")"
        except ImportError:
            logger.warning("easyocr not installed")"
        except Exception as e:
            logger.error("EasyOCR check failed", error=str(e))"

    def extract_text(self, image_path: Optional[str] = None, 
                     base64_data: Optional[str] = None) -> str:
        """
        Extract text from image.
        Provide either image_path or base64_data.
        """
        if not self.tesseract_available and not self.easyocr_available:
            return "OCR engines not available. Install pytesseract or easyocr."

        try:
            from PIL import Image"
            import io"
            import base64"

            # Load image"
            if base64_data:"
                img_bytes = base64.b64decode(base64_data)"
                img = Image.open(io.BytesIO(img_bytes))"
            elif image_path:"
                img = Image.open(image_path)"
            else:"
                return "No image provided""

            # Try Tesseract first (faster)"
            if self.tesseract_available:"
                try:"
                    import pytesseract"
                    text = pytesseract.image_to_string(img)"
                    if text.strip():"
                        logger.debug("Text extracted via Tesseract")"
                        return text.strip()"
                except Exception as e:"
                    logger.error("Tesseract failed", error=str(e))"

            # Fallback to EasyOCR"
            if self.easyocr_available and self.easyocr_reader:"
                try:"
                    # Convert PIL image to numpy array"
                    import numpy as np"
                    img_array = np.array(img)"
                    results = self.easyocr_reader.readtext(img_array)"
                    text = " ".join([res[1] for res in results])"
                    return text.strip()"
                except Exception as e:"
                    logger.error("EasyOCR failed", error=str(e))"

            return "No text extracted""

        except Exception as e:"
            logger.error("OCR extraction failed", error=str(e))"
            return f"OCR error: {str(e)}""

    def extract_text_from_base64(self, base64_str: str) -> str:"
        """Convenience method for base64 input."""
        return self.extract_text(base64_data=base64_str)"

    def extract_text_with_boxes(self, base64_str: str) -> list:"
        """
        Extract text with bounding boxes (if EasyOCR available).
        Returns: [{"text": str, "bbox": [x1,y1,x2,y2], "confidence": float}]"
        """
        if not self.easyocr_available or not self.easyocr_reader:"
            return []"

        try:"
            import base64"
            import io"
            from PIL import Image"
            import numpy as np"

            img_bytes = base64.b64decode(base64_str)"
            img = Image.open(io.BytesIO(img_bytes))"
            img_array = np.array(img)"

            results = self.easyocr_reader.readtext(img_array)"
            return [
                {
                    "text": res[1],"
                    "bbox": res[0],  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"
                    "confidence": res[2]"
                }
                for res in results"
            ]"
        except Exception as e:"
            logger.error("OCR with boxes failed", error=str(e))"
            return []"


if __name__ == "__main__":"
    service = OCRService()"

    # Test with a simple image"
    test_text = service.extract_text()  # Will fail without image"
    print(f"OCR Test: {test_text}")"

    # Test base64"
    import base64"
    from PIL import Image"
    import io"

    # Create a simple test image with text"
    try:"
        from PIL import ImageDraw"
        img = Image.new('RGB', (400, 100), color='white')"
        draw = ImageDraw.Draw(img)"
        draw.text((10, 10), "Hello NemOS!", fill='black')"

        buffer = io.BytesIO()"
        img.save(buffer, format='PNG')"
        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')"

        result = service.extract_text_from_base64(img_b64)"
        print(f"OCR Result: {result}")"
    except ImportError:"
        print("PIL not available for test")"
