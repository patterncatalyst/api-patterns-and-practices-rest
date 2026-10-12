package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * Deterministic quote formula, identical on both stacks so the Quarkus and
 * Python responses are byte-for-byte comparable (see README.md):
 *
 *     quote.currency = "USD"
 *     quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")
 *
 * The amount is always rendered as a decimal STRING ("1250.00"), per
 * `#/$defs/Money` in the shared schema — never a JSON number.
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
