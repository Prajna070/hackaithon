"""
AI-based Certificate Validation System
Analyzes uploaded documents to determine if they are valid certificates before processing
Supports multiple formats: PDF, JPG, PNG, DOCX
"""

import os
import cv2
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
import pickle
import pytesseract
from PIL import Image, ImageEnhance
import pdf2image
import io
import re
import json
from typing import Dict, List, Tuple, Any, Optional
import logging
from datetime import datetime

# For DOCX support
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Warning: python-docx not available. DOCX support disabled.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CertificateValidator:
    """AI-powered certificate validation system"""
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.model = None
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # Certificate indicators
        self.certificate_keywords = [
            'certificate', 'certified', 'completion', 'achievement', 'award', 'merit',
            'recognition', 'accomplishment', 'excellence', 'distinction', 'honor',
            'graduate', 'graduation', 'diploma', 'degree', 'course', 'training',
            'program', 'workshop', 'seminar', 'conference', 'certification',
            'licensed', 'qualified', 'professional', 'expert', 'master'
        ]
        
        self.institution_keywords = [
            'university', 'college', 'institute', 'academy', 'school', 'organization',
            'company', 'corporation', 'foundation', 'association', 'society',
            'department', 'faculty', 'center', 'bureau', 'agency', 'office'
        ]
        
        self.date_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # MM/DD/YYYY or MM-DD-YYYY
            r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',    # YYYY/MM/DD or YYYY-MM-DD
            r'\b\w+\s+\d{1,2},?\s+\d{4}\b',       # Month DD, YYYY
            r'\b\d{1,2}\s+\w+\s+\d{4}\b'          # DD Month YYYY
        ]
        
        self.name_patterns = [
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',      # First Last
            r'\b[A-Z]\.\s*[A-Z][a-z]+\b',          # Initial. Last
            r'\b[A-Z][a-z]+\s+[A-Z]\.\s*[A-Z][a-z]+\b'  # First Initial. Last
        ]
        
        if model_path and os.path.exists(model_path):
            self.load_model()
    
    def extract_text_from_image(self, image_path: str) -> str:
        """Extract text from image files using OCR"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return ""
            
            # Preprocess image for better OCR
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold to get better text extraction
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Denoise
            denoised = cv2.fastNlMeansDenoising(thresh)
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(denoised, config='--psm 6')
            
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from image: {e}")
            return ""
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF files"""
        try:
            # Convert PDF to images
            images = pdf2image.convert_from_path(pdf_path, dpi=200)
            text_content = []
            
            for image in images:
                # Convert PIL to OpenCV format
                open_cv_image = np.array(image)
                open_cv_image = open_cv_image[:, :, ::-1].copy()
                
                # Save temporarily and extract text
                temp_path = "temp_page.jpg"
                cv2.imwrite(temp_path, open_cv_image)
                text = self.extract_text_from_image(temp_path)
                text_content.append(text)
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            return " ".join(text_content)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""
    
    def extract_text_from_docx(self, docx_path: str) -> str:
        """Extract text from DOCX files"""
        if not DOCX_AVAILABLE:
            return ""
        
        try:
            doc = Document(docx_path)
            text_content = []
            
            for paragraph in doc.paragraphs:
                text_content.append(paragraph.text)
            
            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text_content.append(cell.text)
            
            return " ".join(text_content)
        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {e}")
            return ""
    
    def extract_text(self, file_path: str) -> str:
        """Extract text from various file formats"""
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            return self.extract_text_from_image(file_path)
        elif file_extension == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif file_extension == '.docx':
            return self.extract_text_from_docx(file_path)
        else:
            logger.warning(f"Unsupported file format: {file_extension}")
            return ""
    
    def analyze_certificate_indicators(self, text: str) -> Dict[str, Any]:
        """Analyze text for certificate-specific indicators"""
        text_lower = text.lower()
        
        indicators = {
            'certificate_keywords_found': [],
            'institution_keywords_found': [],
            'dates_found': [],
            'names_found': [],
            'certificate_score': 0,
            'document_type': 'unknown'
        }
        
        # Check for certificate keywords
        for keyword in self.certificate_keywords:
            if keyword in text_lower:
                indicators['certificate_keywords_found'].append(keyword)
        
        # Check for institution keywords
        for keyword in self.institution_keywords:
            if keyword in text_lower:
                indicators['institution_keywords_found'].append(keyword)
        
        # Find dates
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text)
            indicators['dates_found'].extend(matches)
        
        # Find potential names (look for capitalized words that could be names)
        for pattern in self.name_patterns:
            matches = re.findall(pattern, text)
            indicators['names_found'].extend(matches)
        
        # Calculate certificate score
        keyword_score = len(indicators['certificate_keywords_found']) * 2
        institution_score = len(indicators['institution_keywords_found']) * 1
        date_score = min(len(indicators['dates_found']) * 1, 3)  # Max 3 points for dates
        name_score = min(len(indicators['names_found']) * 0.5, 2)  # Max 2 points for names
        
        indicators['certificate_score'] = keyword_score + institution_score + date_score + name_score
        
        # Determine document type
        if indicators['certificate_score'] >= 5:
            indicators['document_type'] = 'certificate'
        elif indicators['certificate_score'] >= 3:
            indicators['document_type'] = 'likely_certificate'
        elif indicators['certificate_score'] >= 1:
            indicators['document_type'] = 'possibly_certificate'
        else:
            indicators['document_type'] = 'not_certificate'
        
        return indicators
    
    def analyze_document_structure(self, file_path: str) -> Dict[str, Any]:
        """Analyze document structure and layout"""
        file_extension = os.path.splitext(file_path)[1].lower()
        structure = {
            'has_header_footer': False,
            'has_signatures': False,
            'has_seals_logos': False,
            'has_official_elements': False,
            'layout_score': 0
        }
        
        if file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            structure.update(self._analyze_image_structure(file_path))
        elif file_extension == '.pdf':
            structure.update(self._analyze_pdf_structure(file_path))
        elif file_extension == '.docx':
            structure.update(self._analyze_docx_structure(file_path))
        
        return structure
    
    def _analyze_image_structure(self, image_path: str) -> Dict[str, Any]:
        """Analyze image structure for certificate elements"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return {}
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Look for signature-like elements (handwritten areas)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            signature_areas = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                # Signature-like areas are typically small and irregular
                if 100 < area < 2000:
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 0
                    if 2 < aspect_ratio < 10:  # Signature-like aspect ratio
                        signature_areas += 1
            
            # Look for seal/logo areas (circular or square elements)
            seal_areas = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if 500 < area < 10000:
                    approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
                    if len(approx) > 8:  # Complex shape (could be seal)
                        seal_areas += 1
            
            # Check for borders (common in certificates)
            height, width = gray.shape
            border_pixels_top = np.sum(gray[0:10, :] < 200)
            border_pixels_bottom = np.sum(gray[height-10:height, :] < 200)
            border_pixels_left = np.sum(gray[:, 0:10] < 200)
            border_pixels_right = np.sum(gray[:, width-10:width, :] < 200)
            
            has_border = (border_pixels_top > 100 or border_pixels_bottom > 100 or 
                         border_pixels_left > 100 or border_pixels_right > 100)
            
            return {
                'has_signatures': signature_areas > 0,
                'has_seals_logos': seal_areas > 0,
                'has_border': has_border,
                'signature_count': signature_areas,
                'seal_count': seal_areas
            }
        except Exception as e:
            logger.error(f"Error analyzing image structure: {e}")
            return {}
    
    def _analyze_pdf_structure(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze PDF structure"""
        try:
            images = pdf2image.convert_from_path(pdf_path, dpi=150)
            first_page_structure = self._analyze_image_structure("temp_pdf_page.jpg")
            
            # Save first page temporarily for analysis
            images[0].save("temp_pdf_page.jpg")
            structure = self._analyze_image_structure("temp_pdf_page.jpg")
            
            # Clean up
            if os.path.exists("temp_pdf_page.jpg"):
                os.remove("temp_pdf_page.jpg")
            
            return structure
        except Exception as e:
            logger.error(f"Error analyzing PDF structure: {e}")
            return {}
    
    def _analyze_docx_structure(self, docx_path: str) -> Dict[str, Any]:
        """Analyze DOCX structure"""
        if not DOCX_AVAILABLE:
            return {}
        
        try:
            doc = Document(docx_path)
            
            # Check for headers/footers
            has_header_footer = len(doc.sections) > 0
            
            # Check for tables (often used in certificates)
            has_tables = len(doc.tables) > 0
            
            # Check for formatting
            has_bold_text = any(run.bold for paragraph in doc.paragraphs for run in paragraph.runs if run.bold)
            has_centered_text = any(paragraph.paragraph_format.alignment for paragraph in doc.paragraphs)
            
            return {
                'has_header_footer': has_header_footer,
                'has_tables': has_tables,
                'has_bold_text': has_bold_text,
                'has_centered_text': has_centered_text
            }
        except Exception as e:
            logger.error(f"Error analyzing DOCX structure: {e}")
            return {}
    
    def extract_features(self, file_path: str) -> Dict[str, Any]:
        """Extract comprehensive features for certificate validation"""
        # Extract text content
        text = self.extract_text(file_path)
        
        # Analyze certificate indicators
        indicators = self.analyze_certificate_indicators(text)
        
        # Analyze document structure
        structure = self.analyze_document_structure(file_path)
        
        # Extract text-based features
        text_features = self._extract_text_features(text)
        
        # Extract file-based features
        file_features = self._extract_file_features(file_path)
        
        # Combine all features
        features = {
            **indicators,
            **structure,
            **text_features,
            **file_features
        }
        
        return features
    
    def _extract_text_features(self, text: str) -> Dict[str, Any]:
        """Extract text-based features"""
        if not text:
            return {
                'text_length': 0,
                'word_count': 0,
                'line_count': 0,
                'avg_word_length': 0,
                'uppercase_ratio': 0,
                'digit_ratio': 0
            }
        
        words = text.split()
        lines = text.split('\n')
        
        # Calculate text statistics
        text_length = len(text)
        word_count = len(words)
        line_count = len([line for line in lines if line.strip()])
        
        avg_word_length = np.mean([len(word) for word in words]) if words else 0
        uppercase_ratio = sum(1 for c in text if c.isupper()) / len(text) if text else 0
        digit_ratio = sum(1 for c in text if c.isdigit()) / len(text) if text else 0
        
        return {
            'text_length': text_length,
            'word_count': word_count,
            'line_count': line_count,
            'avg_word_length': avg_word_length,
            'uppercase_ratio': uppercase_ratio,
            'digit_ratio': digit_ratio
        }
    
    def _extract_file_features(self, file_path: str) -> Dict[str, Any]:
        """Extract file-based features"""
        try:
            file_size = os.path.getsize(file_path)
            file_extension = os.path.splitext(file_path)[1].lower()
            
            return {
                'file_size': file_size,
                'is_pdf': file_extension == '.pdf',
                'is_image': file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff'],
                'is_docx': file_extension == '.docx'
            }
        except Exception as e:
            logger.error(f"Error extracting file features: {e}")
            return {
                'file_size': 0,
                'is_pdf': False,
                'is_image': False,
                'is_docx': False
            }
    
    def validate_certificate(self, file_path: str) -> Dict[str, Any]:
        """Validate if the document is a certificate"""
        try:
            # Extract features
            features = self.extract_features(file_path)
            
            # Use trained model if available
            if self.model_trained and self.model:
                prediction = self._predict_with_model(features)
            else:
                # Use rule-based validation
                prediction = self._rule_based_validation(features)
            
            return {
                'is_certificate': prediction['is_certificate'],
                'confidence': prediction['confidence'],
                'document_type': features.get('document_type', 'unknown'),
                'reasoning': prediction['reasoning'],
                'features': features
            }
            
        except Exception as e:
            logger.error(f"Error validating certificate: {e}")
            return {
                'is_certificate': False,
                'confidence': 0.0,
                'document_type': 'error',
                'reasoning': f'Error during validation: {str(e)}',
                'features': {}
            }
    
    def _rule_based_validation(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based certificate validation"""
        score = 0
        reasoning = []
        
        # Certificate keywords (most important)
        keyword_count = len(features.get('certificate_keywords_found', []))
        if keyword_count >= 3:
            score += 40
            reasoning.append(f"Found {keyword_count} certificate keywords")
        elif keyword_count >= 1:
            score += 20
            reasoning.append(f"Found {keyword_count} certificate keyword(s)")
        
        # Institution keywords
        institution_count = len(features.get('institution_keywords_found', []))
        if institution_count >= 1:
            score += 15
            reasoning.append(f"Found {institution_count} institution keyword(s)")
        
        # Dates present
        date_count = len(features.get('dates_found', []))
        if date_count >= 1:
            score += 15
            reasoning.append(f"Found {date_count} date(s)")
        
        # Names present
        name_count = len(features.get('names_found', []))
        if name_count >= 1:
            score += 10
            reasoning.append(f"Found {name_count} potential name(s)")
        
        # Official elements
        if features.get('has_signatures', False):
            score += 10
            reasoning.append("Found signature-like elements")
        
        if features.get('has_seals_logos', False):
            score += 5
            reasoning.append("Found seal/logo elements")
        
        if features.get('has_border', False):
            score += 5
            reasoning.append("Found border elements")
        
        # Text length (certificates usually have substantial text)
        text_length = features.get('text_length', 0)
        if 50 <= text_length <= 2000:
            score += 5
            reasoning.append("Appropriate text length")
        
        # Determine if it's a certificate
        confidence = min(score / 100, 1.0)
        is_certificate = score >= 50  # Threshold for certificate
        
        if not is_certificate:
            if keyword_count == 0:
                reasoning.append("No certificate keywords found")
            if text_length < 20:
                reasoning.append("Text too short")
            if score < 30:
                reasoning.append("Insufficient certificate characteristics")
        
        return {
            'is_certificate': is_certificate,
            'confidence': confidence,
            'reasoning': reasoning
        }
    
    def _predict_with_model(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Use trained ML model for prediction"""
        try:
            # Prepare features for model
            feature_vector = self._prepare_features_for_model(features)
            
            # Make prediction
            prediction = self.model.predict_proba(feature_vector)[0]
            confidence = prediction[1]  # Probability of being certificate
            
            is_certificate = confidence > 0.5
            
            reasoning = []
            if confidence > 0.8:
                reasoning.append("High confidence certificate detection")
            elif confidence > 0.6:
                reasoning.append("Moderate confidence certificate detection")
            elif confidence > 0.4:
                reasoning.append("Low confidence - may be certificate")
            else:
                reasoning.append("Unlikely to be a certificate")
            
            return {
                'is_certificate': is_certificate,
                'confidence': confidence,
                'reasoning': reasoning
            }
        except Exception as e:
            logger.error(f"Error in ML prediction: {e}")
            # Fallback to rule-based
            return self._rule_based_validation(features)
    
    def _prepare_features_for_model(self, features: Dict[str, Any]) -> np.ndarray:
        """Prepare features for ML model"""
        # Define feature order (must match training)
        feature_order = [
            'text_length', 'word_count', 'line_count', 'avg_word_length',
            'uppercase_ratio', 'digit_ratio', 'file_size', 'is_pdf',
            'is_image', 'is_docx', 'certificate_score', 'has_signatures',
            'has_seals_logos', 'has_border', 'signature_count', 'seal_count'
        ]
        
        # Convert features to vector
        feature_vector = []
        for feature in feature_order:
            value = features.get(feature, 0)
            if isinstance(value, bool):
                value = int(value)
            elif value is None:
                value = 0
            feature_vector.append(value)
        
        return np.array(feature_vector).reshape(1, -1)
    
    def train_model(self, training_data: List[Dict[str, Any]], labels: List[int]):
        """Train the certificate validation model"""
        try:
            # Prepare features
            X = []
            for data in training_data:
                features = self._prepare_features_for_model(data)
                X.append(features.flatten())
            
            X = np.array(X)
            y = np.array(labels)
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train model
            self.model = RandomForestClassifier(n_estimators=100, random_state=42)
            self.model.fit(X_scaled, y)
            
            self.model_trained = True
            logger.info("Certificate validation model trained successfully")
            
            # Save model if path provided
            if self.model_path:
                self.save_model()
            
        except Exception as e:
            logger.error(f"Error training certificate validation model: {e}")
            raise
    
    def save_model(self):
        """Save the trained model"""
        if not self.model_trained or not self.model_path:
            return
        
        try:
            model_data = {
                'model': self.model,
                'scaler': self.scaler,
                'vectorizer': self.vectorizer,
                'model_trained': self.model_trained
            }
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            logger.info(f"Certificate validation model saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def load_model(self):
        """Load a trained model"""
        if not self.model_path or not os.path.exists(self.model_path):
            return
        
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.vectorizer = model_data['vectorizer']
            self.model_trained = model_data['model_trained']
            
            logger.info(f"Certificate validation model loaded from {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")


# Example usage
def create_certificate_validation_model():
    """Create and train a certificate validation model"""
    validator = CertificateValidator()
    
    # Example validation
    test_file = "sample_certificate.pdf"
    if os.path.exists(test_file):
        result = validator.validate_certificate(test_file)
        print(f"Validation Result:")
        print(f"Is Certificate: {result['is_certificate']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Document Type: {result['document_type']}")
        print(f"Reasoning: {', '.join(result['reasoning'])}")
    
    return validator


if __name__ == "__main__":
    # Test the certificate validator
    validator = create_certificate_validation_model()
