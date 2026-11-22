# TASKS — ALPHA TRADER AI MT5

## منجز على branch `alpha/mt5-foundation-readonly`
- [x] تأكيد fork وإتاحة main؛ فتح branch منفصل غير محمي.
- [x] إضافة `alpha_mt5/readonly.py` وexports.
- [x] إضافة 10 tests للمحوّل بواجهة fake بدون حساب أوامر.
- [x] إضافة risk evaluator أولي fail-closed و17 tests؛ `PASS` ما كيعطيش صلاحية تنفيذ.
- [x] إضافة GitHub Actions workflow؛ آخر تشغيل كامل شغّل 27 test ونجح.
- [x] إضافة وثائق المشروع الأساسية.

## التالي — أولوية عالية
- [ ] إعداد Windows/MT5 demo environment عند المستخدم؛ ما عندناش وصول للجهاز.
- [ ] تحقق من Python وMT5 terminal/package على الجهاز المستهدف.
- [ ] تحديد broker demo، account currency/type، symbols الدقيقة، timeframes وtimezone.
- [ ] اختبار adapter ضد terminal demo الحقيقي، قراءة فقط.
- [ ] ربط risk evaluator ببيانات موثوقة من terminal/الحساب، وتأكيد أن loss estimate محسوب بعملة الحساب.
- [ ] بناء Position Sizing من MT5 contract/tick conversion وvolume step؛ مازال ما تنفذش.
- [ ] إعداد schema/config آمن بوضع READ_ONLY افتراضي.
- [ ] إضافة exposure/correlation/kill-switch والتعامل مع execution state قبل أي execution.

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