package com.jakeschincariol.daytradersignals;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public final class MainActivity extends Activity {
    private static final Pattern TICKER_PATTERN = Pattern.compile("[A-Za-z0-9.^=-]{1,15}");
    private static final int BACKGROUND = Color.rgb(10, 15, 29);
    private static final int CARD = Color.rgb(20, 29, 48);
    private static final int TEXT = Color.rgb(236, 241, 250);
    private static final int MUTED = Color.rgb(158, 173, 194);
    private static final int ACCENT = Color.rgb(92, 161, 255);
    private static final int GREEN = Color.rgb(105, 220, 167);
    private static final int RED = Color.rgb(255, 133, 133);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private EditText tickerInput;
    private Button analyzeButton;
    private LinearLayout results;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        setContentView(createContent());
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View createContent() {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(BACKGROUND);

        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(20), dp(28), dp(20), dp(30));
        scrollView.addView(page);

        TextView title = text(getString(R.string.title), 28, TEXT, true);
        page.addView(title);
        TextView subtitle = text(getString(R.string.subtitle), 15, MUTED, false);
        addGap(page, 6);
        page.addView(subtitle);

        LinearLayout searchCard = card();
        addGap(page, 22);
        page.addView(searchCard);
        tickerInput = new EditText(this);
        tickerInput.setSingleLine(true);
        tickerInput.setHint(getString(R.string.ticker_hint));
        tickerInput.setHintTextColor(MUTED);
        tickerInput.setTextColor(TEXT);
        tickerInput.setTextSize(17);
        tickerInput.setInputType(EditorInfo.TYPE_CLASS_TEXT | EditorInfo.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        tickerInput.setImeOptions(EditorInfo.IME_ACTION_DONE);
        tickerInput.setFilters(new InputFilter[] {
                new InputFilter.AllCaps(), new InputFilter.LengthFilter(15)
        });
        searchCard.addView(tickerInput, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(52)));

        analyzeButton = new Button(this);
        analyzeButton.setText(getString(R.string.analyze));
        analyzeButton.setTextColor(Color.WHITE);
        analyzeButton.setBackgroundTintList(ColorStateList.valueOf(ACCENT));
        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(52));
        buttonParams.topMargin = dp(12);
        searchCard.addView(analyzeButton, buttonParams);
        analyzeButton.setOnClickListener(view -> analyzeTicker());
        tickerInput.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                analyzeTicker();
                return true;
            }
            return false;
        });

        TextView disclaimer = text(getString(R.string.disclaimer), 13, MUTED, false);
        addGap(page, 14);
        page.addView(disclaimer);

        results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        addGap(page, 22);
        page.addView(results);
        return scrollView;
    }

    private void analyzeTicker() {
        String ticker = tickerInput.getText().toString().trim().toUpperCase(Locale.ROOT);
        if (!TICKER_PATTERN.matcher(ticker).matches()) {
            showMessage(getString(R.string.error_invalid_ticker), RED);
            return;
        }

        analyzeButton.setEnabled(false);
        analyzeButton.setText(getString(R.string.loading));
        results.removeAllViews();
        executor.execute(() -> {
            try {
                MarketAnalysis analysis = fetchAnalysis(ticker);
                mainHandler.post(() -> showAnalysis(analysis));
            } catch (HttpStatusException exception) {
                mainHandler.post(() -> showMessage(
                        getString(R.string.error_http, exception.statusCode), RED));
            } catch (InsufficientDataException exception) {
                mainHandler.post(() -> showMessage(getString(R.string.error_data), RED));
            } catch (IOException | JSONException exception) {
                mainHandler.post(() -> showMessage(getString(R.string.error_network), RED));
            } finally {
                mainHandler.post(() -> {
                    analyzeButton.setEnabled(true);
                    analyzeButton.setText(getString(R.string.analyze));
                });
            }
        });
    }

    private MarketAnalysis fetchAnalysis(String ticker) throws IOException, JSONException {
        HttpURLConnection connection = null;
        try {
            URL url = new URL("https://query1.finance.yahoo.com/v8/finance/chart/"
                    + ticker + "?range=6mo&interval=1d");
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(10_000);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("User-Agent", "DayTraderSignals/1.0 (Android)");

            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                throw new HttpStatusException(status);
            }

            JSONObject root = new JSONObject(readStream(connection.getInputStream()));
            JSONObject chart = root.getJSONObject("chart");
            if (chart.optJSONArray("error") != null && !chart.isNull("error")) {
                throw new InsufficientDataException();
            }
            JSONArray results = chart.getJSONArray("result");
            if (results.length() == 0) {
                throw new InsufficientDataException();
            }
            JSONObject result = results.getJSONObject(0);
            JSONObject meta = result.getJSONObject("meta");
            JSONArray closes = result.getJSONObject("indicators")
                    .getJSONArray("quote")
                    .getJSONObject(0).getJSONArray("close");

            List<Double> validCloses = new ArrayList<>();
            for (int i = 0; i < closes.length(); i++) {
                double close = closes.optDouble(i, Double.NaN);
                if (Double.isFinite(close) && close > 0) {
                    validCloses.add(close);
                }
            }
            if (validCloses.size() < 51) {
                throw new InsufficientDataException();
            }

            double latestClose = validCloses.get(validCloses.size() - 1);
            double previousClose = validCloses.get(validCloses.size() - 2);
            double marketPrice = meta.optDouble("regularMarketPrice", latestClose);
            if (!Double.isFinite(marketPrice) || marketPrice <= 0) {
                marketPrice = latestClose;
            }
            return new MarketAnalysis(
                    ticker,
                    marketPrice,
                    ((latestClose - previousClose) / previousClose) * 100.0,
                    averageLast(validCloses, 20),
                    averageLast(validCloses, 50),
                    calculateRsi(validCloses, 14));
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static String readStream(InputStream stream) throws IOException {
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        return body.toString();
    }

    private static double averageLast(List<Double> values, int count) {
        double sum = 0;
        for (int i = values.size() - count; i < values.size(); i++) {
            sum += values.get(i);
        }
        return sum / count;
    }

    private static double calculateRsi(List<Double> closes, int period) {
        double gains = 0;
        double losses = 0;
        for (int i = closes.size() - period; i < closes.size(); i++) {
            double change = closes.get(i) - closes.get(i - 1);
            if (change > 0) {
                gains += change;
            } else {
                losses -= change;
            }
        }
        if (losses == 0) {
            return gains == 0 ? 50 : 100;
        }
        double relativeStrength = (gains / period) / (losses / period);
        return 100 - (100 / (1 + relativeStrength));
    }

    private void showAnalysis(MarketAnalysis analysis) {
        results.removeAllViews();
        LinearLayout summary = card();
        results.addView(summary);

        boolean priceAboveSma20 = analysis.price > analysis.sma20;
        boolean sma20AboveSma50 = analysis.sma20 > analysis.sma50;
        boolean rsiPositive = analysis.rsi >= 50 && analysis.rsi < 70;
        int positiveFactors = (priceAboveSma20 ? 1 : 0)
                + (sma20AboveSma50 ? 1 : 0)
                + (rsiPositive ? 1 : 0);
        String outlook = positiveFactors >= 3
                ? getString(R.string.trend_positive)
                : positiveFactors == 0
                        ? getString(R.string.trend_negative)
                        : getString(R.string.trend_mixed);
        int outlookColor = positiveFactors >= 3 ? GREEN : positiveFactors == 0 ? RED : ACCENT;

        summary.addView(text(analysis.ticker + " · " + getString(R.string.signal_title),
                17, MUTED, true));
        addGap(summary, 8);
        summary.addView(text(outlook, 22, outlookColor, true));
        addGap(summary, 16);
        addMetric(summary, getString(R.string.price_label),
                getString(R.string.format_price, analysis.price));
        addMetric(summary, getString(R.string.change_label),
                getString(R.string.format_percent, analysis.dailyChangePercent));
        addMetric(summary, getString(R.string.sma20_label),
                getString(R.string.format_indicator, analysis.sma20));
        addMetric(summary, getString(R.string.sma50_label),
                getString(R.string.format_indicator, analysis.sma50));
        addMetric(summary, getString(R.string.rsi_label),
                getString(R.string.format_rsi, analysis.rsi));

        LinearLayout factors = card();
        LinearLayout.LayoutParams factorParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        factorParams.topMargin = dp(14);
        results.addView(factors, factorParams);
        factors.addView(text(getString(R.string.factor_title), 17, TEXT, true));
        addGap(factors, 10);
        addFactor(factors, analysis.price > analysis.sma20
                ? R.string.factor_price_above : analysis.price < analysis.sma20
                        ? R.string.factor_price_below : R.string.factor_price_equal);
        addFactor(factors, sma20AboveSma50
                ? R.string.factor_sma_bullish : R.string.factor_sma_bearish);
        addFactor(factors, analysis.rsi >= 70
                ? R.string.factor_rsi_high : analysis.rsi <= 30
                        ? R.string.factor_rsi_low : rsiPositive
                                ? R.string.factor_rsi_positive : R.string.factor_rsi_neutral);
        addFactor(factors, analysis.dailyChangePercent > 0.1
                ? R.string.factor_daily_up : analysis.dailyChangePercent < -0.1
                        ? R.string.factor_daily_down : R.string.factor_daily_flat);

        TextView source = text(getString(R.string.source), 12, MUTED, false);
        LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        sourceParams.topMargin = dp(12);
        results.addView(source, sourceParams);
    }

    private void addMetric(LinearLayout parent, String label, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, dp(6), 0, dp(6));
        row.addView(text(label, 14, MUTED, false), new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        row.addView(text(value, 15, TEXT, true));
        parent.addView(row);
    }

    private void addFactor(LinearLayout parent, int messageId) {
        TextView factor = text("•  " + getString(messageId), 14, TEXT, false);
        factor.setPadding(0, dp(6), 0, dp(6));
        parent.addView(factor);
    }

    private void showMessage(String message, int color) {
        results.removeAllViews();
        TextView view = text(message, 15, color, false);
        view.setPadding(dp(16), dp(14), dp(16), dp(14));
        view.setBackgroundColor(CARD);
        results.addView(view);
    }

    private LinearLayout card() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(16), dp(16), dp(16), dp(16));
        layout.setBackgroundColor(CARD);
        return layout;
    }

    private TextView text(String value, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        if (bold) {
            view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        }
        return view;
    }

    private void addGap(LinearLayout parent, int heightDp) {
        View gap = new View(this);
        parent.addView(gap, new LinearLayout.LayoutParams(1, dp(heightDp)));
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class MarketAnalysis {
        final String ticker;
        final double price;
        final double dailyChangePercent;
        final double sma20;
        final double sma50;
        final double rsi;

        MarketAnalysis(String ticker, double price, double dailyChangePercent,
                       double sma20, double sma50, double rsi) {
            this.ticker = ticker;
            this.price = price;
            this.dailyChangePercent = dailyChangePercent;
            this.sma20 = sma20;
            this.sma50 = sma50;
            this.rsi = rsi;
        }
    }

    private static final class HttpStatusException extends IOException {
        final int statusCode;

        HttpStatusException(int statusCode) {
            this.statusCode = statusCode;
        }
    }

    private static final class InsufficientDataException extends IOException {
    }
}
