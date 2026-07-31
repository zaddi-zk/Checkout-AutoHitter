# utils/validators.py
"""
Validation helpers for user input.
"""

import re
from typing import Dict, Optional

def is_valid_url(url: str) -> bool:
    """Check if URL is valid."""
    return url.startswith(('http://', 'https://'))

def is_valid_phone(phone: str) -> bool:
    """Basic phone validation (E.164 or US format)."""
    phone = re.sub(r'\D', '', phone)
    return len(phone) >= 10

def is_valid_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None

def parse_card_line(line: str) -> Optional[Dict[str, str]]:
    """Parse a single card line into a dictionary."""
    parts = line.split('|')
    if len(parts) >= 9:
        return {
            'number': parts[0].strip(),
            'exp_month': parts[1].strip(),
            'exp_year': parts[2].strip(),
            'cvv': parts[3].strip(),
            'name': parts[4].strip() if len(parts) > 4 else '',
            'address': parts[5].strip() if len(parts) > 5 else '',
            'city': parts[6].strip() if len(parts) > 6 else '',
            'state': parts[7].strip() if len(parts) > 7 else '',
            'zip': parts[8].strip() if len(parts) > 8 else '',
        }
    return None