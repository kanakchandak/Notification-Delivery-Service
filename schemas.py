import re
from typing import Literal
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator
)


class MessageRequest(BaseModel):

    model_config = ConfigDict(populate_by_name=True)

    channel: Literal["email", "sms"]
    category: Literal["transactional", "marketing"]

    recipient: str = Field(alias="to")

    subject: str | None = None

    body: str = Field(min_length=1, max_length=2000)

    idempotency_key: str | None = None

    @model_validator(mode="after")
    def validate_message(self):

        if self.channel == "email":

            email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

            if not re.fullmatch(email_pattern, self.recipient):
                raise ValueError("Invalid email address")

            if len(self.recipient) > 254:
                raise ValueError("Email address is too long")

            if not self.subject or not 1 <= len(self.subject) <= 150:
                raise ValueError(
                    "Email subject must be 1-150 characters"
                )

            if len(self.body) > 2000:
                raise ValueError(
                    "Email body must be at most 2000 characters"
                )

        elif self.channel == "sms":

            phone_pattern = r"^\+[1-9][0-9]{7,14}$"

            if not re.fullmatch(phone_pattern, self.recipient):
                raise ValueError("Invalid phone number")

            if len(self.body) > 480:
                raise ValueError(
                    "SMS body must be at most 480 characters"
                )

            if self.subject is not None:
                raise ValueError(
                    "SMS messages cannot have a subject"
                )

        return self


class ProviderUpdate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    fail_rate: float | None = Field(
        default=None,
        ge=0,
        le=0.5
    )

    outage: bool | None = None

    @model_validator(mode="after")
    def validate_update(self):

        if self.fail_rate is None and self.outage is None:
            raise ValueError(
                "At least one provider setting must be provided"
            )

        return self
