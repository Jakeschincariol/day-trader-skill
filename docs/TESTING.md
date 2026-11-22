# TESTING — ALPHA TRADER AI MT5

## الاختبارات الحالية
- Unit suite محلياً: **27 tests passed**، بلا MT5 terminal أو network.
- GitHub Actions run [45058026746](https://github.com/xfloki-40/day-trader-skill/actions/runs/45058026746) شغّل testين suites ونجح:
  - `python -m unittest discover -s tests -p 'test_mt5_readonly_adapter.py' -v` — 10 passed.
  - `python -m unittest discover -s tests -p 'test_alpha_mt5_risk.py' -v` — 17 passed.
- التغطية تشمل initialize failure، disconnect، symbol/tick/history، UTC، NaN، freshness، stop geometry، spread، daily loss، max positions، duplicate، account currency mismatch، و`execution_authorized=False`.

## حدود الدليل
- CI كيستعمل Fake MT5 API؛ ما كيثبتش توافق package/terminal الحقيقي ولا اتصال حساب demo.
- `loss_at_stop_account` مدخل للـrisk evaluator، ومازال ما مربوطش بحساب MT5 موثوق.
- upstream tests ما تشغلوش.
- ما تدار حتى sizing على broker specs ولا backtest ولا demo/live order.

## بوابات الاختبار التالية
1. Contract tests مع MT5 API الحقيقي على demo، قراءة فقط.
2. stale/missing data، timezone/session، spread وsymbol-spec cases.
3. sizing/risk tests عبر FX وindices حسب contract specs ديال broker، مع currency conversion وvolume step.
4. mock execution/reconciliation tests قبل أي demo execution.

أي اختبار تنفيذي مستقبلي يكون على حساب demo وبموافقة منفصلة، وما كيعطيش ضمان ربح.