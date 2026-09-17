from typing import Dict, Any, List

# Import the consolidated validator from within the package
from .verify_core import CertificateValidator

_validator = CertificateValidator()


def _first_result(results: List[Dict]) -> Dict[str, Any]:
    if isinstance(results, list) and results:
        return results[0]
    return {'verification_status': 'unverified', 'validation_steps': {}}


def verify_certificate(file_path: str) -> Dict[str, Any]:
    """
    Wrapper expected by Flask app.
    Returns a dict with keys: verified (bool), reason (str), event_date (str), plus raw results.
    """
    try:
        if file_path.lower().endswith('.pdf'):
            res = _first_result(_validator.process_document(file_path))
        else:
            res = _validator.validate_certificate(file_path)

        status = res.get('verification_status', 'unverified')
        verified = status == 'verified'

        # Prefer summary as human-readable reason; fallback to status
        reason = res.get('summary') or status

        # Try to derive an event_date from metadata when available
        meta_file_info = (
            res.get('validation_steps', {})
              .get('metadata_analysis', {})
              .get('file_info', {})
        )
        event_date = meta_file_info.get('modified') or meta_file_info.get('created')

        return {
            'verified': bool(verified),
            'reason': reason or '',
            'event_date': event_date or '',
            'raw': res,
        }
    except Exception as e:
        return {
            'verified': False,
            'reason': f'Verification error: {str(e)}',
            'event_date': '',
        }
