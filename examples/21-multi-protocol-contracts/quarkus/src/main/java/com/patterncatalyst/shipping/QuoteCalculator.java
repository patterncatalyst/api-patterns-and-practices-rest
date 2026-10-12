package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.Money;

import java.util.List;
import java.util.Locale;

/**
 * Deterministic quote formula, identical to examples/04-contract-first and
 * mirrored bit-for-bit on the Python side:
 *
 *     quote.currency = "USD"
 *     quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")
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
