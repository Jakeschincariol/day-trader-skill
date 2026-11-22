# CHANGELOG

## Initial MT5 foundation
- أُنشئ branch `alpha/mt5-foundation-readonly` في fork المستخدم؛ upstream الأصلي ما تمش تعديلو.
- تضاف Python read-only adapter: health/account summary، symbol specs، tick وbars، timestamps UTC، وقيم غير صالحة كترجع `None`.
- تضاف exports واختبارات fake MT5؛ 10 tests نجحو محلياً. لا اتصال حقيقي بMT5.
- تضاف وثائق المشروع الأساسية فـ`docs/`.
- ما تضاف حتى دالة إرسال/تعديل/إغلاق، وما تدار حتى معاملة تداول.

## سياسة السجل
الإصدارات التالية خاصها توثق الملفات والسبب والـtests المشغلة والنتائج وأثر المخاطر/الأمان. ما يتسجلش اختبار ناجح بلا تشغيل فعلي.