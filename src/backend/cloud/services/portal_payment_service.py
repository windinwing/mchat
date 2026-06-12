"""Portal checkout — Alipay / WeChat (9235.net same merchant)."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.portal_order import PortalOrder
from app.models.user import User
from cloud.schemas.portal import MyChannelResponse, RentChannelRequest
from cloud.services import alipay_pay, wechat_pay
from cloud.services.portal_service import PortalService
from app.services.subscription_gate import extend_subscription_end
from loguru import logger


def _order_no() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"mchat{ts}{random.randint(100000, 999999)}"


def _amount_for_template(template: ChannelTemplate, period: str) -> int:
    if period == "yearly" and template.price_yearly_cents > 0:
        return template.price_yearly_cents
    return template.price_monthly_cents


class PortalPaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_template(self, template_id: str) -> ChannelTemplate:
        result = await self.db.execute(
            select(ChannelTemplate).where(
                ChannelTemplate.id == template_id,
                ChannelTemplate.is_published == True,
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return template

    async def _resolve_renewal_channel(
        self, user: User, channel_id: str, template_id: str
    ) -> CustomerConfig:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found")
        if channel.template_id and channel.template_id != template_id:
            raise HTTPException(
                status_code=400,
                detail="Template does not match this channel",
            )
        return channel

    async def create_checkout(
        self,
        user: User,
        *,
        template_id: str,
        billing_period: str,
        channel_name: str | None,
        channel_id: str | None,
        payment_method: str,
        client_ip: str,
    ) -> dict:
        if billing_period not in ("monthly", "yearly"):
            raise HTTPException(status_code=400, detail="Invalid billing period")
        if payment_method not in ("alipay", "wechat"):
            raise HTTPException(status_code=400, detail="Invalid payment method")

        template = await self._get_template(template_id)
        amount = _amount_for_template(template, billing_period)

        renewal_channel: CustomerConfig | None = None
        if channel_id:
            renewal_channel = await self._resolve_renewal_channel(
                user, channel_id, template_id
            )

        if amount <= 0:
            if renewal_channel:
                return await self._instant_automation_renewal(
                    renewal_channel,
                    template,
                    billing_period=billing_period,
                )
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "free_template_checkout",
                    "message": "该模板无需支付，请联系管理员开通工作流权益",
                },
            )

        dup_query = select(PortalOrder).where(
            PortalOrder.user_id == user.id,
            PortalOrder.status == "pending",
        )
        if renewal_channel:
            dup_query = dup_query.where(PortalOrder.channel_id == renewal_channel.id)
        else:
            dup_query = dup_query.where(
                PortalOrder.template_id == template_id,
                PortalOrder.channel_id.is_(None),
            )
        dup = await self.db.execute(dup_query)
        pending = dup.scalar_one_or_none()
        if pending:
            order = pending
            order.payment_method = payment_method
            order.billing_period = billing_period
            order.amount_cents = amount
        else:
            period_label = "年付" if billing_period == "yearly" else "月付"
            subject = f"MChat {template.name} ({period_label})"
            if renewal_channel:
                subject = f"MChat {renewal_channel.name} 续费 ({period_label})"
            order = PortalOrder(
                order_no=_order_no(),
                user_id=user.id,
                template_id=template.id,
                channel_id=renewal_channel.id if renewal_channel else None,
                channel_name=channel_name or (renewal_channel.name if renewal_channel else None),
                billing_period=billing_period,
                amount_cents=amount,
                subject=subject,
                status="pending",
                payment_method=payment_method,
            )
            self.db.add(order)
            await self.db.flush()
            await self.db.refresh(order)

        qr_content = await self._start_payment(order, template, client_ip)
        return {
            "order_id": order.id,
            "order_no": order.order_no,
            "amount_cents": order.amount_cents,
            "subject": order.subject,
            "payment_method": payment_method,
            "qr_content": qr_content,
            "status": order.status,
            "is_renewal": bool(renewal_channel),
            "channel_id": order.channel_id,
        }

    async def _start_payment(
        self, order: PortalOrder, template: ChannelTemplate, client_ip: str
    ) -> str:
        amount_yuan = f"{order.amount_cents / 100:.2f}"
        body = template.description or order.subject
        try:
            if order.payment_method == "alipay":
                return alipay_pay.precreate_qr(
                    order.order_no, amount_yuan, order.subject, body
                )
            return wechat_pay.native_qr(
                order.order_no, order.amount_cents, order.subject, client_ip
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            ) from e

    async def get_order(self, user: User, order_id: str) -> PortalOrder:
        result = await self.db.execute(
            select(PortalOrder).where(
                PortalOrder.id == order_id,
                PortalOrder.user_id == user.id,
            )
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return order

    async def get_order_detail(self, user: User, order_id: str):
        from cloud.schemas.portal import PortalOrderDetailResponse

        order = await self.get_order(user, order_id)
        template_name: str | None = None
        t_result = await self.db.execute(
            select(ChannelTemplate.name).where(ChannelTemplate.id == order.template_id)
        )
        template_name = t_result.scalar_one_or_none()
        data = PortalOrderDetailResponse.model_validate(order)
        data.template_name = template_name
        data.is_renewal = bool(order.channel_id)
        return data

    async def get_order_invoice(self, user: User, order_id: str):
        from cloud.schemas.portal import PortalInvoiceResponse

        order = await self.get_order(user, order_id)
        if order.status != "paid":
            raise HTTPException(
                status_code=400, detail="Invoice available only for paid orders"
            )
        template_name: str | None = None
        t_result = await self.db.execute(
            select(ChannelTemplate.name).where(ChannelTemplate.id == order.template_id)
        )
        template_name = t_result.scalar_one_or_none()
        channel_name = order.channel_name
        if order.channel_id and not channel_name:
            ch_result = await self.db.execute(
                select(CustomerConfig.name).where(
                    CustomerConfig.id == order.channel_id
                )
            )
            channel_name = ch_result.scalar_one_or_none()

        return PortalInvoiceResponse(
            order_no=order.order_no,
            status=order.status,
            subject=order.subject,
            template_name=template_name,
            channel_name=channel_name,
            billing_period=order.billing_period,
            amount_cents=order.amount_cents,
            amount_yuan=f"{order.amount_cents / 100:.2f}",
            payment_method=order.payment_method,
            provider_trade_no=order.provider_trade_no,
            paid_at=order.paid_at,
            subscription_ends_at=order.subscription_ends_at,
            created_at=order.created_at,
            company_name=settings.invoice_company_name,
            company_tax_id=settings.invoice_company_tax_id or None,
            support_email=settings.invoice_support_email or None,
            buyer_email=user.email,
            buyer_phone=getattr(user, "phone", None),
        )

    async def check_and_fulfill(self, user: User, order_id: str) -> dict:
        order = await self.get_order(user, order_id)
        if order.status == "paid":
            return {
                "paid": True,
                "channel_id": order.channel_id,
                "status": order.status,
            }
        if order.status != "pending":
            return {"paid": False, "status": order.status}

        paid = await self._sync_payment_status(order)
        if paid:
            channel = await self._fulfill(order)
            return {
                "paid": True,
                "channel_id": channel.id,
                "status": "paid",
            }
        return {"paid": False, "status": order.status}

    async def _sync_payment_status(self, order: PortalOrder) -> bool:
        if order.payment_method == "alipay":
            try:
                result = alipay_pay.query_trade(order.order_no)
            except Exception as e:
                logger.warning("Alipay query {}: {}", order.order_no, e)
                return False
            if result.get("trade_status") == "TRADE_SUCCESS":
                order.status = "paid"
                order.provider_trade_no = result.get("trade_no")
                order.paid_at = datetime.now(timezone.utc)
                await self.db.flush()
                return True
            return False

        return False

    async def mark_paid(
        self,
        order_no: str,
        *,
        provider_trade_no: str | None = None,
    ) -> PortalOrder | None:
        result = await self.db.execute(
            select(PortalOrder).where(PortalOrder.order_no == order_no)
        )
        order = result.scalar_one_or_none()
        if order is None or order.status == "paid":
            return order
        order.status = "paid"
        order.provider_trade_no = provider_trade_no
        order.paid_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._fulfill(order)
        return order

    async def _instant_automation_renewal(
        self,
        channel: CustomerConfig,
        template: ChannelTemplate,
        *,
        billing_period: str,
    ) -> dict:
        """Free-template workspace: grant Pro for automation without payment."""
        sub_end = extend_subscription_end(
            channel.subscription_ends_at, billing_period
        )
        channel.plan = "pro"
        channel.subscription_ends_at = sub_end
        channel.trial_ends_at = None
        channel.enabled = True
        await self.db.flush()
        period_label = "年付" if billing_period == "yearly" else "月付"
        logger.info(
            "instant automation upgrade channel={} template={} until={}",
            channel.id,
            template.id,
            sub_end.isoformat(),
        )
        return {
            "instant": True,
            "order_id": "",
            "order_no": "",
            "amount_cents": 0,
            "subject": f"工作流编排已开通 · {channel.name} ({period_label})",
            "payment_method": "instant",
            "qr_content": "",
            "status": "paid",
            "is_renewal": True,
            "channel_id": channel.id,
        }

    async def _extend_channel_subscription(
        self, order: PortalOrder
    ) -> MyChannelResponse:
        if not order.channel_id:
            raise HTTPException(status_code=400, detail="Renewal requires channel_id")

        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == order.channel_id,
                CustomerConfig.user_id == order.user_id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=404, detail="Channel not found")

        sub_end = extend_subscription_end(
            config.subscription_ends_at, order.billing_period
        )
        config.plan = "pro"
        config.subscription_ends_at = sub_end
        config.active_order_id = order.id
        config.enabled = True
        order.subscription_ends_at = sub_end
        await self.db.flush()

        user_result = await self.db.execute(
            select(User).where(User.id == order.user_id)
        )
        user = user_result.scalar_one()
        return await PortalService(self.db).get_my_channel(user, config.id)

    async def _fulfill(self, order: PortalOrder) -> MyChannelResponse:
        if order.channel_id:
            ch_result = await self.db.execute(
                select(CustomerConfig).where(CustomerConfig.id == order.channel_id)
            )
            if ch_result.scalar_one_or_none() is not None:
                return await self._extend_channel_subscription(order)

        user_result = await self.db.execute(
            select(User).where(User.id == order.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        from cloud.services.subscription_utils import subscription_end_from_period

        sub_end = subscription_end_from_period(order.billing_period)
        order.subscription_ends_at = sub_end

        portal = PortalService(self.db)
        channel = await portal.rent_channel(
            user,
            RentChannelRequest(
                template_id=order.template_id,
                name=order.channel_name,
            ),
            paid_order=True,
            billing_period=order.billing_period,
            active_order_id=order.id,
            subscription_ends_at=sub_end,
        )
        order.channel_id = channel.id
        await self.db.flush()
        return channel

    async def list_user_orders(self, user: User) -> list:
        from cloud.schemas.portal import PortalOrderResponse

        result = await self.db.execute(
            select(PortalOrder)
            .where(PortalOrder.user_id == user.id)
            .order_by(PortalOrder.created_at.desc())
        )
        return [
            PortalOrderResponse.model_validate(o) for o in result.scalars().all()
        ]

    async def handle_alipay_notify(self, form: dict[str, str]) -> str:
        if not alipay_pay.verify_notify(form):
            return "fail"
        trade_status = form.get("trade_status")
        if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            return "success"
        order_no = form.get("out_trade_no", "")
        await self.mark_paid(order_no, provider_trade_no=form.get("trade_no"))
        await self.db.commit()
        return "success"

    async def handle_wechat_notify(self, xml_body: str) -> str:
        ok, data = wechat_pay.verify_notify_xml(xml_body)
        if not ok:
            return (
                "<xml><return_code><![CDATA[FAIL]]></return_code>"
                "<return_msg><![CDATA[SIGNERROR]]></return_msg></xml>"
            )
        if data.get("result_code") != "SUCCESS":
            return (
                "<xml><return_code><![CDATA[SUCCESS]]></return_code>"
                "<return_msg><![CDATA[OK]]></return_msg></xml>"
            )
        order_no = data.get("out_trade_no", "")
        await self.mark_paid(
            order_no, provider_trade_no=data.get("transaction_id")
        )
        await self.db.commit()
        return (
            "<xml><return_code><![CDATA[SUCCESS]]></return_code>"
            "<return_msg><![CDATA[OK]]></return_msg></xml>"
        )


def client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"
