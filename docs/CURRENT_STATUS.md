# CURRENT_STATUS — ALPHA TRADER AI MT5

## الحالة
**Foundation / prototype.** الفرع الحالي: `alpha/mt5-foundation-readonly` فـ`xfloki-40/day-trader-skill`، مبني من `main` بلا تعديل upstream مباشرة.

## VERIFIED فهاد المرحلة
- GitHub fork موجود وقابل للقراءة والكتابة عبر integration.
- تضاف `alpha_mt5/readonly.py` لقراءة terminal/account health، symbol metadata، ticks وbars.
- تضاف 10 اختبارات على fake MT5 API؛ شغّلت محلياً ونجحات كلها.
- adapter لا يرسل أوامر؛ الاختبارات ما كتحتاجش MetaTrader5 package ولا network.
- ملفات المعرفة الأساسية تضافت تحت `docs/`.

## مازال ما تجرّبش / ما متاحش
- الاتصال بMT5 terminal حقيقي أو account demo.
- Windows host ديال المستخدم، تثبيت Python package، broker specs، symbols/timeframes.
- اختبارات upstream، CI على GitHub، live/paper/demo execution أو backtest.
- local always-on service أو bridge مع Langdock؛ ما كاينش تشغيل 24/24 من هاد المحادثة.
- Langdock knowledge base/agents/workflows للمشروع ما تهيأوش هنا.

## القيود الحالية
- مخرجات adapter ماشي risk approval؛ freshness/schema/strategy/sizing gates مازال ما تبناوش.
- balance/equity حقول محلية؛ ما خاصهاش تتشارك تلقائياً مع cloud.
- ما كاين لا أمر تداول لا حساب حي لا مفاتيح/كلمات مرور فالمستودع.

## الخطوة التالية
إضافة CI وتحديد إعدادات demo/instruments من المستخدم، ثم اختبار read-only على MT5 الحقيقي بعد ما يكون الجهاز والإعداد متاحين. أي مرحلة execution كتحتاج موافقة مستقلة ومراجعة risk.