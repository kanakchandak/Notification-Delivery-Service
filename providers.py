
import random


def send_message(provider, message):
    """
    Simulates sending an email or SMS.

    Returns:
        ("ok", None) for success
        ("transient", error) for temporary failure
        ("permanent", error) for permanent failure
    """

    recipient = message["recipient"]
    channel = message["channel"]

    if (
        channel == "email"
        and recipient.lower().endswith("@bounce.example")
    ):
        return "permanent", "bounced: recipient does not exist"

    if (
        channel == "sms"
        and recipient.startswith("+91900000")
    ):
        return "permanent", "Phone number permanently rejected"

    if provider["outage"]:
        return "transient", "503 provider unavailable"

    if random.random() < provider["fail_rate"]:
        return "transient", "Temporary provider failure"

    return "ok", None
