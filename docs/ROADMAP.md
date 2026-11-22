# ROADMAP — ALPHA TRADER AI MT5

المراحل بلا مواعيد مضمونة؛ كل انتقال مربوط بدليل اختبار ومراجعة سلامة.

## P0 — Foundation/access
- [x] مراجعة upstream والـMIT license بشكل أولي.
- [x] تأكيد fork وإتاحة branch تطوير منفصل.
- [x] إضافة وثائق المشروع الأساسية.
- [x] إضافة read-only adapter ونموذج tests offline.
- [x] إعداد CI وتشغيل اختبارات المحوّل والمخاطر بنجاح على GitHub Actions.

## P1 — Local developer foundation
- [ ] إعداد Windows/MT5 demo environment عند المستخدم؛ لا وصول محلي متاح حالياً.
- [ ] تثبيت/التحقق من MetaTrader5 Python API على الجهاز المستهدف.
- [ ] schemas/config versioning وlogging آمن.
- [ ] اختبارات contract على terminal demo لhealth/symbol/tick/rates.
- [ ] SQLite migrations وappend-only audit trail.
- **Exit gate:** اختبار فعلي read-only على terminal demo؛ لا أوامر.

## P2 — Deterministic core
- [x] risk evaluator أولي fail-closed مع tests؛ يعتمد على context/limits معطاة ولا يعطي execution authorization.
- [ ] ربط risk بمصادر موثوقة من MT5، وحساب loss بعملة الحساب واختبار جميع الحدود.
- [ ] Position sizing حسب MT5 contract/tick/currency conversion؛ تقريب volume للأسفل.
- [ ] Market Scanner محدود للـForex والمؤشرات اللي يحددها المستخدم.
- [ ] Smart Entry/Dynamic Exit خطط paper-only.
- **Exit gate:** edge cases وcurrency conversion وvolume step مجرّبة على broker specs.

## P3 — Paper/demo monitoring
- [ ] alerts وposition monitoring/reconciliation.
- [ ] mock execution interface مع duplicate/timeout tests.
- [ ] أي إرسال demo يحتاج طلب مستقل وموافقة بشرية محلية.
- **Exit gate:** demo integration موثقة بلا حالات أوامر مجهولة.

## P4 — Research
- [ ] MT5 historical backtesting مع spread/commission/slippage/swap.
- [ ] Performance Analyst، News Intelligence وSentiment بمصادر موثوقة ومؤرخة.
- **Exit gate:** تقارير قابلة لإعادة الإنتاج وOOS منفصل.

## P5 — Advanced
- [ ] AI Strategy Lab، Adaptive Engine وPortfolio Manager كمقترحات مع versioning/rollback.
- [ ] لا نشر تلقائي للاستراتيجيات ولا زيادة تلقائية للمخاطر.

## P6 — Langdock orchestration/availability
- [ ] central knowledge base، agents/workflows، integration آمنة بعد مراجعة إعدادات workspace.
- [ ] local always-on service + bridge يُهيّأ ويُختبر عند المستخدم؛ الدردشة الدردشة وحدها ما كتخدمش 24/24.
- **Exit gate:** outage cloud ما يتجاوزش local risk gate، ومراقبة health واضحة.

## Live eligibility
مقفول افتراضياً. يتطلب تفويض صريح منفصل، sign-off على demo، مراجعة مستقلة للمخاطر، kill switch، reconciliation، وسجل أداء كافٍ.