# TODO – Payment Bypass (selenium-wire) + Manual OTP Integration

## Steps
- [x] 1. config.py – default TAMPER_ENABLED=true, ENGINE_TIMEOUT=300
- [x] 2. requirements.txt – add selenium-wire
- [x] 3. engines/request_tamper.py – rewrite with selenium-wire interceptors + JS fallback
- [x] 4. engines/engine_base.py – init_driver(use_wire), manual_otp_callback, max_runtime=300
- [x] 5. engines/threeds_bypass.py – manual_otp_callback + timeout fallback
- [x] 6. engines/engine_captcha.py, engine_nocaptcha.py, engine_advanced.py – forward manual_otp_callback, default 300
- [x] 7. checkout_runner.py – accept + forward manual_otp_callback
- [x] 8. handlers/checkout.py – thread-safe OTP waiter + callback
- [x] 9. checkout_bot.py – text_router OTP short-circuit
- [x] 10. Verify syntax (py_compile) + install requirements (selenium-wire 5.1.0 installed & verified)

