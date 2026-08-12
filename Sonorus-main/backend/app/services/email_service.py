"""Transactional email via Resend's HTTP API (httpx, already a dependency
-- no new SDK needed for a single-endpoint integration like this)."""
import structlog
import httpx

from app.config import settings

logger = structlog.get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


async def send_verification_email(to_email: str, name: str, verify_url: str) -> bool:
    """Never raises -- a failed send shouldn't break signup; the account
    still exists, the user just won't get the email (can be handled with a
    resend feature later)."""
    if not settings.resend.api_key:
        logger.warning("resend_not_configured_skipping_email", to=to_email)
        return False

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #0b1740;">Verify your email</h2>
      <p style="color: #5b6478; font-size: 15px; line-height: 1.5;">
        Hi {name}, welcome to Sonorus. Confirm this is your email address to activate your account:
      </p>
      <a href="{verify_url}" style="display: inline-block; background: #2f5bff; color: #fff; padding: 12px 24px;
         border-radius: 10px; text-decoration: none; font-weight: 700; margin-top: 12px;">
        Verify email
      </a>
      <p style="color: #a3aabf; font-size: 12px; margin-top: 24px;">
        If you didn't create a Sonorus account, you can ignore this email.
      </p>
    </div>
    """

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend.api_key}", "Content-Type": "application/json"},
                json={
                    "from": f"Sonorus <{settings.resend.from_email}>",
                    "to": [to_email],
                    "subject": "Verify your Sonorus account",
                    "html": html,
                },
            )
            if res.status_code >= 400:
                logger.warning("resend_send_failed", status=res.status_code, body=res.text[:300])
                return False
            return True
    except Exception as e:
        logger.warning("resend_send_exception", error=str(e))
        return False
