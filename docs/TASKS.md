# TASKS — ALPHA TRADER AI MT5

## منجز على branch `alpha/mt5-foundation-readonly`
- [x] تأكيد fork وإتاحة main؛ فتح branch منفصل غير محمي.
- [x] إضافة `alpha_mt5/readonly.py` وexports.
- [x] إضافة tests بواجهة fake بدون حساب أوامر.
- [x] تشغيل suite المحلي على النسخة المحلية: 10 اختبارات ناجحة.
- [x] إضافة GitHub Actions workflow؛ تشغيلين على الفرع دازو بنجاح.
- [x] إضافة وثائق المشروع الأساسية.

## التالي — أولوية عالية
- [ ] إعداد Windows/MT5 demo environment عند المستخدم؛ ما عندناش وصول للجهاز.
- [ ] تحقق من Python وMT5 terminal/package على الجهاز المستهدف.
- [ ] تحديد broker demo، account currency/type، symbols الدقيقة، timeframes وtimezone.
- [ ] اختبار adapter ضد terminal demo الحقيقي، قراءة فقط.
- [ ] بناء schema/config آمن بوضع READ_ONLY افتراضي.
- [ ] Risk Manager وPosition Sizing بحسابات MT5 وfixtures.
- [ ] freshness/session/spread/kill-switch validations.

## لاحقاً
- [ ] SQLite migrations وappend-only audit trail.
- [ ] Scanner، Smart Entry وDynamic Exit كـcandidate/plans فقط.
- [ ] Mock execution + reconciliation؛ demo إرسال فقط بموافقة منفصلة.
- [ ] ربط Langdock knowledge/agents/workflows وbridge بعد مراجعة أمنية.
- [ ] Backtesting، analytics، news/sentiment، adaptive وportfolio modules.

## Blockers / شروط
- لا live execution ولا كلمات مرور/مفاتيح داخل المستودع.
- لا ندّعي اتصال MT5 أو 24/24 قبل إعداد واختبار local service فعلياً.
- ما نعلّمو حتى اختبار DONE إلا مع أمر تشغيل ونتيجة فعلية.
- الحفاظ على MIT notice إذا تم تكييف كود من upstream.