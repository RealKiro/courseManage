def calculate_remaining_amount(fee) -> tuple:
    """计算剩余金额，处理优惠额度。
    
    返回 (remaining_amount, discount_note)
    - remaining_amount: 剩余金额
    - discount_note: 优惠备注（如果有）
    
    逻辑：
    1. 原始剩余 = total_actual_amount - total_refund_amount - consumed_hours * hourly_fee
    2. 当剩余课时 <= 0 且原始剩余 < 0 时，用优惠额度抵扣
    3. 优惠额度 = total_receivable_amount - total_actual_amount
    """
    raw_remaining = fee.total_actual_amount - fee.total_refund_amount - fee.consumed_hours * fee.hourly_fee
    discount_note = ""
    
    if fee.remaining_hours <= 0 and raw_remaining < 0:
        discount_amount = fee.total_receivable_amount - fee.total_actual_amount
        if discount_amount > 0:
            offset = min(abs(raw_remaining), discount_amount)
            adjusted = raw_remaining + offset
            if adjusted >= 0:
                discount_note = f"补齐优惠额度{offset:.0f}元"
                raw_remaining = 0
            else:
                discount_note = f"已补齐优惠额度{discount_amount:.0f}元"
                raw_remaining = adjusted
    
    return raw_remaining, discount_note