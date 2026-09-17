"""
Certificate Fraud Detection ML Model
Trained to detect fraudulent certificates based on:
- Font inconsistencies and style analysis
- Watermark detection
- QR code presence and validation
- Layout anomalies
- Text pattern analysis
- Cross-student comparison for anomalies
"""

import os
import cv2
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import pickle
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import qrcode
from pdf2image import convert_from_path
import io
import base64
import json
import re
from typing import Dict, List, Tuple, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CertificateFeatureExtractor:
    """Extract features from certificate images for fraud detection"""
    
    def __init__(self):
        self.common_fonts = [
            'Arial', 'Times New Roman', 'Helvetica', 'Georgia', 
            'Verdana', 'Courier New', 'Palatino', 'Garamond',
            'Bookman', 'Comic Sans MS', 'Trebuchet MS', 'Arial Black'
        ]
        
    def extract_font_features(self, image_path: str) -> Dict[str, Any]:
        """Extract font-related features from certificate"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return self._get_default_font_features()
            
            # Preprocess image for better OCR
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray)
            thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            
            # Extract text with bounding box information
            data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
            
            font_features = {
                'avg_font_size': 0,
                'font_size_variance': 0,
                'num_different_fonts': 0,
                'text_density': 0,
                'line_spacing_variance': 0,
                'font_consistency_score': 0,
                'has_multiple_font_sizes': False,
                'has_inconsistent_spacing': False
            }
            
            # Extract font sizes from text
            font_sizes = []
            line_heights = []
            prev_bottom = -1
            
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 0 and data['text'][i].strip():
                    height = data['height'][i]
                    font_sizes.append(height)
                    
                    # Calculate line spacing
                    bottom = data['top'][i] + height
                    if prev_bottom != -1:
                        line_spacing = bottom - prev_bottom
                        if line_spacing > 0:
                            line_heights.append(line_spacing)
                    prev_bottom = bottom
            
            if font_sizes:
                font_features['avg_font_size'] = np.mean(font_sizes)
                font_features['font_size_variance'] = np.var(font_sizes)
                font_features['num_different_fonts'] = len(set(font_sizes))
                font_features['has_multiple_font_sizes'] = len(set(font_sizes)) > 1
                
                # Font consistency score (lower variance = higher consistency)
                font_features['font_consistency_score'] = 1 / (1 + font_features['font_size_variance'])
                
            if line_heights:
                font_features['line_spacing_variance'] = np.var(line_heights)
                font_features['has_inconsistent_spacing'] = font_features['line_spacing_variance'] > 100
            
            # Text density (text area vs total area)
            text_area = sum([(data['width'][i] * data['height'][i]) 
                           for i in range(len(data['text'])) 
                           if int(data['conf'][i]) > 0])
            total_area = image.shape[0] * image.shape[1]
            font_features['text_density'] = text_area / total_area if total_area > 0 else 0
            
            return font_features
            
        except Exception as e:
            logger.error(f"Error extracting font features: {e}")
            return self._get_default_font_features()
    
    def extract_watermark_features(self, image_path: str) -> Dict[str, Any]:
        """Detect and analyze watermarks"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return self._get_default_watermark_features()
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Method 1: Detect transparent watermarks using threshold analysis
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            
            # Look for peaks in histogram that might indicate watermarks
            watermark_indicators = 0
            for i in range(1, 255):
                if hist[i] > hist[i-1] * 2 and hist[i] > hist[i+1] * 2:
                    watermark_indicators += 1
            
            # Method 2: Edge detection for watermark patterns
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Count potential watermark contours (large, faint patterns)
            watermark_contours = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if 1000 < area < 50000:  # Medium-sized contours
                    # Check if contour is faint (possible watermark)
                    x, y, w, h = cv2.boundingRect(contour)
                    roi = gray[y:y+h, x:x+w]
                    if np.mean(roi) > 200:  # Faint/light color
                        watermark_contours += 1
            
            # Method 3: Frequency domain analysis for watermarks
            f_transform = np.fft.fft2(gray)
            f_shift = np.fft.fftshift(f_transform)
            magnitude_spectrum = np.abs(f_shift)
            
            # Look for periodic patterns (watermarks)
            center = magnitude_spectrum.shape[0] // 2
            center_region = magnitude_spectrum[center-50:center+50, center-50:center+50]
            frequency_anomaly = np.std(center_region) / np.mean(magnitude_spectrum) if np.mean(magnitude_spectrum) > 0 else 0
            
            return {
                'has_watermark': watermark_indicators > 3 or watermark_contours > 2 or frequency_anomaly > 2,
                'watermark_confidence': min(1.0, (watermark_indicators + watermark_contours) / 10),
                'watermark_indicators': watermark_indicators,
                'watermark_contours': watermark_contours,
                'frequency_anomaly': frequency_anomaly
            }
            
        except Exception as e:
            logger.error(f"Error extracting watermark features: {e}")
            return self._get_default_watermark_features()
    
    def extract_qr_features(self, image_path: str) -> Dict[str, Any]:
        """Detect and analyze QR codes"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return self._get_default_qr_features()
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Initialize QR code detector
            detector = cv2.QRCodeDetector()
            
            # Detect QR codes
            data, points, _ = detector.detectAndDecode(gray)
            
            qr_features = {
                'has_qr_code': False,
                'qr_code_count': 0,
                'qr_data_valid': False,
                'qr_position_anomaly': False,
                'qr_size_variance': 0
            }
            
            if data and points is not None:
                qr_features['has_qr_code'] = True
                qr_features['qr_code_count'] = len(points) if isinstance(points, list) else 1
                qr_features['qr_data_valid'] = len(data.strip()) > 0
                
                # Analyze QR code position and size
                if isinstance(points, list) and len(points) > 0:
                    qr_areas = []
                    qr_positions = []
                    
                    for qr_point in points:
                        if qr_point is not None and len(qr_point) == 4:
                            # Calculate QR code area
                            area = cv2.contourArea(qr_point)
                            qr_areas.append(area)
                            
                            # Calculate center position
                            center_x = np.mean(qr_point[:, 0])
                            center_y = np.mean(qr_point[:, 1])
                            qr_positions.append((center_x, center_y))
                    
                    if qr_areas:
                        qr_features['qr_size_variance'] = np.var(qr_areas)
                        
                        # Check if QR codes are in unusual positions
                        img_center_x, img_center_y = image.shape[1] // 2, image.shape[0] // 2
                        position_anomalies = 0
                        
                        for pos in qr_positions:
                            dist_from_center = np.sqrt((pos[0] - img_center_x)**2 + (pos[1] - img_center_y)**2)
                            if dist_from_center > min(image.shape[1], image.shape[0]) * 0.4:
                                position_anomalies += 1
                        
                        qr_features['qr_position_anomaly'] = position_anomalies > 0
            
            return qr_features
            
        except Exception as e:
            logger.error(f"Error extracting QR features: {e}")
            return self._get_default_qr_features()
    
    def extract_layout_features(self, image_path: str) -> Dict[str, Any]:
        """Analyze certificate layout for anomalies"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return self._get_default_layout_features()
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Get text data
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            
            layout_features = {
                'text_alignment_score': 0,
                'margin_consistency': 0,
                'layout_balance': 0,
                'has_irregular_spacing': False,
                'text_blocks_count': 0,
                'center_alignment_ratio': 0
            }
            
            # Analyze text alignment
            x_positions = []
            y_positions = []
            
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 0 and data['text'][i].strip():
                    x_positions.append(data['left'][i])
                    y_positions.append(data['top'][i])
            
            if x_positions:
                # Calculate text alignment score
                x_positions = np.array(x_positions)
                left_aligned = np.sum(x_positions < 50)
                center_aligned = np.sum((x_positions > image.shape[1] * 0.3) & (x_positions < image.shape[1] * 0.7))
                right_aligned = np.sum(x_positions > image.shape[1] - 50)
                
                total_texts = len(x_positions)
                layout_features['center_alignment_ratio'] = center_aligned / total_texts if total_texts > 0 else 0
                layout_features['text_alignment_score'] = max(left_aligned, center_aligned, right_aligned) / total_texts if total_texts > 0 else 0
            
            # Analyze margins
            if x_positions:
                left_margin = np.min(x_positions)
                right_margin = image.shape[1] - np.max(x_positions)
                margin_consistency = abs(left_margin - right_margin) / image.shape[1]
                layout_features['margin_consistency'] = 1 - margin_consistency
            
            # Count text blocks (groups of text on same line)
            if y_positions:
                y_positions = np.array(y_positions)
                text_lines = 0
                prev_y = -1
                
                for y in sorted(y_positions):
                    if prev_y == -1 or abs(y - prev_y) > 20:
                        text_lines += 1
                    prev_y = y
                
                layout_features['text_blocks_count'] = text_lines
            
            return layout_features
            
        except Exception as e:
            logger.error(f"Error extracting layout features: {e}")
            return self._get_default_layout_features()
    
    def extract_text_pattern_features(self, image_path: str) -> Dict[str, Any]:
        """Analyze text patterns for anomalies"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return self._get_default_text_features()
            
            # Extract text
            text = pytesseract.image_to_string(image)
            
            text_features = {
                'certificate_keywords_present': False,
                'date_format_consistent': False,
                'has_special_characters': False,
                'text_length': len(text),
                'word_count': len(text.split()),
                'suspicious_patterns': 0
            }
            
            # Check for certificate keywords
            cert_keywords = ['certificate', 'completion', 'achievement', 'course', 'training', 'certified']
            text_lower = text.lower()
            keyword_count = sum(1 for keyword in cert_keywords if keyword in text_lower)
            text_features['certificate_keywords_present'] = keyword_count >= 2
            
            # Check date format consistency
            date_patterns = [
                r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
                r'\d{4}-\d{2}-\d{2}',        # YYYY-MM-DD
                r'\d{1,2}-\d{1,2}-\d{4}',    # MM-DD-YYYY
                r'\w+ \d{1,2}, \d{4}'        # Month DD, YYYY
            ]
            
            date_matches = 0
            for pattern in date_patterns:
                matches = re.findall(pattern, text)
                date_matches += len(matches)
            
            text_features['date_format_consistent'] = date_matches == 1
            
            # Check for suspicious patterns
            suspicious_patterns = [
                r'[^a-zA-Z0-9\s\.,\-\:]+',  # Unusual special characters
                r'[A-Z]{10,}',              # Long capitalized words
                r'\d{10,}',                 # Very long numbers
            ]
            
            for pattern in suspicious_patterns:
                matches = re.findall(pattern, text)
                text_features['suspicious_patterns'] += len(matches)
            
            text_features['has_special_characters'] = text_features['suspicious_patterns'] > 0
            
            return text_features
            
        except Exception as e:
            logger.error(f"Error extracting text pattern features: {e}")
            return self._get_default_text_features()
    
    def _get_default_font_features(self) -> Dict[str, Any]:
        return {
            'avg_font_size': 0, 'font_size_variance': 0, 'num_different_fonts': 0,
            'text_density': 0, 'line_spacing_variance': 0, 'font_consistency_score': 0,
            'has_multiple_font_sizes': False, 'has_inconsistent_spacing': False
        }
    
    def _get_default_watermark_features(self) -> Dict[str, Any]:
        return {
            'has_watermark': False, 'watermark_confidence': 0, 'watermark_indicators': 0,
            'watermark_contours': 0, 'frequency_anomaly': 0
        }
    
    def _get_default_qr_features(self) -> Dict[str, Any]:
        return {
            'has_qr_code': False, 'qr_code_count': 0, 'qr_data_valid': False,
            'qr_position_anomaly': False, 'qr_size_variance': 0
        }
    
    def _get_default_layout_features(self) -> Dict[str, Any]:
        return {
            'text_alignment_score': 0, 'margin_consistency': 0, 'layout_balance': 0,
            'has_irregular_spacing': False, 'text_blocks_count': 0, 'center_alignment_ratio': 0
        }
    
    def _get_default_text_features(self) -> Dict[str, Any]:
        return {
            'certificate_keywords_present': False, 'date_format_consistent': False,
            'has_special_characters': False, 'text_length': 0, 'word_count': 0,
            'suspicious_patterns': 0
        }


class CertificateFraudDetector:
    """Main fraud detection model"""
    
    def __init__(self, model_path: str = None):
        self.feature_extractor = CertificateFeatureExtractor()
        self.scaler = StandardScaler()
        self.isolation_forest = IsolationForest(contamination=0.1, random_state=42)
        self.random_forest = RandomForestClassifier(n_estimators=100, random_state=42)
        self.model_trained = False
        self.model_path = model_path
        
        if model_path and os.path.exists(model_path):
            self.load_model()
    
    def extract_all_features(self, image_path: str) -> Dict[str, Any]:
        """Extract all features from a certificate image"""
        features = {}
        
        # Extract different types of features
        font_features = self.feature_extractor.extract_font_features(image_path)
        watermark_features = self.feature_extractor.extract_watermark_features(image_path)
        qr_features = self.feature_extractor.extract_qr_features(image_path)
        layout_features = self.feature_extractor.extract_layout_features(image_path)
        text_features = self.feature_extractor.extract_text_pattern_features(image_path)
        
        # Combine all features
        features.update(font_features)
        features.update(watermark_features)
        features.update(qr_features)
        features.update(layout_features)
        features.update(text_features)
        
        return features
    
    def prepare_features_for_model(self, features: Dict[str, Any]) -> np.ndarray:
        """Convert features to numpy array for model input"""
        # Define feature order (must be consistent)
        feature_order = [
            'avg_font_size', 'font_size_variance', 'num_different_fonts', 'text_density',
            'line_spacing_variance', 'font_consistency_score', 'has_multiple_font_sizes',
            'has_inconsistent_spacing', 'has_watermark', 'watermark_confidence',
            'watermark_indicators', 'watermark_contours', 'frequency_anomaly',
            'has_qr_code', 'qr_code_count', 'qr_data_valid', 'qr_position_anomaly',
            'qr_size_variance', 'text_alignment_score', 'margin_consistency',
            'layout_balance', 'has_irregular_spacing', 'text_blocks_count',
            'center_alignment_ratio', 'certificate_keywords_present', 'date_format_consistent',
            'has_special_characters', 'text_length', 'word_count', 'suspicious_patterns'
        ]
        
        # Convert boolean to int
        feature_values = []
        for feature in feature_order:
            value = features.get(feature, 0)
            if isinstance(value, bool):
                value = int(value)
            elif value is None:
                value = 0
            feature_values.append(value)
        
        return np.array(feature_values).reshape(1, -1)
    
    def train_model(self, training_data: List[Dict[str, Any]], labels: List[int]):
        """Train the fraud detection model"""
        try:
            # Prepare features
            X = []
            for data in training_data:
                features = self.prepare_features_for_model(data)
                X.append(features.flatten())
            
            X = np.array(X)
            y = np.array(labels)
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train both models
            self.isolation_forest.fit(X_scaled)
            self.random_forest.fit(X_scaled, y)
            
            self.model_trained = True
            logger.info("Model training completed successfully")
            
            # Save model if path provided
            if self.model_path:
                self.save_model()
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
            raise
    
    def predict_fraud_probability(self, image_path: str) -> Dict[str, Any]:
        """Predict fraud probability for a certificate"""
        if not self.model_trained:
            raise ValueError("Model not trained yet")
        
        try:
            # Extract features
            features = self.extract_all_features(image_path)
            X = self.prepare_features_for_model(features)
            X_scaled = self.scaler.transform(X)
            
            # Get predictions from both models
            isolation_score = self.isolation_forest.decision_function(X_scaled)[0]
            rf_proba = self.random_forest.predict_proba(X_scaled)[0]
            
            # Convert isolation score to probability (lower score = more anomalous)
            isolation_proba = 1 - (isolation_score + 1) / 2  # Normalize to [0, 1]
            
            # Combine predictions (weighted average)
            combined_proba = 0.6 * rf_proba[1] + 0.4 * isolation_proba
            
            # Determine risk level
            if combined_proba < 0.3:
                risk_level = "Low"
            elif combined_proba < 0.7:
                risk_level = "Medium"
            else:
                risk_level = "High"
            
            return {
                'fraud_probability': float(combined_proba),
                'risk_level': risk_level,
                'isolation_score': float(isolation_score),
                'random_forest_probability': float(rf_proba[1]),
                'features': features,
                'recommendation': self._get_recommendation(combined_proba, features)
            }
            
        except Exception as e:
            logger.error(f"Error predicting fraud: {e}")
            return {
                'fraud_probability': 0.5,
                'risk_level': "Medium",
                'error': str(e),
                'recommendation': "Manual review required due to processing error"
            }
    
    def _get_recommendation(self, probability: float, features: Dict[str, Any]) -> str:
        """Generate recommendation based on probability and features"""
        if probability < 0.3:
            return "Certificate appears authentic. Safe to approve."
        elif probability < 0.7:
            reasons = []
            if features.get('has_multiple_font_sizes'):
                reasons.append("multiple font sizes detected")
            if features.get('has_inconsistent_spacing'):
                reasons.append("inconsistent text spacing")
            if features.get('has_watermark'):
                reasons.append("watermark detected")
            if not features.get('certificate_keywords_present'):
                reasons.append("missing certificate keywords")
            
            if reasons:
                return f"Review needed: {', '.join(reasons)}."
            else:
                return "Minor anomalies detected. Consider manual review."
        else:
            reasons = []
            if features.get('suspicious_patterns') > 0:
                reasons.append("suspicious text patterns")
            if features.get('has_watermark'):
                reasons.append("unusual watermark detected")
            if features.get('qr_position_anomaly'):
                reasons.append("QR code in unusual position")
            if not features.get('date_format_consistent'):
                reasons.append("inconsistent date format")
            
            return f"High risk detected: {', '.join(reasons) if reasons else 'multiple anomalies'}. Recommend rejection."
    
    def compare_certificates(self, image_paths: List[str]) -> Dict[str, Any]:
        """Compare multiple certificates for consistency"""
        if len(image_paths) < 2:
            return {"error": "Need at least 2 certificates for comparison"}
        
        try:
            all_features = []
            for path in image_paths:
                features = self.extract_all_features(path)
                all_features.append(features)
            
            # Compare font consistency across certificates
            font_sizes = [f.get('avg_font_size', 0) for f in all_features]
            font_variance = np.var(font_sizes)
            
            # Compare layout consistency
            alignments = [f.get('text_alignment_score', 0) for f in all_features]
            alignment_variance = np.var(alignments)
            
            # Compare text density
            densities = [f.get('text_density', 0) for f in all_features]
            density_variance = np.var(densities)
            
            # Calculate overall consistency score
            consistency_score = 1 / (1 + font_variance + alignment_variance + density_variance)
            
            # Find outliers
            outlier_indices = []
            for i, features in enumerate(all_features):
                if self.model_trained:
                    X = self.prepare_features_for_model(features)
                    X_scaled = self.scaler.transform(X)
                    score = self.isolation_forest.decision_function(X_scaled)[0]
                    if score < -0.5:  # Threshold for outlier
                        outlier_indices.append(i)
            
            return {
                'consistency_score': float(consistency_score),
                'font_variance': float(font_variance),
                'alignment_variance': float(alignment_variance),
                'density_variance': float(density_variance),
                'outlier_certificates': outlier_indices,
                'recommendation': self._get_comparison_recommendation(consistency_score, outlier_indices)
            }
            
        except Exception as e:
            logger.error(f"Error comparing certificates: {e}")
            return {"error": str(e)}
    
    def _get_comparison_recommendation(self, consistency_score: float, outliers: List[int]) -> str:
        """Get recommendation for certificate comparison"""
        if consistency_score > 0.8 and not outliers:
            return "All certificates show consistent patterns. Safe to approve."
        elif consistency_score > 0.6:
            if outliers:
                return f"Certificates mostly consistent, but certificate(s) {', '.join(map(str, outliers))} show anomalies. Review recommended."
            else:
                return "Minor variations detected. Consider manual review."
        else:
            if outliers:
                return f"Significant inconsistencies detected. Certificate(s) {', '.join(map(str, outliers))} may be fraudulent. Recommend rejection of outliers."
            else:
                return "High variability detected across certificates. Thorough review recommended."
    
    def save_model(self):
        """Save the trained model"""
        if not self.model_trained or not self.model_path:
            return
        
        try:
            model_data = {
                'scaler': self.scaler,
                'isolation_forest': self.isolation_forest,
                'random_forest': self.random_forest,
                'model_trained': self.model_trained
            }
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            logger.info(f"Model saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def load_model(self):
        """Load a trained model"""
        if not self.model_path or not os.path.exists(self.model_path):
            return
        
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.scaler = model_data['scaler']
            self.isolation_forest = model_data['isolation_forest']
            self.random_forest = model_data['random_forest']
            self.model_trained = model_data['model_trained']
            
            logger.info(f"Model loaded from {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")


# Example usage and training function
def create_training_dataset(certificates_folder: str, labels_file: str) -> Tuple[List[Dict], List[int]]:
    """Create training dataset from certificates folder"""
    detector = CertificateFraudDetector()
    
    training_data = []
    labels = []
    
    # Read labels file (CSV with filename, label columns)
    try:
        labels_df = pd.read_csv(labels_file)
        
        for _, row in labels_df.iterrows():
            filename = row['filename']
            label = row['label']  # 0 for authentic, 1 for fraudulent
            
            image_path = os.path.join(certificates_folder, filename)
            if os.path.exists(image_path):
                features = detector.extract_all_features(image_path)
                training_data.append(features)
                labels.append(label)
                logger.info(f"Processed {filename}")
        
        return training_data, labels
        
    except Exception as e:
        logger.error(f"Error creating training dataset: {e}")
        return [], []


def train_fraud_detection_model(certificates_folder: str, labels_file: str, model_save_path: str):
    """Train and save the fraud detection model"""
    logger.info("Starting fraud detection model training...")
    
    # Create training dataset
    training_data, labels = create_training_dataset(certificates_folder, labels_file)
    
    if len(training_data) == 0:
        logger.error("No training data created")
        return
    
    # Train model
    detector = CertificateFraudDetector(model_save_path)
    detector.train_model(training_data, labels)
    
    # Evaluate model
    if len(training_data) > 10:
        # Split for evaluation
        X_train, X_test, y_train, y_test = train_test_split(training_data, labels, test_size=0.2, random_state=42)
        
        detector.train_model(X_train, y_train)
        
        # Test predictions
        predictions = []
        for i, data in enumerate(X_test):
            features = detector.prepare_features_for_model(data)
            X_scaled = detector.scaler.transform(features)
            pred = detector.random_forest.predict(X_scaled)[0]
            predictions.append(pred)
        
        print("\nModel Evaluation:")
        print(classification_report(y_test, predictions))
        print("Confusion Matrix:")
        print(confusion_matrix(y_test, predictions))
    
    logger.info("Model training completed")
    return detector


if __name__ == "__main__":
    # Example training script
    CERTIFICATES_FOLDER = "training_data/certificates"
    LABELS_FILE = "training_data/labels.csv"
    MODEL_SAVE_PATH = "models/certificate_fraud_detector.pkl"
    
    # Train model
    detector = train_fraud_detection_model(CERTIFICATES_FOLDER, LABELS_FILE, MODEL_SAVE_PATH)
    
    # Example prediction
    if detector:
        test_image = "test_certificate.jpg"
        if os.path.exists(test_image):
            result = detector.predict_fraud_probability(test_image)
            print(f"\nPrediction Results:")
            print(f"Fraud Probability: {result['fraud_probability']:.2f}")
            print(f"Risk Level: {result['risk_level']}")
            print(f"Recommendation: {result['recommendation']}")
