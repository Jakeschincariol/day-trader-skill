# CHANGELOG

## Initial MT5 foundation
- أُنشئ branch `alpha/mt5-foundation-readonly` في fork المستخدم؛ upstream الأصلي ما تمش تعديلو.
- تضاف Python read-only adapter: health/account summary، symbol specs، tick وbars، timestamps UTC، وقيم غير صالحة كترجع `None`.
- تضاف exports واختبارات fake MT5؛ 10 tests للمحوّل.
- تضاف وثائق المشروع الأساسية فـ`docs/`.
- تضاف GitHub Actions workflow؛ تشغيل المحوّل نجح.
- ما تضاف حتى دالة إرسال/تعديل/إغلاق، وما تدار حتى معاملة تداول.

## Risk evaluator prototype
- تضاف `alpha_mt5/risk.py`: تقييم حتمي للـproposal مع fail-closed على terminal/mode، timestamps، spread، stop، loss input، daily P/L، positions، duplicate وcurrency.
- النتيجة `PASS` ما كتمنحش التنفيذ؛ `execution_authorized` دائماً false. لا lot sizing ولا حساب MT5 فعلي لـloss حتى الآن.
- تضاف 17 اختبار للمخاطر؛ CI شغّل 10 adapter + 17 risk tests بنجاح على GitHub Actions.

## سياسة السجل
الإصدارات التالية خاصها توثق الملفات والسبب والـtests المشغلة والنتائج وأثر المخاطر/الأمان. ما يتسجلش اختبار ناجح بلا تشغيل فعلي.