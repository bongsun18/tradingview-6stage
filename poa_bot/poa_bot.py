"""
POA Bot - TradingView Webhook 수신 서버
트레이딩뷰 Alert → Webhook → POA Bot → 증권사 API 주문 실행

설치:
    pip install fastapi uvicorn pydantic python-dotenv

실행:
    uvicorn poa_bot:app --host 0.0.0.0 --port 8000

환경변수 (.env):
    WEBHOOK_SECRET=your_webhook_secret_key
    KIS_APPKEY=한국투자증권_APPKEY
    KIS_APPSECRET=한국투자증권_APPSECRET
    KIS_ACCTNO=계좌번호
    KIS_BASE_URL=https://openapivts.koreainvestment.com:9443  (모의투자)
"""

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import hashlib
import hmac
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("POA-Bot")

app = FastAPI(title="POA Bot", version="1.0.0")

# ──────────────────────────────────────────
# 1. 데이터 모델
# ──────────────────────────────────────────

class TradingViewAlert(BaseModel):
    """트레이딩뷰에서 오는 Webhook JSON 포맷"""
    bot: str
    action: str          # BUY or SELL
    reason: str          # STAGE2, BULL_DIV, BEAR_DIV, DEAD_CROSS, FULL_SELL
    ticker: str
    exchange: Optional[str] = None
    price: float
    stage: int
    qty_pct: int         # 포트폴리오 대비 매매 비율 (%)
    strength: Optional[str] = None  # 다이버전스 강도 (true/false)
    ts: Optional[str] = None

class OrderResult(BaseModel):
    status: str
    order_id: Optional[str] = None
    ticker: str
    action: str
    qty: Optional[int] = None
    price: float
    message: str
    timestamp: str

# ──────────────────────────────────────────
# 2. 주문 이력 저장 (간이 DB)
# ──────────────────────────────────────────

order_history = []

def save_order(result: OrderResult):
    order_history.append(result.dict())
    # 파일로도 저장
    with open("order_history.jsonl", "a") as f:
        f.write(json.dumps(result.dict(), ensure_ascii=False) + "\n")

# ──────────────────────────────────────────
# 3. 한국투자증권 API 클라이언트 (스켈레톤)
# ──────────────────────────────────────────

class KISClient:
    """한국투자증권 REST API 클라이언트"""
    
    def __init__(self):
        self.app_key = os.getenv("KIS_APPKEY", "")
        self.app_secret = os.getenv("KIS_APPSECRET", "")
        self.acct_no = os.getenv("KIS_ACCTNO", "")
        self.base_url = os.getenv("KIS_BASE_URL", "https://openapivts.koreainvestment.com:9443")
        self.token = None
    
    def get_token(self):
        """인증 토큰 발급"""
        # TODO: 한국투자증권 토큰 API 호출
        logger.info("🔑 KIS 토큰 발급 요청")
        pass
    
    def get_balance(self):
        """잔고 조회"""
        # TODO: 잔고 조회 API
        logger.info("💰 잔고 조회")
        return 10_000_000  # 임시
    
    def buy(self, ticker: str, qty: int, price: float) -> dict:
        """매수 주문"""
        logger.info(f"📈 매수 주문: {ticker} {qty}주 @ {price}")
        # TODO: 매수 주문 API 호출
        return {"status": "OK", "order_id": "MOCK_BUY_001"}
    
    def sell(self, ticker: str, qty: int, price: float) -> dict:
        """매도 주문"""
        logger.info(f"📉 매도 주문: {ticker} {qty}주 @ {price}")
        # TODO: 매도 주문 API 호출
        return {"status": "OK", "order_id": "MOCK_SELL_001"}
    
    def get_holding_qty(self, ticker: str) -> int:
        """보유 수량 조회"""
        # TODO: 보유 종목 조회 API
        return 0

kis = KISClient()

# ──────────────────────────────────────────
# 4. Webhook 검증
# ──────────────────────────────────────────

def verify_webhook(request_body: bytes, signature: str = None) -> bool:
    """Webhook 서명 검증"""
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not secret:
        return True  # 시크릿 없으면 스킵
    
    if not signature:
        return False
    
    expected = hmac.new(
        secret.encode(), request_body, hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

# ──────────────────────────────────────────
# 5. 주문 실행 로직
# ──────────────────────────────────────────

def execute_order(alert: TradingViewAlert) -> OrderResult:
    """트레이딩뷰 알림 → 주문 실행"""
    
    ticker = alert.ticker
    price = alert.price
    pct = alert.qty_pct
    
    if alert.action == "BUY":
        # 잔고 기준으로 매수 수량 계산
        balance = kis.get_balance()
        buy_amount = balance * pct / 100
        qty = int(buy_amount / price)
        
        if qty <= 0:
            return OrderResult(
                status="SKIP", ticker=ticker, action="BUY",
                price=price, message="매수 금액 부족",
                timestamp=datetime.now().isoformat()
            )
        
        result = kis.buy(ticker, qty, price)
        
        msg = f"🟢 {alert.reason}: {ticker} {qty}주 매수 @ {price:,.0f}원 (S{alert.stage})"
        logger.info(msg)
        
        return OrderResult(
            status="FILLED", order_id=result.get("order_id"),
            ticker=ticker, action="BUY", qty=qty, price=price,
            message=msg, timestamp=datetime.now().isoformat()
        )
    
    elif alert.action == "SELL":
        # 보유 수량 기준으로 매도 수량 계산
        holding = kis.get_holding_qty(ticker)
        sell_qty = int(holding * pct / 100)
        
        if sell_qty <= 0:
            return OrderResult(
                status="SKIP", ticker=ticker, action="SELL",
                price=price, message="매도할 보유 수량 없음",
                timestamp=datetime.now().isoformat()
            )
        
        result = kis.sell(ticker, sell_qty, price)
        
        emoji = "⚠️" if "DIV" in alert.reason else "🔴" if "DEAD" in alert.reason else "⬛"
        msg = f"{emoji} {alert.reason}: {ticker} {sell_qty}주 매도 @ {price:,.0f}원 ({pct}%)"
        logger.info(msg)
        
        return OrderResult(
            status="FILLED", order_id=result.get("order_id"),
            ticker=ticker, action="SELL", qty=sell_qty, price=price,
            message=msg, timestamp=datetime.now().isoformat()
        )
    
    else:
        return OrderResult(
            status="ERROR", ticker=ticker, action=alert.action,
            price=price, message=f"알 수 없는 액션: {alert.action}",
            timestamp=datetime.now().isoformat()
        )

# ──────────────────────────────────────────
# 6. API 엔드포인트
# ──────────────────────────────────────────

@app.post("/webhook", response_model=OrderResult)
async def receive_webhook(alert: TradingViewAlert, request: Request):
    """트레이딩뷰 Webhook 수신 엔드포인트"""
    
    logger.info(f"📨 Webhook 수신: {alert.action} {alert.ticker} S{alert.stage} ({alert.reason})")
    
    # 봇 이름 검증
    expected_bot = os.getenv("BOT_NAME", "6StageBot")
    if alert.bot != expected_bot:
        raise HTTPException(status_code=403, detail=f"Unknown bot: {alert.bot}")
    
    # 주문 실행
    result = execute_order(alert)
    save_order(result)
    
    return result

@app.get("/history")
async def get_history(limit: int = 50):
    """주문 이력 조회"""
    return order_history[-limit:]

@app.get("/status")
async def get_status():
    """봇 상태 조회"""
    return {
        "bot": os.getenv("BOT_NAME", "6StageBot"),
        "status": "running",
        "total_orders": len(order_history),
        "kis_connected": bool(kis.app_key),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """헬스체크"""
    return {"status": "ok"}

# ──────────────────────────────────────────
# 7. 메인
# ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
