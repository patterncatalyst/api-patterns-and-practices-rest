package com.patterncatalyst.shipping;

import io.quarkus.test.junit.QuarkusTest;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.matchesPattern;
import static org.hamcrest.Matchers.notNullValue;

/**
 * Item 2 of the Ch24 test pyramid: a real, in-process @QuarkusTest
 * integration test against the booking create/read surface. This boots the
 * full Quarkus application (CDI, JAX-RS, Jackson) in the same JVM as the
 * test — it is NOT a live-container HTTP call like verify.sh's contract
 * checks or the Newman collection.
 *
 * Run locally with:
 *
 *   cd examples/24-testing/quarkus
 *   mvn test
 *
 * NOT invoked by verify.sh — see README.md "What runs where" for why
 * (a Maven/JVM boot per CI matrix leg is too heavy/slow for the bounded,
 * deterministic CI path this chapter's verify.sh is scoped to).
 */
@QuarkusTest
class BookingResourceTest {

    private static final String VALID_BOOKING = """
            {
              "origin": {"unLocode": "USNYC", "name": "New York", "country": "US"},
              "destination": {"unLocode": "NLRTM", "name": "Rotterdam", "country": "NL"},
              "cargo": [
                {"description": "Palletized electronics", "type": "GENERAL",
                 "dimensions": {"weightKg": 1200.5, "volumeM3": 4.2}, "hazardous": false}
              ],
              "requestedPickup": "2026-02-01"
            }
            """;

    @Test
    void createBooking_returns201WithLocationAndBookingBody() {
        given()
                .contentType("application/json")
                .body(VALID_BOOKING)
                .when().post("/bookings")
                .then()
                .statusCode(201)
                .header("Location", matchesPattern("^/bookings/bkg_[0-9A-HJKMNP-TV-Z]{26}$"))
                .body("id", matchesPattern("^bkg_[0-9A-HJKMNP-TV-Z]{26}$"))
                .body("status", equalTo("PENDING"))
                .body("quote.currency", equalTo("USD"))
                .body("quote.amount", equalTo("3001.25"));
    }

    @Test
    void getBooking_afterCreate_returns200WithSameBooking() {
        String id = given()
                .contentType("application/json")
                .body(VALID_BOOKING)
                .when().post("/bookings")
                .then().statusCode(201)
                .extract().path("id");

        given()
                .when().get("/bookings/{id}", id)
                .then()
                .statusCode(200)
                .body("id", equalTo(id))
                .body("origin.unLocode", equalTo("USNYC"))
                .body("cargo.size()", greaterThan(0))
                .body("createdAt", notNullValue());
    }

    @Test
    void getBooking_nonexistent_returns404ProblemBody() {
        given()
                .when().get("/bookings/{id}", "bkg_00000000000000000000000000")
                .then()
                .statusCode(404)
                .contentType("application/problem+json")
                .body("title", equalTo("Booking not found"))
                .body("status", equalTo(404));
    }

    @Test
    void createBooking_missingCargo_returns400ProblemBody() {
        String invalid = """
                {
                  "origin": {"unLocode": "USNYC"},
                  "destination": {"unLocode": "NLRTM"}
                }
                """;

        given()
                .contentType("application/json")
                .body(invalid)
                .when().post("/bookings")
                .then()
                .statusCode(400)
                .contentType("application/problem+json")
                .body("status", equalTo(400));
    }
}
