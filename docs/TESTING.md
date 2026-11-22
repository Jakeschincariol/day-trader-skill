# TESTING — ALPHA TRADER AI MT5

## الاختبارات الحالية
- Unit/contract mock suite: `python -m unittest discover -s tests -p 'test_mt5_readonly_adapter.py' -v`
- النتيجة المحلية على نسخة مطابقة للملفات المضافة: **10 tests passed**.
- GitHub Actions على الفرع: [push run](https://github.com/xfloki-40/day-trader-skill/actions/runs/45057262581) و[manual run](https://github.com/xfloki-40/day-trader-skill/actions/runs/45057274082) — بجوج `success`.
- التغطية: initialize failure، انقطاع terminal، health/account snapshot، symbol metadata، tick/time normalization، bars، missing symbol/tick، NaN، count validation، وshutdown بلا إرسال أمر.

## حدود الدليل
- CI كيستعمل Fake MT5 API فقط؛ ما كيثبتش توافق package/terminal الحقيقي ولا اتصال حساب demo.
- upstream tests ما تشغلوش.
- ما تدار حتى backtest ولا demo/live order.

## بوابات الاختبار التالية
1. Contract tests مع MT5 API الحقيقي على demo، قراءة فقط.
2. stale/missing data، timezone/session، spread وsymbol-spec cases.
3. sizing/risk tests عبر FX وindices حسب contract specs ديال broker، مع currency conversion وvolume step.
4. mock execution/reconciliation tests قبل أي demo execution.

أي اختبار تنفيذي مستقبلي يكون على حساب demo وبموافقة منفصلة، وما كيعطيش ضمان ربح.