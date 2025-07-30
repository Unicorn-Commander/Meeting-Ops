"""
SSL Service for Unicorn Commander Meeting Ops
Handles checking SSL certificate status and renewal.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import subprocess

logger = logging.getLogger(__name__)

class SSLService:
    def __init__(self):
        self.cert_path_base = "/etc/letsencrypt/live/"

    def _get_cert_paths(self, domain: str) -> Dict[str, str]:
        return {
            "fullchain": os.path.join(self.cert_path_base, domain, "fullchain.pem"),
            "privkey": os.path.join(self.cert_path_base, domain, "privkey.pem"),
            "chain": os.path.join(self.cert_path_base, domain, "chain.pem"),
        }

    def get_certificate_status(self, domain: str) -> Dict[str, Any]:
        """Checks the status of the SSL certificate for a given domain."""
        paths = self._get_cert_paths(domain)
        status = {
            "domain": domain,
            "configured": False,
            "valid": False,
            "expires_in_days": None,
            "expiration_date": None,
            "auto_renewal_enabled": False,
            "message": ""
        }

        if not os.path.exists(paths["fullchain"]):
            status["message"] = "Certificate files not found. Run setup-ssl.sh to configure."
            return status

        try:
            # Check expiration date using openssl
            cmd = ["openssl", "x509", "-in", paths["fullchain"], "-noout", "-enddate"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            end_date_str = result.stdout.strip().split("=")[1]
            # Example: notAfter=Jul 25 12:00:00 2026 GMT
            expiration_date = datetime.strptime(end_date_str, "%b %d %H:%M:%S %Y %Z")
            
            status["configured"] = True
            status["expiration_date"] = expiration_date.isoformat()
            
            time_remaining = expiration_date - datetime.now(expiration_date.tzinfo) # Use tzinfo for comparison
            status["expires_in_days"] = time_remaining.days

            if time_remaining.total_seconds() > 0:
                status["valid"] = True
                status["message"] = "Certificate is valid."
            else:
                status["valid"] = False
                status["message"] = "Certificate has expired!"

            # Check for Certbot auto-renewal timer
            try:
                timer_check = subprocess.run(["systemctl", "list-timers", "certbot.timer"], capture_output=True, text=True, check=False)
                if "certbot.timer" in timer_check.stdout and "active" in timer_check.stdout:
                    status["auto_renewal_enabled"] = True
            except Exception as e:
                logger.warning(f"Could not check certbot.timer: {e}")
                status["message"] += " Could not verify auto-renewal timer."

        except subprocess.CalledProcessError as e:
            status["message"] = f"Error checking certificate with openssl: {e.stderr.strip()}"
            logger.error(status["message"])
        except Exception as e:
            status["message"] = f"An unexpected error occurred: {e}"
            logger.error(status["message"])
            
        return status

    def trigger_renewal(self) -> Dict[str, Any]:
        """Triggers a manual Certbot renewal attempt."""
        try:
            cmd = ["sudo", "certbot", "renew", "--force-renewal"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Certbot renewal output: {result.stdout}")
            if "Congratulations" in result.stdout:
                return {"status": "success", "message": "Certificate renewal successful."}
            else:
                return {"status": "info", "message": "Certbot renewal command executed, but no new certificate issued. Check logs.", "details": result.stdout}
        except subprocess.CalledProcessError as e:
            logger.error(f"Certbot renewal failed: {e.stderr}")
            return {"status": "error", "message": f"Certificate renewal failed: {e.stderr.strip()}"}
        except Exception as e:
            logger.error(f"An unexpected error occurred during renewal: {e}")
            return {"status": "error", "message": str(e)}

ssl_service = SSLService()