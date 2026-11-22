# MT5 Read-Only Adapter

## الهدف
`alpha_mt5/readonly.py` كيوفر أول جسر بيانات محلي بين Python وMetaTrader 5. النطاق الحالي قراءة فقط: terminal/account health، خصائص الرمز، tick حديث، وbars تاريخية. ما فيهش order send/modify/close، وما كيحسبش risk أو lot size.

## متطلبات التشغيل
- Windows وجهاز فيه MT5 terminal متاح للمستخدم.
- Python وMetaTrader5 Python package متوافقين مع terminal.
- افتح terminal وسجّل الدخول محلياً بالطريقة المعتادة؛ الكود ما كيقبلش login/password.
- هاد التكامل ما تجرّبش بعد على MT5 حقيقي. التوافق الفعلي خاصو test منفصل على demo وبوضع القراءة فقط.

## مثال استخدام محلي

```python
import MetaTrader5 as mt5
from alpha_mt5 import ReadOnlyMT5Adapter

adapter = ReadOnlyMT5Adapter(mt5)
try:
    adapter.connect()
    health = adapter.health()
    print("connected:", health.connected)

    # Replace EURUSD with the exact broker symbol, if available.
    quote = adapter.quote("EURUSD")
    print(quote.symbol, quote.bid, quote.ask, quote.time_utc)
finally:
    adapter.close()
```

اسم `EURUSD` غير مثال؛ الوسطاء كيستعملو أحياناً suffix/prefix وأسماء مختلفة. خاص التأكد من الاسم الفعلي داخل terminal.

## الواجهات
- `connect()` يهيّأ اتصال API بالـterminal الحالي بلا credentials.
- `health()` يرجع connected، terminal name/build، account currency/balance/equity. خلي account values محلية وما تشاركهاش بلا حاجة.
- `symbol_spec(symbol)` يرجع digits/point/tick/contract/volume/stops/freeze/trade mode/currencies؛ أي قيمة مفقودة كتظل `None`.
- `quote(symbol)` يرجع bid/ask/last/volume وتوقيت UTC.
- `bars(symbol, timeframe, count)` يرجع bar tuple؛ `timeframe` خاصو constant ديال package المتوافق.
- `close()` يوقف session ديال API.

## الاختبارات
الـunit suite كتستعمل FakeMT5 فقط، بلا terminal ولا network. شغّل من جذر المستودع:

```bash
python -m unittest discover -s tests -p 'test_mt5_readonly_adapter.py' -v
```

نتيجة هاد suite المحلية: 10 اختبارات ناجحة على mock. هاد النتيجة ما كتثبتش اتصال MT5 الحقيقي.

## تحذير
مخرجات المحوّل ماشي موافقة تداول. لا تستعملها مباشرة لتنفيذ أوامر أو sizing؛ خاص freshness validation وschema/risk gates وcurrency conversion وbroker-specific tests أولاً.