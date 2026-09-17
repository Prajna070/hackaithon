"""
Certificate Fraud Detection Model Training Script
This script prepares training data and trains the ML model for certificate fraud detection.
"""

import os
import pandas as pd
import numpy as np
import cv2
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
import json
import random
from datetime import datetime
import shutil
from certificate_fraud_detection import CertificateFraudDetector, CertificateFeatureExtractor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CertificateDataGenerator:
    """Generate synthetic certificate data for training"""
    
    def __init__(self, output_dir: str = "training_data"):
        self.output_dir = output_dir
        self.certificates_dir = os.path.join(output_dir, "certificates")
        self.create_directories()
        
        # Certificate templates
        self.templates = {
            'authentic': {
                'fonts': ['Arial', 'Times New Roman', 'Georgia'],
                'layouts': ['standard', 'modern'],
                'colors': [(0, 0, 0), (50, 50, 50)],  # Black, dark gray
                'background': (255, 255, 255),  # White
                'has_watermark': False,
                'has_qr': True
            },
            'fraudulent': {
                'fonts': ['Comic Sans MS', 'Courier New', 'Arial Black'],  # Unusual fonts
                'layouts': ['irregular', 'asymmetric'],
                'colors': [(0, 0, 255), (255, 0, 0), (128, 0, 128)],  # Unusual colors
                'background': (250, 250, 250),  # Slightly off-white
                'has_watermark': True,
                'has_qr': False
            }
        }
    
    def create_directories(self):
        """Create necessary directories"""
        os.makedirs(self.certificates_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "models"), exist_ok=True)
    
    def generate_authentic_certificate(self, student_name: str, course: str, date: str, cert_id: str) -> str:
        """Generate an authentic certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Try to use standard fonts
        try:
            title_font = ImageFont.truetype("arial.ttf", 48)
            text_font = ImageFont.truetype("arial.ttf", 24)
            signature_font = ImageFont.truetype("arial.ttf", 20)
        except:
            # Fallback to default fonts
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            signature_font = ImageFont.load_default()
        
        # Draw border
        draw.rectangle([50, 50, width-50, height-50], outline=(0, 0, 0), width=3)
        draw.rectangle([60, 60, width-60, height-60], outline=(0, 0, 0), width=1)
        
        # Title
        title = "CERTIFICATE OF COMPLETION"
        title_width = draw.textlength(title, font=title_font)
        draw.text(((width - title_width) / 2, 150), title, fill='black', font=title_font)
        
        # Student name
        name_text = f"This is to certify that"
        name_width = draw.textlength(name_text, font=text_font)
        draw.text(((width - name_width) / 2, 300), name_text, fill='black', font=text_font)
        
        student_width = draw.textlength(student_name, font=title_font)
        draw.text(((width - student_width) / 2, 350), student_name, fill='black', font=title_font)
        
        # Course text
        course_text = f"has successfully completed the course"
        course_width = draw.textlength(course_text, font=text_font)
        draw.text(((width - course_width) / 2, 450), course_text, fill='black', font=text_font)
        
        course_width = draw.textlength(course, font=title_font)
        draw.text(((width - course_width) / 2, 500), course, fill='black', font=title_font)
        
        # Date
        date_text = f"on {date}"
        date_width = draw.textlength(date_text, font=text_font)
        draw.text(((width - date_width) / 2, 600), date_text, fill='black', font=text_font)
        
        # Certificate ID
        id_text = f"Certificate ID: {cert_id}"
        id_width = draw.textlength(id_text, font=signature_font)
        draw.text(((width - id_width) / 2, 700), id_text, fill='black', font=signature_font)
        
        # Add QR code
        qr_data = f"https://verify.example.com/{cert_id}"
        self.add_qr_code(draw, qr_data, width - 200, height - 200)
        
        # Save certificate
        filename = f"authentic_{cert_id}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        
        return filename
    
    def generate_fraudulent_certificate(self, student_name: str, course: str, date: str, cert_id: str, fraud_type: str = "font") -> str:
        """Generate a fraudulent certificate with various anomalies"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), (250, 250, 250))  # Off-white
        draw = ImageDraw.Draw(img)
        
        # Use unusual fonts or inconsistent styling
        try:
            if fraud_type == "font":
                title_font = ImageFont.truetype("arial.ttf", 48)
                text_font = ImageFont.truetype("comic.ttf", 24)  # Different font
                signature_font = ImageFont.truetype("cour.ttf", 20)  # Another font
            elif fraud_type == "size":
                title_font = ImageFont.truetype("arial.ttf", 60)  # Too large
                text_font = ImageFont.truetype("arial.ttf", 16)  # Too small
                signature_font = ImageFont.truetype("arial.ttf", 28)  # Inconsistent
            else:
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
                signature_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            signature_font = ImageFont.load_default()
        
        # Irregular border
        if fraud_type == "layout":
            draw.rectangle([30, 70, width-40, height-60], outline=(0, 0, 255), width=3)  # Blue border
            draw.rectangle([45, 55, width-55, height-55], outline=(255, 0, 0), width=1)  # Red inner border
        else:
            draw.rectangle([50, 50, width-50, height-50], outline=(0, 0, 0), width=3)
        
        # Title with unusual styling
        title = "Certificate Of Completion"  # Inconsistent capitalization
        if fraud_type == "color":
            title_color = (0, 0, 255)  # Blue title
        else:
            title_color = 'black'
        
        title_width = draw.textlength(title, font=title_font)
        draw.text(((width - title_width) / 2 + random.randint(-20, 20), 150), title, fill=title_color, font=title_font)
        
        # Student name (maybe misspelled or unusual formatting)
        if fraud_type == "text":
            name_text = "This is to Certify that"  # Capitalization error
            # Introduce a typo in student name
            student_name = student_name.replace('a', '@').replace('e', '3')
        else:
            name_text = f"This is to certify that"
        
        name_width = draw.textlength(name_text, font=text_font)
        draw.text(((width - name_width) / 2, 300), name_text, fill='black', font=text_font)
        
        student_width = draw.textlength(student_name, font=title_font)
        draw.text(((width - student_width) / 2, 350), student_name, fill='black', font=title_font)
        
        # Course text with potential issues
        course_text = f"has successfully completed the course"
        if fraud_type == "spacing":
            # Add irregular spacing
            course_text = "has  successfully   completed the   course"
        
        course_width = draw.textlength(course_text, font=text_font)
        draw.text(((width - course_width) / 2, 450), course_text, fill='black', font=text_font)
        
        course_width = draw.textlength(course, font=title_font)
        draw.text(((width - course_width) / 2, 500), course, fill='black', font=title_font)
        
        # Date with potential format issues
        if fraud_type == "date":
            date_text = f"on {date} 2024 EXTRA"  # Extra text
        else:
            date_text = f"on {date}"
        
        date_width = draw.textlength(date_text, font=text_font)
        draw.text(((width - date_width) / 2, 600), date_text, fill='black', font=text_font)
        
        # Certificate ID (might be missing or malformed)
        if fraud_type == "missing_id":
            id_text = "Certificate ID: MISSING"
        else:
            id_text = f"Certificate ID: {cert_id}FAKE"
        
        id_width = draw.textlength(id_text, font=signature_font)
        draw.text(((width - id_width) / 2, 700), id_text, fill='black', font=signature_font)
        
        # Add watermark for fraudulent certificates
        if fraud_type == "watermark":
            self.add_watermark(draw, "SAMPLE", width, height)
        
        # Don't add QR code for fraudulent certificates
        # or add it in wrong position
        if fraud_type == "qr_position":
            qr_data = f"https://verify.example.com/{cert_id}"
            self.add_qr_code(draw, qr_data, 50, 50)  # Wrong position
        
        # Add noise/distortion
        if fraud_type == "noise":
            img = self.add_noise(img)
        
        # Save certificate
        filename = f"fraudulent_{fraud_type}_{cert_id}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        
        return filename
    
    def add_qr_code(self, draw, data: str, x: int, y: int):
        """Add a simple QR code representation"""
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=3, border=1)
            qr.add_data(data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Paste QR code onto certificate
            qr_img = qr_img.resize((100, 100))
            draw.bitmap([x, y], qr_img.convert('1'), fill='black')
        except:
            # Draw simple square as QR placeholder
            draw.rectangle([x, y, x+100, y+100], fill='black')
            draw.rectangle([x+10, y+10, x+90, y+90], fill='white')
            draw.rectangle([x+20, y+20, x+80, y+80], fill='black')
    
    def add_watermark(self, draw, text: str, width: int, height: int):
        """Add watermark to certificate"""
        try:
            font = ImageFont.load_default()
            text_width = draw.textlength(text, font=font)
            
            # Add watermark diagonally across the certificate
            for i in range(0, width, 200):
                for j in range(0, height, 200):
                    draw.text((i, j), text, fill=(200, 200, 200), font=font)
        except:
            pass
    
    def add_noise(self, img: Image.Image) -> Image.Image:
        """Add noise to image"""
        pixels = np.array(img)
        noise = np.random.normal(0, 25, pixels.shape)
        noisy_pixels = np.clip(pixels + noise, 0, 255)
        return Image.fromarray(noisy_pixels.astype('uint8'))
    
    def generate_training_dataset(self, num_authentic: int = 100, num_fraudulent: int = 100):
        """Generate complete training dataset"""
        logger.info(f"Generating {num_authentic} authentic and {num_fraudulent} fraudulent certificates...")
        
        # Sample data
        students = [f"Student_{i}" for i in range(1, 201)]
        courses = [
            "Python Programming", "Web Development", "Data Science", 
            "Machine Learning", "Cloud Computing", "Cybersecurity",
            "Mobile Development", "DevOps Engineering", "Blockchain",
            "Artificial Intelligence"
        ]
        
        certificates_data = []
        
        # Generate authentic certificates
        for i in range(num_authentic):
            student = random.choice(students)
            course = random.choice(courses)
            date = f"{random.randint(2020, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            cert_id = f"AUT{i:04d}"
            
            filename = self.generate_authentic_certificate(student, course, date, cert_id)
            certificates_data.append({
                'filename': filename,
                'label': 0,  # 0 for authentic
                'student': student,
                'course': course,
                'date': date,
                'cert_id': cert_id,
                'fraud_type': 'authentic'
            })
        
        # Generate fraudulent certificates with different fraud types
        fraud_types = ['font', 'layout', 'color', 'text', 'spacing', 'date', 'missing_id', 'watermark', 'qr_position', 'noise']
        
        for i in range(num_fraudulent):
            student = random.choice(students)
            course = random.choice(courses)
            date = f"{random.randint(2020, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            cert_id = f"FRD{i:04d}"
            fraud_type = random.choice(fraud_types)
            
            filename = self.generate_fraudulent_certificate(student, course, date, cert_id, fraud_type)
            certificates_data.append({
                'filename': filename,
                'label': 1,  # 1 for fraudulent
                'student': student,
                'course': course,
                'date': date,
                'cert_id': cert_id,
                'fraud_type': fraud_type
            })
        
        # Save labels file
        labels_df = pd.DataFrame(certificates_data)
        labels_file = os.path.join(self.output_dir, "labels.csv")
        labels_df.to_csv(labels_file, index=False)
        
        logger.info(f"Training dataset generated. Saved {len(certificates_data)} certificates to {self.certificates_dir}")
        logger.info(f"Labels saved to {labels_file}")
        
        return labels_file


def train_and_evaluate_model():
    """Train and evaluate the fraud detection model"""
    # Generate training data
    generator = CertificateDataGenerator()
    labels_file = generator.generate_training_dataset(num_authentic=50, num_fraudulent=50)
    
    # Train model
    from certificate_fraud_detection import train_fraud_detection_model
    
    certificates_folder = generator.certificates_dir
    model_save_path = os.path.join(generator.output_dir, "models", "fraud_detector.pkl")
    
    logger.info("Starting model training...")
    detector = train_fraud_detection_model(certificates_folder, labels_file, model_save_path)
    
    if detector:
        logger.info("Model training completed successfully!")
        
        # Test with sample certificates
        test_certificates = [
            os.path.join(certificates_folder, "authentic_AUT0001.png"),
            os.path.join(certificates_folder, "fraudulent_font_FRD0001.png")
        ]
        
        for cert_path in test_certificates:
            if os.path.exists(cert_path):
                result = detector.predict_fraud_probability(cert_path)
                print(f"\nResults for {os.path.basename(cert_path)}:")
                print(f"Fraud Probability: {result['fraud_probability']:.3f}")
                print(f"Risk Level: {result['risk_level']}")
                print(f"Recommendation: {result['recommendation']}")
        
        # Test certificate comparison
        cert_paths = [
            os.path.join(certificates_folder, "authentic_AUT0001.png"),
            os.path.join(certificates_folder, "authentic_AUT0002.png"),
            os.path.join(certificates_folder, "fraudulent_font_FRD0001.png")
        ]
        
        cert_paths = [p for p in cert_paths if os.path.exists(p)]
        if len(cert_paths) >= 2:
            comparison_result = detector.compare_certificates(cert_paths)
            print(f"\nCertificate Comparison Results:")
            print(f"Consistency Score: {comparison_result['consistency_score']:.3f}")
            print(f"Recommendation: {comparison_result['recommendation']}")
    
    return detector


def create_requirements_file():
    """Create requirements.txt for the ML model"""
    requirements = """opencv-python>=4.8.0
scikit-learn>=1.3.0
pandas>=2.0.0
numpy>=1.24.0
Pillow>=10.0.0
pytesseract>=0.3.10
pdf2image>=1.16.0
qrcode[pil]>=7.4.0
matplotlib>=3.7.0
seaborn>=0.12.0
joblib>=1.3.0
"""
    
    with open("requirements_ml.txt", "w") as f:
        f.write(requirements)
    
    logger.info("Requirements file created: requirements_ml.txt")


def setup_training_environment():
    """Setup the training environment with all necessary files"""
    logger.info("Setting up ML training environment...")
    
    # Create directory structure
    dirs = [
        "training_data/certificates",
        "training_data/models",
        "training_data/test_samples",
        "models"
    ]
    
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
    
    # Create configuration file
    config = {
        "model_settings": {
            "contamination": 0.1,
            "n_estimators": 100,
            "random_state": 42,
            "test_size": 0.2
        },
        "feature_extraction": {
            "min_confidence": 0.6,
            "max_text_length": 1000,
            "supported_formats": [".png", ".jpg", ".jpeg", ".pdf"]
        },
        "thresholds": {
            "low_risk": 0.3,
            "medium_risk": 0.7,
            "high_risk": 1.0
        }
    }
    
    with open("ml_config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    # Create requirements file
    create_requirements_file()
    
    # Create training script
    training_script = """#!/usr/bin/env python3
# Certificate Fraud Detection Training Script

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from certificate_fraud_detection import train_fraud_detection_model
from data_generator import train_and_evaluate_model

if __name__ == "__main__":
    print("Starting Certificate Fraud Detection Model Training...")
    detector = train_and_evaluate_model()
    print("Training completed!")
"""
    
    with open("train_model.py", "w") as f:
        f.write(training_script)
    
    logger.info("Training environment setup completed!")
    logger.info("Run 'python train_model.py' to start training")


if __name__ == "__main__":
    # Setup training environment
    setup_training_environment()
    
    # Train the model
    detector = train_and_evaluate_model()
