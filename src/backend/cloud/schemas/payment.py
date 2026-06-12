"""Portal payment schemas."""

from pydantic import BaseModel, Field


class CreateCheckoutRequest(BaseModel):
    template_id: str = Field(..., min_length=1)
    billing_period: str = Field("monthly", pattern=r"^(monthly|yearly)$")
    channel_name: str | None = Field(None, max_length=200)
    channel_id: str | None = Field(
        None,
        description="Renew existing channel (extends subscription_ends_at)",
    )
    payment_method: str = Field(..., pattern=r"^(alipay|wechat)$")


class CheckoutResponse(BaseModel):
    order_id: str = ""
    order_no: str = ""
    amount_cents: int
    subject: str
    payment_method: str
    qr_content: str = ""
    status: str
    is_renewal: bool = False
    channel_id: str | None = None
    instant: bool = False


class OrderStatusResponse(BaseModel):
    paid: bool
    status: str
    channel_id: str | None = None
