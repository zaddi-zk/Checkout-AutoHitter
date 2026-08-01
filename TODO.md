# TODO – Payment Bypass (PaymentBypass) + Simplified Architecture

## Steps
- [x] 1. config.py – default TAMPER_ENABLED=true, ENGINE_TIMEOUT=300
- [x] 2. requirements.txt – add selenium-wire
- [x] 3. engines/request_tamper.py → engines/payment_bypass.py (new) – selenium-wire interceptors
- [x] 4. engines/engine_base.py – init_driver(use_wire=True), PaymentBypass always enabled, max_runtime=300, simplified 3DS call
- [x] 5. engines/threeds_bypass.py – simplified, no manual OTP callback, no user wait
- [x] 6. engines/engine_captcha.py, engine_nocaptcha.py, engine_advanced.py – simplified (no manual_otp_callback param)
- [x] 7. checkout_runner.py – simplified (no manual_otp_callback)
- [x] 8. handlers/checkout.py – removed OTP waiter logic
- [x] 9. checkout_bot.py – removed OTP short-circuit handlers
- [x] 10. Syntax verification – all imports pass ✅
