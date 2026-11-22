# PROJECT\_MASTER — ALPHA TRADER AI MT5

## الحالة الحالية

**Foundation / read-only prototype.** المستودع العامل هو `xfloki-40/day-trader-skill`، والتطوير كاين فـbranch `alpha/mt5-foundation-readonly`. تضاف محوّل Python للقراءة فقط و10 اختبارات باستعمال fake MT5 API؛ الاختبارات دازت محلياً. ما كاينش اتصال حقيقي بـMT5، لا demo order، لا خدمة 24/24، ولا live execution.

## الهدف

بناء منظومة modular لـMetaTrader 5 لمراقبة Forex والمؤشرات، تحليل الإشارات، إدارة المخاطر والاختبار، مع حماية رأس المال وبيانات قابلة للتدقيق. الربح غير مضمون. البداية READ\_ONLY؛ أي انتقال لتنفيذ demo أو live خاصو بوابات وموافقة منفصلة.

## المهارات المستهدفة (14)

1. Market Scanner
2. News Intelligence
3. Smart Entry
4. Dynamic Exit
5. Advanced Risk Manager
6. Position Sizing
7. Backtesting &amp; Simulation
8. MT5 Execution Engine
9. Smart Alerts
10. Performance Analyst
11. Market Sentiment Research
12. AI Strategy Lab
13. Adaptive Engine
14. Portfolio Manager

## المرجع الأصلي

المستودع الأصلي هو [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)، مبني على 11 مهارة day-trading للأسهم الأمريكية. افتراضات US equities وYahoo/SEC/Alpaca ما كتتحولش مباشرة لـMT5. أي نقل لاحق لكود upstream خاصو يحتافظ بإشعار MIT؛ المحوّل الحالي مكتوب كطبقة جديدة للقراءة فقط.

## حدود السلامة

- Python/MQL5 المحلي هو مصدر الحقيقة للحساب والسوق والمخاطر والتنفيذ.
- Risk Manager المحلي عنده veto نهائي؛ غياب أو تقادم البيانات يوقف أي دخول.
- Langdock للتنسيق والمعرفة والتحليل، ماشي لحساب اللوت أو تجاوز المخاطر.
- لا أسرار أو كلمات مرور فـGit أو prompts.
- ما كاين حتى تداول حي بلا تفويض صريح وإعداد مستقل.

راجع `ARCHITECTURE.md`, `RISK_POLICY.md`, `TESTING.md`, و`CURRENT_STATUS.md` للتفاصيل والحالة الدقيقة.