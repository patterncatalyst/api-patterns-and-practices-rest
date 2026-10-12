package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * Deterministic quote formula, identical on both stacks (mirrors
 * examples/04-contract-first/quarkus/.../QuoteCalculator.java):
 *
 *     quote.currency = "USD"
 *     quote.amount   = round_half_up(sum(cargo[].dimensions.weightKg) * 2.50, 2)
 *
 * `amount` is always rendered as a decimal STRING ("1250.00"), per
 * `#/$defs/Money` — never a JSON number. Both stacks round HALF_UP
 * explicitly (BigDecimal.setScale here, Python's
 * Decimal(...).quantize(..., ROUND_HALF_UP) in app/quote.py) so they agree
 * on every input, not just ones that happen to land exactly on two decimal
 * places.
 */
public final class QuoteCalculator {

    private static final double RATE_PER_KG = 2.50;

    private QuoteCalculator() {
    }

    public static Money compute(List<Cargo> cargo) {
        double totalWeightKg = 0;
        for (Cargo item : cargo) {
            totalWeightKg += item.dimensions().weightKg();
        }
        String amount = BigDecimal.valueOf(totalWeightKg * RATE_PER_KG)
                .setScale(2, RoundingMode.HALF_UP)
                .toPlainString();
        return new Money("USD", amount);
    }
}
