# CURRENT_STATUS — ALPHA TRADER AI MT5

## الحالة
**Foundation / prototype.** الفرع الحالي: `alpha/mt5-foundation-readonly` فـ`xfloki-40/day-trader-skill`، مبني من `main` بلا تعديل upstream مباشرة.

## VERIFIED فهاد المرحلة
- GitHub fork موجود وقابل للقراءة والكتابة عبر integration.
- `alpha_mt5/readonly.py`: adapter لقراءة terminal/account health، symbol metadata، ticks وbars؛ لا دوال order send/modify/close.
- `alpha_mt5/risk.py`: evaluator أولي fail-closed؛ كيتحقق من freshness، spread، stop، loss input، daily P/L، positions، duplicate وmode. `execution_authorized` دائماً false.
- اختبارات محلية: 10 للمحوّل + 17 للمخاطر = 27 ناجحة.
- GitHub Actions run [45058026746](https://github.com/xfloki-40/day-trader-skill/actions/runs/45058026746) شغّل testين suites كاملة ونجح: 10 + 17.
- وثائق المشروع الأساسية تضافت تحت `docs/`.

## مازال ما تجرّبش / ما متاحش
- الاتصال بMT5 terminal حقيقي أو account demo.
- Windows host ديال المستخدم، تثبيت Python package، broker specs، symbols/timeframes.
- sizing أوامر حقيقي؛ مازال ما كاينش ربط لـloss input بحساب موثوق من MT5.
- upstream tests، backtest، أو demo/live order.
- local always-on service أو bridge مع Langdock؛ ما كاينش تشغيل 24/24 من هاد المحادثة.
- Langdock knowledge base/agents/workflows للمشروع ما تهيأوش هنا.

## القيود الحالية
- Risk evaluator prototype فقط؛ `PASS` ماشي موافقة تنفيذ ولا ضمان للخسارة القصوى.
- أي مدخل ناقص/قديم/غير متوافق خاصو يوقف الدخول.
- balance/equity حقول محلية؛ ما خاصهاش تتشارك تلقائياً مع cloud.
- ما كاين لا أمر تداول لا حساب حي لا مفاتيح/كلمات مرور فالمستودع.

## الخطوة التالية
إعداد بيئة Windows/MT5 demo عند المستخدم ثم اختبار read-only على terminal حقيقي. قبل أي تنفيذ، نربط risk بحساب MT5 للاحتمال/الخسارة ونبني sizing على contract specs، ونختبرهم. أي مرحلة execution كتحتاج موافقة مستقلة ومراجعة risk.