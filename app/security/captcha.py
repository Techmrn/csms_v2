import base64
import hmac
import hashlib
import random
import time
from app.core.config import get_settings

settings = get_settings()
CAPTCHA_VALIDITY_SECONDS = 300  # 5 minutes


def generate_numeric_captcha() -> dict:
    """
    Generates a secure, stateless 5-digit numbers-based CAPTCHA.
    Returns:
        {
            "digits": "59281",
            "token": "signed_payload",
            "svg": "<svg ...> inline svg </svg>"
        }
    """
    # 1. Generate 5 random digits (excluding confusing shapes if needed, but 0-9 is standard)
    digits = f"{random.randint(10000, 99999)}"
    timestamp = int(time.time())

    # 2. Sign the digits and timestamp with HMAC-SHA256 using the application JWT secret key
    payload = f"{digits}:{timestamp}"
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    token = f"{payload}:{signature}"

    # 3. Render clean visual SVG with interference lines and slight character offsets
    svg_elements = []
    # Background rectangle
    svg_elements.append('<rect width="180" height="46" rx="8" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.5"/>')

    # Subtle background noise lines
    colors_lines = ["#94a3b8", "#cbd5e1", "#cbd5e1", "#94a3b8"]
    for i in range(4):
        x1 = random.randint(5, 40)
        y1 = random.randint(5, 40)
        x2 = random.randint(130, 175)
        y2 = random.randint(5, 40)
        svg_elements.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colors_lines[i]}" stroke-width="1.2" stroke-dasharray="3,2"/>')

    # Draw each digit with slight rotation and vertical offset for visual anti-scraping
    x_offset = 24
    digit_colors = ["#1e293b", "#0f172a", "#1e3a8a", "#0f172a", "#1e293b"]
    for idx, digit in enumerate(digits):
        y_pos = random.randint(30, 34)
        rot = random.randint(-12, 12)
        color = digit_colors[idx % len(digit_colors)]
        svg_elements.append(
            f'<text x="{x_offset}" y="{y_pos}" fill="{color}" font-family="Courier, monospace" '
            f'font-size="26" font-weight="900" transform="rotate({rot} {x_offset} {y_pos})">{digit}</text>'
        )
        x_offset += 28

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 46" width="180" height="46" style="display:block; border-radius:8px; user-select:none;">{"".join(svg_elements)}</svg>'

    return {
        "digits": digits,
        "token": token,
        "svg": svg,
    }


def verify_numeric_captcha(user_input: str | None, token: str | None) -> bool:
    """
    Verifies that the user entered the correct digits for the signed token.
    Enforces HMAC integrity and 5-minute expiration.
    """
    if not user_input or not token:
        return False

    parts = token.split(":")
    if len(parts) != 3:
        return False

    expected_digits, ts_str, signature = parts

    try:
        timestamp = int(ts_str)
    except ValueError:
        return False

    # Check expiration (5 minutes)
    if time.time() - timestamp > CAPTCHA_VALIDITY_SECONDS:
        return False

    # Recompute signature
    expected_payload = f"{expected_digits}:{ts_str}"
    computed_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(computed_signature, signature):
        return False

    # Normalize user input (strip whitespace)
    cleaned_input = "".join(ch for ch in user_input if ch.isdigit())
    return hmac.compare_digest(cleaned_input, expected_digits)
