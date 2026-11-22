# RISK_POLICY — ALPHA TRADER AI MT5

## أوضاع التشغيل
- `READ_ONLY`: الوضع الحالي؛ قراءة market/account metadata فقط.
- `DEMO_PROPOSAL`: تحليل/اقتراح بدون إرسال أمر.
- `DEMO_APPROVED`: غير لطلب demo محدد بعد موافقة بشرية ونجاح local Risk gate؛ غير مطبق حالياً.
- `LIVE_DISABLED`: live execution ممنوع افتراضياً؛ ما كاين حتى تفويض live.

## شروط block الإلزامية لأي دخول مستقبلي
يرفض النظام الدخول إذا account/mode ما واضحش، terminal غير متصل، البيانات ناقصة أو قديمة، symbol specs مجهولة، session/spread غير مقبولين، stop غير صالح، sizing أو تحويل العملة غير قابل للتحقق، limits/exposure/margin متجاوزة، intent مكرر، نتيجة تنفيذ سابقة مجهولة، أو risk service فشل.

## حساب المخاطر
- ما نفترضوش نسبة أو قيمة مالية للمخاطرة؛ المستخدم يحدد limits بوضوح.
- sizing يعتمد على خصائص العقد وtick والعملة من MT5/الوسيط، ويقرب volume للأسفل.
- أي قيمة NaN/Inf أو metadata ناقصة تعتبر invalid، ماشي قيمة صفرية صالحة.
- stop-loss ماشي ضمان للخسارة القصوى بسبب gaps/slippage.
- Risk Manager المحلي عنده veto نهائي؛ لا AI ولا Strategy ولا Executor يقدر يلغيه أو يرفع limit تلقائياً.

## التنفيذ والتعافي
- ما كاين حالياً order sender.
- إذا تضاف مستقبلاً: سجّل intent/fingerprint قبل الإرسال، تحقق مرة أخرى من snapshot، وافحص retcode وticket/deal ثم reconcile.
- timeout أو جواب ملتبس = UNKNOWN؛ ممنوع blind retry قبل المطابقة مع حالة terminal.
- kill switch يمنع entries الجديدة؛ أي مسار للخروج/تقليل التعرض يبقى منفصلاً ويخضع للتحقق المحلي.

## الأسرار والبيانات
- ممنوع commit ديال login/password/API keys أو تخزينها فـprompts/Knowledge.
- بيانات balance/equity تبقى محلية وتُشارك بأقل قدر وبعد مراجعة الحاجة.
- bridge مستقبلي ما يقبلش shell، raw code، أو أفعال غير محددة؛ typed allow-list فقط.

أي تغيير لحدود المخاطر يتطلب قرار موثق، اختبار allow/block، وموافقة بشرية؛ لا توجد ضمانات للربح.