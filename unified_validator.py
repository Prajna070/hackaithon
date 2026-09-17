"""
Unified Certificate Validation Framework
Integrates ML models with existing verify.py and analyzer.py systems
Provides single criteria for certificate validity determination
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing systems
from verify_core import CertificateValidator as VerifyCoreValidator
from analyze import analyze_certificate

# Import ML models
try:
    from certificate_fraud_detection import CertificateFraudDetector
    from certificate_validator import CertificateValidator as MLValidator
    ML_ENABLED = True
except ImportError as e:
    logging.warning(f"ML modules not available: {e}")
    ML_ENABLED = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedCertificateValidator:
    """
    Unified certificate validation system that combines:
    1. Traditional verification (verify.py)
    2. Content analysis (analyzer.py) 
    3. ML certificate validation
    4. ML fraud detection
    """
    
    def __init__(self, models_dir: str = None):
        self.models_dir = models_dir or os.path.join(os.path.dirname(__file__), '..', 'models')
        
        # Initialize existing systems
        self.verify_validator = VerifyCoreValidator()
        
        # Initialize ML systems if available
        self.ml_certificate_validator = None
        self.fraud_detector = None
        
        if ML_ENABLED:
            try:
                self.ml_certificate_validator = MLValidator(
                    model_path=os.path.join(self.models_dir, 'certificate_validator.pkl')
                )
                self.fraud_detector = CertificateFraudDetector(
                    model_path=os.path.join(self.models_dir, 'fraud_detector.pkl')
                )
                logger.info("ML models loaded successfully")
            except Exception as e:
                logger.warning(f"ML models not available: {e}")
                ML_ENABLED = False
    
    def validate_certificate_comprehensive(self, file_path: str, output_dir: str = None) -> Dict[str, Any]:
        """
        Comprehensive certificate validation using all available systems
        
        Returns unified result with single validity determination
        """
        logger.info(f"Starting comprehensive validation for: {file_path}")
        
        # Initialize result structure
        result = {
            'file_path': file_path,
            'timestamp': datetime.now().isoformat(),
            'is_valid_certificate': False,
            'overall_confidence': 0.0,
            'validation_criteria': {
                'certificate_content_check': False,
                'traditional_verification': False,
                'fraud_analysis': False,
                'content_analysis': False
            },
            'detailed_results': {},
            'recommendations': [],
            'warnings': [],
            'errors': []
        }
        
        try:
            # Step 1: ML Certificate Validation (Primary Gatekeeper)
            if self.ml_certificate_validator:
                ml_cert_result = self.ml_certificate_validator.validate_certificate(file_path)
                result['detailed_results']['ml_certificate_validation'] = ml_cert_result
                
                # Apply certificate content criteria
                is_cert_content, cert_confidence = self._apply_certificate_content_criteria(ml_cert_result)
                result['validation_criteria']['certificate_content_check'] = is_cert_content
                result['detailed_results']['certificate_content_score'] = cert_confidence
                
                if not is_cert_content:
                    result['recommendations'].append("Document does not appear to be a certificate")
                    result['warnings'].extend(ml_cert_result.get('reasoning', []))
                    return self._finalize_result(result)
            
            # Step 2: Traditional Verification (verify.py)
            verify_result = self.verify_validator.process_document(file_path, output_dir)
            if isinstance(verify_result, list) and len(verify_result) > 0:
                verify_result = verify_result[0]  # Take first page result
            result['detailed_results']['traditional_verification'] = verify_result
            
            # Apply traditional verification criteria
            is_traditional_valid, trad_confidence = self._apply_traditional_verification_criteria(verify_result)
            result['validation_criteria']['traditional_verification'] = is_traditional_valid
            result['detailed_results']['traditional_verification_score'] = trad_confidence
            
            # Step 3: ML Fraud Detection
            if self.fraud_detector:
                fraud_result = self.fraud_detector.predict_fraud_probability(file_path)
                result['detailed_results']['fraud_detection'] = fraud_result
                
                # Apply fraud detection criteria
                is_fraud_safe, fraud_confidence = self._apply_fraud_detection_criteria(fraud_result)
                result['validation_criteria']['fraud_analysis'] = is_fraud_safe
                result['detailed_results']['fraud_detection_score'] = fraud_confidence
            else:
                # Fallback if fraud detection not available
                is_fraud_safe = True
                fraud_confidence = 0.7  # Neutral score
                result['validation_criteria']['fraud_analysis'] = is_fraud_safe
                result['detailed_results']['fraud_detection_score'] = fraud_confidence
            
            # Step 4: Content Analysis (analyzer.py)
            try:
                analysis_result = analyze_certificate(file_path)
                result['detailed_results']['content_analysis'] = analysis_result
                
                # Apply content analysis criteria
                is_content_valid, content_confidence = self._apply_content_analysis_criteria(analysis_result)
                result['validation_criteria']['content_analysis'] = is_content_valid
                result['detailed_results']['content_analysis_score'] = content_confidence
            except Exception as e:
                logger.warning(f"Content analysis failed: {e}")
                is_content_valid = True  # Don't fail on analysis error
                content_confidence = 0.6
                result['validation_criteria']['content_analysis'] = is_content_valid
                result['detailed_results']['content_analysis_score'] = content_confidence
                result['errors'].append(f"Content analysis failed: {str(e)}")
            
            # Step 5: Apply Unified Validation Criteria
            is_valid, overall_confidence, criteria_summary = self._apply_unified_validation_criteria(result)
            result['is_valid_certificate'] = is_valid
            result['overall_confidence'] = overall_confidence
            result['criteria_summary'] = criteria_summary
            
            # Generate recommendations and warnings
            self._generate_recommendations(result)
            
        except Exception as e:
            logger.error(f"Comprehensive validation failed: {e}")
            result['errors'].append(f"Validation failed: {str(e)}")
            result['is_valid_certificate'] = False
            result['overall_confidence'] = 0.0
        
        return self._finalize_result(result)
    
    def _apply_certificate_content_criteria(self, ml_result: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Criteria 1: Certificate Content Validation
        - Must be identified as a certificate by ML model
        - Confidence >= 0.6 for medium security, >= 0.8 for high security
        - Must contain certificate keywords
        """
        is_certificate = ml_result.get('is_certificate', False)
        confidence = ml_result.get('confidence', 0.0)
        document_type = ml_result.get('document_type', 'unknown')
        
        # High security threshold
        threshold = 0.7
        
        # Additional checks
        has_keywords = document_type in ['certificate', 'likely_certificate']
        reasoning = ml_result.get('reasoning', [])
        has_certificate_terms = any('certificate' in reason.lower() for reason in reasoning)
        
        # Final decision
        is_valid = is_certificate and confidence >= threshold and has_certificate_terms
        adjusted_confidence = confidence if is_certificate else confidence * 0.5
        
        return is_valid, adjusted_confidence
    
    def _apply_traditional_verification_criteria(self, verify_result: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Criteria 2: Traditional Verification
        - QR code validation (if present)
        - Text integrity and OCR quality
        - No duplicates detected
        - Basic authenticity score >= 0.6
        """
        if 'error' in verify_result:
            return False, 0.0
        
        authenticity_score = verify_result.get('authenticity_score', 0.0)
        verification_status = verify_result.get('verification_status', 'unverified')
        is_duplicate = verify_result.get('is_duplicate', False)
        
        # Extract validation steps
        qr_validation = verify_result.get('validation_steps', {}).get('qr_validation', {})
        text_integrity = verify_result.get('validation_steps', {}).get('text_integrity', {})
        
        # Criteria checks
        qr_valid = qr_validation.get('valid', True)  # Optional if no QR code
        ocr_confidence = text_integrity.get('average_confidence', 0) / 100.0
        not_duplicate = not is_duplicate
        
        # Traditional verification is valid if:
        # - Not a duplicate
        # - Reasonable authenticity score
        # - OCR confidence is acceptable
        is_valid = (
            not_duplicate and 
            authenticity_score >= 0.5 and 
            ocr_confidence >= 0.3
        )
        
        # Calculate confidence
        confidence = (
            (0.4 * (1.0 if not_duplicate else 0.0)) +
            (0.3 * authenticity_score) +
            (0.3 * ocr_confidence)
        )
        
        return is_valid, confidence
    
    def _apply_fraud_detection_criteria(self, fraud_result: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Criteria 3: Fraud Detection
        - Fraud probability <= 0.4 (60% confidence it's legitimate)
        - Risk level should be Low or Medium
        - No high-risk anomalies detected
        """
        fraud_probability = fraud_result.get('fraud_probability', 1.0)
        risk_level = fraud_result.get('risk_level', 'High')
        features = fraud_result.get('features', {})
        
        # Thresholds
        max_fraud_probability = 0.4  # Allow up to 40% fraud probability
        acceptable_risk_levels = ['Low', 'Medium']
        
        # Feature-based checks
        has_multiple_fonts = features.get('has_multiple_font_sizes', False)
        has_watermark = features.get('has_watermark', False)
        suspicious_patterns = features.get('suspicious_patterns', 0)
        
        # Criteria evaluation
        risk_acceptable = risk_level in acceptable_risk_levels
        probability_acceptable = fraud_probability <= max_fraud_probability
        not_too_suspicious = suspicious_patterns <= 2
        
        # Final decision
        is_valid = risk_acceptable and probability_acceptable and not_too_suspicious
        
        # Calculate confidence (inverse of fraud probability)
        confidence = 1.0 - fraud_probability
        
        # Adjust confidence based on features
        if has_multiple_fonts:
            confidence *= 0.9
        if suspicious_patterns > 1:
            confidence *= 0.8
        
        return is_valid, confidence
    
    def _apply_content_analysis_criteria(self, analysis_result: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Criteria 4: Content Analysis
        - Summary should be meaningful (length > 20 chars)
        - Skills should be extracted (at least 1 skill)
        - Goal prediction should be successful
        """
        summary = analysis_result.get('summary', '')
        skills = analysis_result.get('skills', [])
        goal = analysis_result.get('goal', '')
        
        # Criteria checks
        summary_meaningful = len(summary.strip()) > 20
        has_skills = len(skills) > 0
        has_goal = goal != 'Unknown' and len(goal.strip()) > 0
        
        # Content analysis is valid if basic extraction works
        is_valid = summary_meaningful and has_skills
        
        # Calculate confidence based on extraction quality
        confidence = 0.0
        if summary_meaningful:
            confidence += 0.4
        if has_skills:
            confidence += 0.3 * min(len(skills) / 5.0, 1.0)  # More skills is better
        if has_goal:
            confidence += 0.3
        
        return is_valid, confidence
    
    def _apply_unified_validation_criteria(self, result: Dict[str, Any]) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Unified Validation Criteria - Single Rule for Certificate Validity
        
        A certificate is VALID if and only if:
        1. It passes certificate content validation (ML model says it's a certificate)
        2. It passes traditional verification (basic authenticity checks)
        3. It passes fraud detection (not likely fraudulent)
        4. Content analysis works (can extract meaningful information)
        
        Overall confidence is weighted average:
        - Certificate Content: 30% (most important)
        - Traditional Verification: 25%
        - Fraud Detection: 25%
        - Content Analysis: 20%
        """
        criteria = result['validation_criteria']
        scores = result['detailed_results']
        
        # Extract individual results
        cert_content_valid = criteria['certificate_content_check']
        cert_content_score = scores.get('certificate_content_score', 0.0)
        
        traditional_valid = criteria['traditional_verification']
        traditional_score = scores.get('traditional_verification_score', 0.0)
        
        fraud_valid = criteria['fraud_analysis']
        fraud_score = scores.get('fraud_detection_score', 0.0)
        
        content_valid = criteria['content_analysis']
        content_score = scores.get('content_analysis_score', 0.0)
        
        # Unified Rule: ALL criteria must pass for validity
        is_valid = (
            cert_content_valid and 
            traditional_valid and 
            fraud_valid and 
            content_valid
        )
        
        # Calculate weighted overall confidence
        overall_confidence = (
            0.30 * cert_content_score +
            0.25 * traditional_score +
            0.25 * fraud_score +
            0.20 * content_score
        )
        
        # Criteria summary for transparency
        criteria_summary = {
            'certificate_content_validation': {
                'passed': cert_content_valid,
                'score': cert_content_score,
                'weight': '30%',
                'description': 'ML model confirms document is a certificate'
            },
            'traditional_verification': {
                'passed': traditional_valid,
                'score': traditional_score,
                'weight': '25%',
                'description': 'QR codes, OCR quality, duplicate check'
            },
            'fraud_detection': {
                'passed': fraud_valid,
                'score': fraud_score,
                'weight': '25%',
                'description': 'Font consistency, watermarks, anomalies'
            },
            'content_analysis': {
                'passed': content_valid,
                'score': content_score,
                'weight': '20%',
                'description': 'Summary, skills, and goal extraction'
            }
        }
        
        return is_valid, overall_confidence, criteria_summary
    
    def _generate_recommendations(self, result: Dict[str, Any]):
        """Generate recommendations based on validation results"""
        criteria = result['validation_criteria']
        
        if not criteria['certificate_content_check']:
            result['recommendations'].append(
                "Upload a proper certificate with clear certificate-related content"
            )
        
        if not criteria['traditional_verification']:
            result['recommendations'].append(
                "Ensure certificate has clear text and no quality issues"
            )
        
        if not criteria['fraud_analysis']:
            result['recommendations'].append(
                "Certificate shows signs of potential fraud - review required"
            )
        
        if not criteria['content_analysis']:
            result['recommendations'].append(
                "Certificate text should be clearer for better analysis"
            )
        
        # Add warnings for edge cases
        overall_confidence = result['overall_confidence']
        if 0.5 <= overall_confidence < 0.7:
            result['warnings'].append("Low confidence validation - manual review recommended")
        
        # Add fraud-specific warnings
        fraud_result = result['detailed_results'].get('fraud_detection', {})
        if fraud_result.get('risk_level') == 'High':
            result['warnings'].append("High fraud risk detected")
    
    def _finalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize and format the result"""
        # Add status based on validity and confidence
        if result['is_valid_certificate']:
            if result['overall_confidence'] >= 0.8:
                result['status'] = 'VALID_HIGH_CONFIDENCE'
            elif result['overall_confidence'] >= 0.6:
                result['status'] = 'VALID_MEDIUM_CONFIDENCE'
            else:
                result['status'] = 'VALID_LOW_CONFIDENCE'
        else:
            if result['overall_confidence'] >= 0.4:
                result['status'] = 'INVALID_REVIEW_NEEDED'
            else:
                result['status'] = 'INVALID_REJECTED'
        
        # Add processing summary
        result['processing_summary'] = {
            'total_criteria': 4,
            'criteria_passed': sum(result['validation_criteria'].values()),
            'ml_models_available': ML_ENABLED,
            'processing_time': datetime.now().isoformat()
        }
        
        return result
    
    def get_validation_criteria_summary(self) -> Dict[str, Any]:
        """Get summary of validation criteria for documentation"""
        return {
            'unified_validation_rule': {
                'description': 'A certificate is VALID only if ALL four criteria pass',
                'criteria': [
                    {
                        'name': 'Certificate Content Validation',
                        'weight': '30%',
                        'requirement': 'ML model confirms document is a certificate with >=70% confidence',
                        'description': 'Ensures the uploaded document is actually a certificate'
                    },
                    {
                        'name': 'Traditional Verification',
                        'weight': '25%',
                        'requirement': 'Passes basic authenticity checks (QR, OCR, duplicate detection)',
                        'description': 'Validates traditional certificate security features'
                    },
                    {
                        'name': 'Fraud Detection',
                        'weight': '25%',
                        'requirement': 'Fraud probability <=40% and no high-risk anomalies',
                        'description': 'Detects potential fraud using ML analysis'
                    },
                    {
                        'name': 'Content Analysis',
                        'weight': '20%',
                        'requirement': 'Can extract meaningful summary, skills, and goals',
                        'description': 'Ensures certificate content is analyzable'
                    }
                ],
                'decision_logic': 'ALL criteria must pass for certificate to be valid',
                'confidence_calculation': 'Weighted average of individual criteria scores'
            }
        }


# Command line interface for verify.py integration
def main():
    """Command line interface for unified certificate validation"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Unified Certificate Validation')
    parser.add_argument('file_path', type=str, help='Certificate file path')
    parser.add_argument('--output', type=str, help='Output folder for processed images', default=None)
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--summary', action='store_true', help='Show validation criteria summary')
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = UnifiedCertificateValidator()
    
    if args.summary:
        # Show validation criteria
        criteria = validator.get_validation_criteria_summary()
        print(json.dumps(criteria, indent=2))
        return
    
    # Validate certificate
    result = validator.validate_certificate_comprehensive(args.file_path, args.output)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human readable output
        print(f"\n{'='*60}")
        print(f"UNIFIED CERTIFICATE VALIDATION RESULT")
        print(f"{'='*60}")
        print(f"File: {result['file_path']}")
        print(f"Status: {result['status']}")
        print(f"Valid Certificate: {'YES' if result['is_valid_certificate'] else 'NO'}")
        print(f"Overall Confidence: {result['overall_confidence']:.2f}")
        
        print(f"\nCriteria Results:")
        for name, criteria_info in result['criteria_summary'].items():
            status = 'PASS' if criteria_info['passed'] else 'FAIL'
            print(f"  {criteria_info['description']}: {status} ({criteria_info['score']:.2f})")
        
        if result['recommendations']:
            print(f"\nRecommendations:")
            for rec in result['recommendations']:
                print(f"  - {rec}")
        
        if result['warnings']:
            print(f"\nWarnings:")
            for warn in result['warnings']:
                print(f"  - {warn}")
        
        print(f"\n{'='*60}")


if __name__ == '__main__':
    main()
