"""
Certificate Validation Model Training Script
Trains the AI model to distinguish between certificates and non-certificate documents
"""

import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import pickle
import logging
from certificate_validator import CertificateValidator, CertificateDataGenerator
from PIL import Image, ImageDraw, ImageFont
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CertificateTrainingDataGenerator:
    """Generate training data for certificate validation"""
    
    def __init__(self, output_dir: str = "training_data"):
        self.output_dir = output_dir
        self.certificates_dir = os.path.join(output_dir, "certificates")
        self.documents_dir = os.path.join(output_dir, "documents")
        self.create_directories()
    
    def create_directories(self):
        """Create necessary directories"""
        os.makedirs(self.certificates_dir, exist_ok=True)
        os.makedirs(self.documents_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "models"), exist_ok=True)
    
    def generate_certificate_samples(self, num_samples: int = 200) -> List[str]:
        """Generate authentic certificate samples"""
        logger.info(f"Generating {num_samples} certificate samples...")
        
        certificates = []
        
        # Certificate templates
        templates = [
            self._create_completion_certificate,
            self._create_achievement_certificate,
            self._create_training_certificate,
            self._create_workshop_certificate,
            self._create_course_certificate
        ]
        
        students = [f"Student_{i}" for i in range(1, 101)]
        courses = [
            "Python Programming", "Web Development", "Data Science", 
            "Machine Learning", "Cloud Computing", "Cybersecurity",
            "Mobile Development", "DevOps Engineering", "Blockchain",
            "Artificial Intelligence", "Database Management", "Software Engineering"
        ]
        
        institutions = [
            "Tech University", "Computer Science Institute", "Engineering College",
            "Digital Academy", "Innovation Center", "Professional Training Institute"
        ]
        
        for i in range(num_samples):
            template = random.choice(templates)
            student = random.choice(students)
            course = random.choice(courses)
            institution = random.choice(institutions)
            date = f"{random.randint(2020, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            
            filename = template(student, course, institution, date, i)
            certificates.append(filename)
        
        return certificates
    
    def generate_non_certificate_samples(self, num_samples: int = 200) -> List[str]:
        """Generate non-certificate document samples"""
        logger.info(f"Generating {num_samples} non-certificate samples...")
        
        documents = []
        
        # Document types
        doc_types = [
            self._create_invoice,
            self._create_resume,
            self._create_letter,
            self._create_report,
            self._create_form,
            self._create_notes
        ]
        
        for i in range(num_samples):
            doc_type = random.choice(doc_types)
            filename = doc_type(i)
            documents.append(filename)
        
        return documents
    
    def _create_completion_certificate(self, student: str, course: str, institution: str, date: str, index: int) -> str:
        """Create a completion certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Border
        draw.rectangle([50, 50, width-50, height-50], outline=(0, 0, 0), width=3)
        draw.rectangle([60, 60, width-60, height-60], outline=(0, 0, 0), width=1)
        
        # Title
        title = "CERTIFICATE OF COMPLETION"
        draw.text(((width - 400) // 2, 150), title, fill='black')
        
        # Institution
        inst_text = institution
        draw.text(((width - 300) // 2, 250), inst_text, fill='black')
        
        # Student name
        name_text = f"This is to certify that"
        draw.text(((width - 250) // 2, 350), name_text, fill='black')
        draw.text(((width - 200) // 2, 400), student, fill='black')
        
        # Course
        course_text = f"has successfully completed"
        draw.text(((width - 250) // 2, 500), course_text, fill='black')
        draw.text(((width - 200) // 2, 550), course, fill='black')
        
        # Date
        date_text = f"on {date}"
        draw.text(((width - 150) // 2, 650), date_text, fill='black')
        
        filename = f"certificate_completion_{index:04d}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_achievement_certificate(self, student: str, course: str, institution: str, date: str, index: int) -> str:
        """Create an achievement certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Border
        draw.rectangle([50, 50, width-50, height-50], outline=(0, 0, 255), width=3)
        
        # Title
        title = "CERTIFICATE OF ACHIEVEMENT"
        draw.text(((width - 350) // 2, 150), title, fill='black')
        
        # Student name
        draw.text(((width - 200) // 2, 300), student, fill='black')
        
        # Achievement text
        achievement = f"For outstanding achievement in {course}"
        draw.text(((width - 400) // 2, 400), achievement, fill='black')
        
        # Institution and date
        draw.text(((width - 200) // 2, 600), institution, fill='black')
        draw.text(((width - 150) // 2, 650), date, fill='black')
        
        filename = f"certificate_achievement_{index:04d}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_training_certificate(self, student: str, course: str, institution: str, date: str, index: int) -> str:
        """Create a training certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Title
        title = "TRAINING CERTIFICATE"
        draw.text(((width - 250) // 2, 150), title, fill='black')
        
        # Content
        content = [
            f"{institution}",
            "",
            "This certifies that",
            student,
            "",
            f"has successfully completed the training program",
            course,
            "",
            f"Completed on: {date}"
        ]
        
        y_pos = 250
        for line in content:
            if line:
                draw.text(((width - len(line) * 8) // 2, y_pos), line, fill='black')
            y_pos += 50
        
        filename = f"certificate_training_{index:04d}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_workshop_certificate(self, student: str, course: str, institution: str, date: str, index: int) -> str:
        """Create a workshop certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Title
        title = "WORKSHOP CERTIFICATE"
        draw.text(((width - 250) // 2, 150), title, fill='black')
        
        # Content
        draw.text(((width - 300) // 2, 300), f"Participant: {student}", fill='black')
        draw.text(((width - 350) // 2, 400), f"Workshop: {course}", fill='black')
        draw.text(((width - 200) // 2, 500), institution, fill='black')
        draw.text(((width - 150) // 2, 600), f"Date: {date}", fill='black')
        
        filename = f"certificate_workshop_{index:04d}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_course_certificate(self, student: str, course: str, institution: str, date: str, index: int) -> str:
        """Create a course certificate"""
        width, height = 1200, 900
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Title
        title = "COURSE CERTIFICATE"
        draw.text(((width - 250) // 2, 150), title, fill='black')
        
        # Content with certificate keywords
        content = [
            f"{institution} proudly presents",
            "",
            "CERTIFICATE OF COMPLETION",
            "",
            f"This certifies that {student}",
            f"has successfully completed the course",
            f"'{course}'",
            f"and has been awarded this certificate",
            f"on {date}"
        ]
        
        y_pos = 250
        for line in content:
            if line:
                draw.text(((width - min(len(line) * 8, 800)) // 2, y_pos), line, fill='black')
            y_pos += 40
        
        filename = f"certificate_course_{index:04d}.png"
        filepath = os.path.join(self.certificates_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_invoice(self, index: int) -> str:
        """Create an invoice document"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Invoice content
        content = [
            "INVOICE",
            "",
            "Invoice Number: INV-001",
            "Date: 2024-01-15",
            "",
            "Bill To:",
            "Client Company",
            "123 Business Street",
            "City, State 12345",
            "",
            "Description:",
            "Consulting Services",
            "Amount: $500.00",
            "",
            "Total Due: $500.00",
            "",
            "Payment Terms: Net 30"
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 40
        
        filename = f"document_invoice_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_resume(self, index: int) -> str:
        """Create a resume document"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Resume content
        content = [
            "JOHN DOE",
            "123 Main Street",
            "City, State 12345",
            "Phone: (555) 123-4567",
            "Email: john.doe@email.com",
            "",
            "OBJECTIVE",
            "Seeking a challenging position in software development",
            "",
            "EXPERIENCE",
            "Software Engineer - Tech Company",
            "2020 - Present",
            "- Developed web applications",
            "- Maintained databases",
            "",
            "EDUCATION",
            "Bachelor of Science in Computer Science",
            "State University",
            "2016 - 2020"
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 35
        
        filename = f"document_resume_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_letter(self, index: int) -> str:
        """Create a business letter"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Letter content
        content = [
            "John Doe",
            "123 Main Street",
            "City, State 12345",
            "",
            "January 15, 2024",
            "",
            "Hiring Manager",
            "Tech Company",
            "456 Business Ave",
            "City, State 67890",
            "",
            "Dear Hiring Manager,",
            "",
            "I am writing to express my interest in the Software Developer position.",
            "With my experience in web development and database management,",
            "I believe I would be a valuable addition to your team.",
            "",
            "Sincerely,",
            "John Doe"
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 35
        
        filename = f"document_letter_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_report(self, index: int) -> str:
        """Create a business report"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Report content
        content = [
            "QUARTERLY BUSINESS REPORT",
            "Q1 2024",
            "",
            "Executive Summary",
            "This report summarizes the business performance for Q1 2024.",
            "",
            "Key Metrics:",
            "- Revenue: $1,250,000",
            "- Expenses: $850,000",
            "- Profit: $400,000",
            "",
            "Analysis",
            "Revenue increased by 15% compared to Q1 2023.",
            "Expenses remained stable with slight inflation adjustments.",
            "",
            "Recommendations",
            "Continue current growth strategies.",
            "Explore new market opportunities."
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 35
        
        filename = f"document_report_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_form(self, index: int) -> str:
        """Create a form document"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Form content
        content = [
            "APPLICATION FORM",
            "",
            "Personal Information:",
            "First Name: _________________",
            "Last Name: _________________",
            "Address: ____________________",
            "City: ________ State: ____ ZIP: _____",
            "",
            "Contact Information:",
            "Phone: _______________________",
            "Email: _______________________",
            "",
            "Please check all that apply:",
            "[ ] Full-time position",
            "[ ] Part-time position",
            "[ ] Contract work",
            "[ ] Internship",
            "",
            "Signature: ___________________",
            "Date: _______________________"
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 40
        
        filename = f"document_form_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def _create_notes(self, index: int) -> str:
        """Create meeting notes"""
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Notes content
        content = [
            "MEETING NOTES",
            "Date: January 15, 2024",
            "Attendees: John, Mary, Bob, Sarah",
            "",
            "Agenda:",
            "1. Project status update",
            "2. Budget review",
            "3. Next steps",
            "",
            "Discussion:",
            "- Project is on schedule",
            "- Budget needs adjustment for Q2",
            "- Additional resources required",
            "",
            "Action Items:",
            "- John: Prepare budget proposal",
            "- Mary: Update project timeline",
            "- Bob: Resource planning",
            "",
            "Next meeting: January 22, 2024"
        ]
        
        y_pos = 50
        for line in content:
            draw.text((50, y_pos), line, fill='black')
            y_pos += 35
        
        filename = f"document_notes_{index:04d}.png"
        filepath = os.path.join(self.documents_dir, filename)
        img.save(filepath)
        return filename
    
    def create_training_dataset(self, num_certificates: int = 200, num_documents: int = 200):
        """Create complete training dataset"""
        logger.info("Creating training dataset for certificate validation...")
        
        # Generate certificates
        certificate_files = self.generate_certificate_samples(num_certificates)
        
        # Generate non-certificates
        document_files = self.generate_non_certificate_samples(num_documents)
        
        # Create labels file
        training_data = []
        
        # Add certificates (label = 1)
        for filename in certificate_files:
            training_data.append({
                'filename': filename,
                'filepath': os.path.join(self.certificates_dir, filename),
                'label': 1,  # 1 for certificate
                'category': 'certificate'
            })
        
        # Add documents (label = 0)
        for filename in document_files:
            training_data.append({
                'filename': filename,
                'filepath': os.path.join(self.documents_dir, filename),
                'label': 0,  # 0 for non-certificate
                'category': 'document'
            })
        
        # Save to CSV
        df = pd.DataFrame(training_data)
        labels_file = os.path.join(self.output_dir, "validation_labels.csv")
        df.to_csv(labels_file, index=False)
        
        logger.info(f"Training dataset created with {len(training_data)} samples")
        logger.info(f"Labels saved to {labels_file}")
        
        return labels_file


def train_certificate_validation_model():
    """Train the certificate validation model"""
    logger.info("Starting certificate validation model training...")
    
    # Generate training data
    generator = CertificateTrainingDataGenerator()
    labels_file = generator.create_training_dataset(num_certificates=150, num_documents=150)
    
    # Load training data
    df = pd.read_csv(labels_file)
    
    # Initialize validator
    validator = CertificateValidator()
    
    # Extract features for all samples
    training_features = []
    training_labels = []
    
    logger.info("Extracting features from training samples...")
    
    for index, row in df.iterrows():
        try:
            features = validator.extract_features(row['filepath'])
            training_features.append(features)
            training_labels.append(row['label'])
            
            if (index + 1) % 50 == 0:
                logger.info(f"Processed {index + 1}/{len(df)} samples")
                
        except Exception as e:
            logger.error(f"Error processing {row['filename']}: {e}")
            continue
    
    if len(training_features) == 0:
        logger.error("No features extracted. Training failed.")
        return None
    
    # Train model
    logger.info("Training certificate validation model...")
    validator.train_model(training_features, training_labels)
    
    # Evaluate model
    if len(training_features) > 20:
        # Split for evaluation
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(training_features, training_labels, test_size=0.2, random_state=42)
        
        # Train on training set
        validator.train_model(X_train, y_train)
        
        # Test on validation set
        correct_predictions = 0
        for i, features in enumerate(X_test):
            result = validator.validate_certificate("dummy_path")  # We'll use the features directly
            # Since we can't easily test with file paths, we'll use the model directly
            feature_vector = validator._prepare_features_for_model(features)
            prediction = validator.model.predict_proba(feature_vector)[0]
            predicted_label = 1 if prediction[1] > 0.5 else 0
            
            if predicted_label == y_test[i]:
                correct_predictions += 1
        
        accuracy = correct_predictions / len(y_test)
        logger.info(f"Model validation accuracy: {accuracy:.2f}")
    
    # Save model
    model_path = os.path.join(generator.output_dir, "models", "certificate_validator.pkl")
    validator.save_model()
    
    logger.info("Certificate validation model training completed!")
    return validator


if __name__ == "__main__":
    # Train the certificate validation model
    validator = train_certificate_validation_model()
    
    if validator:
        # Test with a sample
        test_files = [
            "training_data/certificates/certificate_completion_0001.png",
            "training_data/documents/document_invoice_0001.png"
        ]
        
        for test_file in test_files:
            if os.path.exists(test_file):
                result = validator.validate_certificate(test_file)
                print(f"\nResults for {os.path.basename(test_file)}:")
                print(f"Is Certificate: {result['is_certificate']}")
                print(f"Confidence: {result['confidence']:.2f}")
                print(f"Document Type: {result['document_type']}")
                print(f"Reasoning: {', '.join(result['reasoning'])}")
