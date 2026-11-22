# TESTING — ALPHA TRADER AI MT5

## الاختبارات الحالية
- Unit/contract mock suite: `python3 -m unittest discover -s tests -p 'test_mt5_readonly_adapter.py' -v`
- النتيجة المحلية على نسخة مطابقة للملفات المضافة: **10 tests passed**.
- تغطية: initialize failure، انقطاع terminal، health/account snapshot، symbol metadata، tick/time normalization، bars، missing symbol/tick، NaN، count validation، وshutdown بلا إرسال أمر.

## حدود الدليل
- النتيجة ديال fake MT5 API فقط؛ ما كتثبتش توافق package/terminal الحقيقي ولا اتصال حساب demo.
- ما تشغلوش upstream tests ولا repository-wide suite.
- ما كاينش CI مهيأ حتى الآن.
- ما تدار حتى backtest ولا demo/live order.

## بوابات الاختبار التالية
1. CI/local suite على كل commit.
2. Contract tests مع MT5 API الحقيقي على demo، قراءة فقط.
3. stale/missing data، timezone/session، spread وsymbol-spec cases.
4. sizing/risk tests عبر FX وindices حسب contract specs ديال broker، مع currency conversion وvolume step.
5. mock execution/reconciliation tests قبل أي demo execution.

أي اختبار تنفيذي مستقبلي يكون على حساب demo وبموافقة منفصلة، وما كيعطيش ضمان ربح.