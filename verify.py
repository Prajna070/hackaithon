import json
import argparse
from mindvault.modules.unified_validator import UnifiedCertificateValidator


def main():
    parser = argparse.ArgumentParser(description='Unified Certificate Verification System')
    parser.add_argument('file_path', type=str, help='Certificate file path')
    parser.add_argument('--output', type=str, help='Output folder for processed images', default=None)
    parser.add_argument('--json', action='store_true', help='Output as JSON', default=True)
    parser.add_argument('--summary', action='store_true', help='Show validation criteria summary')
    parser.add_argument('--criteria', action='store_true', help='Show detailed validation criteria')
    
    args = parser.parse_args()

    # Initialize unified validator
    validator = UnifiedCertificateValidator()
    
    if args.summary:
        # Show validation criteria summary
        criteria = validator.get_validation_criteria_summary()
        print(json.dumps(criteria, indent=2))
        return
    
    if args.criteria:
        # Show detailed criteria
        print("\n" + "="*80)
        print("UNIFIED CERTIFICATE VALIDATION CRITERIA")
        print("="*80)
        print("\nA certificate is VALID if and only if ALL four criteria pass:")
        print("\n1. CERTIFICATE CONTENT VALIDATION (30% weight)")
        print("   - ML model confirms document is a certificate")
        print("   - Confidence >= 70%")
        print("   - Contains certificate keywords")
        print("\n2. TRADITIONAL VERIFICATION (25% weight)")
        print("   - QR code validation (if present)")
        print("   - OCR quality >= 30%")
        print("   - No duplicates detected")
        print("   - Basic authenticity score >= 50%")
        print("\n3. FRAUD DETECTION (25% weight)")
        print("   - Fraud probability <= 40%")
        print("   - Risk level: Low or Medium")
        print("   - No high-risk anomalies")
        print("\n4. CONTENT ANALYSIS (20% weight)")
        print("   - Meaningful summary extracted (>20 chars)")
        print("   - At least 1 skill extracted")
        print("   - Goal prediction successful")
        print("\nDECISION LOGIC: ALL criteria must pass for certificate to be valid")
        print("CONFIDENCE: Weighted average of individual criteria scores")
        print("="*80)
        return

    # Validate certificate using unified framework
    results = validator.validate_certificate_comprehensive(args.file_path, args.output)
    
    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human readable format
        print(f"\n{'='*60}")
        print(f"UNIFIED CERTIFICATE VALIDATION RESULT")
        print(f"{'='*60}")
        print(f"File: {results['file_path']}")
        print(f"Status: {results['status']}")
        print(f"Valid Certificate: {'YES' if results['is_valid_certificate'] else 'NO'}")
        print(f"Overall Confidence: {results['overall_confidence']:.2f}")
        
        print(f"\nCriteria Results:")
        for name, criteria_info in results['criteria_summary'].items():
            status = '✓ PASS' if criteria_info['passed'] else '✗ FAIL'
            print(f"  {criteria_info['description']}: {status} ({criteria_info['score']:.2f})")
        
        if results.get('recommendations'):
            print(f"\nRecommendations:")
            for rec in results['recommendations']:
                print(f"  • {rec}")
        
        if results.get('warnings'):
            print(f"\nWarnings:")
            for warn in results['warnings']:
                print(f"  ⚠ {warn}")
        
        print(f"\n{'='*60}")


if __name__ == '__main__':
    main()
