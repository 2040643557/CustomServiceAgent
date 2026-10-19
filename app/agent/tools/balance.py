def get_user_balance() -> dict:
    """查询当前用户账户余额"""
    return {
        "success": True,
        "user_id":"USER-001",
        "balance": 128.50,
        "currency":"CNY",
    }