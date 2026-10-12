package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.Money;

import java.util.List;
import java.util.Locale;

/**
 * Deterministic quote formula, identical on both stacks (mirrors
 * examples/04-contract-first/quarkus/.../QuoteCalculator.java):
 *
 *     quote.currency = "USD"
 *     quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")
 *
 * `amount` is always rendered as a decimal STRING ("1250.00"), per
 * `#/$defs/Money` — never a JSON number.
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
        String amount = String.format(Locale.ROOT, "%.2f", totalWeightKg * RATE_PER_KG);
        return new Money("USD", amount);
    }
}
