import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
from urllib.parse import urlparse
from datetime import datetime
import requests
import fitz  # PyMuPDF
import uuid
import json
import tempfile
from typing import Dict, List, Any

class CertificateValidator:
    def __init__(self):
        self.known_watermarks = self._load_watermark_templates()
        self.certificate_hashes = set()
        self.template_similarity_threshold = 0.85
        self.duplicate_threshold = 0.95
        self.trusted_domains = ['coursera.org', 'edx.org', 'udemy.com']
        self.suspicious_software = ['canva', 'figma', 'paint', 'photoshop', 'gimp']

    def _load_watermark_templates(self) -> Dict[str, Any]:
        return {
            'coursera': {
                'logo_path': 'watermarks/coursera_logo.png',
                'positions': ['top_right', 'bottom_center'],
                'min_confidence': 0.75
            },
        }

    def process_document(self, file_path: str, output_dir: str = None) -> List[Dict]:
        if not os.path.exists(file_path):
            return [{'error': 'File not found', 'file_path': file_path}]
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        if file_path.lower().endswith('.pdf'):
            return self._process_pdf(file_path, output_dir)
        else:
            return [self.validate_certificate(file_path)]

    def _process_pdf(self, pdf_path: str, output_dir: str = None) -> List[Dict]:
        try:
            results: List[Dict] = []
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap()
                if output_dir:
                    image_path = os.path.join(output_dir, f'page_{page_num + 1}.png')
                    pix.save(image_path)
                    results.append(self.validate_certificate(image_path))
                else:
                    temp_path = os.path.join(tempfile.gettempdir(), f"cert_page_{uuid.uuid4().hex}.png")
                    pix.save(temp_path)
                    try:
                        results.append(self.validate_certificate(temp_path))
                    finally:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
            return results
        except Exception as e:
            return [{'error': f'PDF processing failed: {str(e)}', 'file_path': pdf_path}]

    def validate_certificate(self, image_path: str) -> Dict:
        results = {
            'file_path': image_path,
            'validation_steps': {},
            'authenticity_score': 0.0,
            'verification_status': 'unverified',
            'warnings': [],
            'anomalies': []
        }
        if not os.path.exists(image_path):
            results['error'] = 'Certificate file not found'
            return results

        # Preprocess
        preprocessed = self._preprocess_image(image_path)
        if isinstance(preprocessed, dict) and 'error' in preprocessed:
            results.update(preprocessed)
            return results

        # QR Validation
        qr_results = self.validate_qr_code(image_path)
        results['validation_steps']['qr_validation'] = qr_results

        # Metadata
        metadata = self.analyze_metadata(image_path)
        results['validation_steps']['metadata_analysis'] = metadata

        # Template Verification
        template_results = self.verify_template(image_path)
        results['validation_steps']['template_verification'] = template_results

        # Text Integrity
        text_results = self.check_text_integrity(image_path)
        results['validation_steps']['text_integrity'] = text_results

        # Duplicate check
        duplicate_check = self.check_duplicate(image_path)
        results['is_duplicate'] = duplicate_check['is_duplicate']
        results['validation_steps']['duplicate_check'] = duplicate_check

        # Score & status
        results['authenticity_score'] = self.calculate_authenticity_score(results)
        thresholds = {'verified': 0.85, 'review_needed': 0.6}
        if results['authenticity_score'] >= thresholds['verified']:
            results['verification_status'] = 'verified'
        elif results['authenticity_score'] >= thresholds['review_needed']:
            results['verification_status'] = 'review_needed'
        else:
            results['verification_status'] = 'likely_fake'

        results['summary'] = self.generate_summary(results)
        return results

    def _preprocess_image(self, image_path: str) -> np.ndarray:
        try:
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
            denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(denoised, -1, kernel)
            return sharpened
        except Exception as e:
            return {'error': f'Image preprocessing failed: {str(e)}'}

    def validate_qr_code(self, image_path: str) -> Dict:
        try:
            image = cv2.imread(image_path)
            detector = cv2.QRCodeDetector()
            ok, decoded_info, points, _ = detector.detectAndDecodeMulti(image)
            results = []
            if ok and decoded_info:
                for i, data in enumerate(decoded_info):
                    if not data:
                        continue
                    result = {'data': data}
                    if data.startswith(('http://', 'https://')):
                        url_val = self._validate_url(data)
                        result['url_validation'] = url_val
                        domain = urlparse(data).netloc
                        result['is_trusted_domain'] = any(t in domain for t in self.trusted_domains)
                    results.append(result)
            return {'valid': bool(results), 'found': bool(results), 'codes': results}
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    def _validate_url(self, url: str) -> Dict:
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return {'valid': False, 'error': 'Invalid URL'}
            response = requests.head(url, allow_redirects=True, timeout=10)
            final_url = response.url
            was_redirected = final_url != url
            return {'valid': 200 <= response.status_code < 400,
                    'final_url': final_url,
                    'was_redirected': was_redirected,
                    'status_code': response.status_code,
                    'is_https': parsed.scheme=='https'}
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    def analyze_metadata(self, image_path: str) -> Dict:
        results = {'file_info': {}, 'suspicious': {'has_editing_software': False, 'editing_software': []}}
        stat = os.stat(image_path)
        results['file_info'] = {'size_bytes': stat.st_size,
                                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                'file_type': os.path.splitext(image_path)[1].lower()}
        return results

    def verify_template(self, image_path: str) -> Dict:
        results = {'watermark_found': False, 'watermark_confidence': 0.0}
        # Skipping actual logo matching for simplicity
        return results

    def check_text_integrity(self, image_path: str) -> Dict:
        try:
            img = Image.open(image_path)
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confidences = [int(c) for c in ocr_data['conf'] if c.isdigit()]
            avg_conf = np.mean(confidences) if confidences else 0
            return {'average_confidence': avg_conf, 'ocr_blocks': len(confidences)}
        except Exception as e:
            return {'average_confidence': 0, 'error': str(e)}

    def check_duplicate(self, image_path: str) -> Dict:
        hash_val = self._calculate_image_hash(image_path)
        is_dup = hash_val in self.certificate_hashes
        self.certificate_hashes.add(hash_val)
        return {'is_duplicate': is_dup, 'hash': hash_val}

    def _calculate_image_hash(self, image_path: str, hash_size: int = 16) -> str:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        img = cv2.resize(img, (hash_size, hash_size))
        avg = img.mean()
        hash_bits = img > avg
        return ''.join(['1' if b else '0' for b in hash_bits.flatten()])

    def calculate_authenticity_score(self, results: Dict) -> float:
        score = 0
        score += 0.3 * (1.0 if results['validation_steps']['qr_validation'].get('valid') else 0)
        score += 0.2  # metadata placeholder
        score += 0.2 * results['validation_steps']['template_verification'].get('watermark_confidence',0)
        score += 0.15 * (results['validation_steps']['text_integrity'].get('average_confidence',0)/100)
        score += 0.15 * (0 if results.get('is_duplicate') else 1)
        return min(score,1.0)

    def generate_summary(self, results: Dict) -> str:
        lines = [f"Verification status: {results.get('verification_status')}",
                 f"Authenticity score: {results.get('authenticity_score'):.2f}"]
        qr = results['validation_steps'].get('qr_validation', {})
        lines.append(f"QR codes found: {len(qr.get('codes',[]))}")
        text = results['validation_steps'].get('text_integrity',{})
        lines.append(f"OCR average confidence: {text.get('average_confidence',0):.2f}")
        lines.append(f"Duplicate: {results.get('is_duplicate')}")
        return "\n".join(lines)
