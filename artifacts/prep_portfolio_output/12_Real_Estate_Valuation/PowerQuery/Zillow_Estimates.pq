let
    // TODO: Configure the data source for connector type: json
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"zip_code", "zestimate_median", "rent_zestimate", "price_change_yoy_pct", "days_on_market_median", "month"},
            {
                {"Sample 1", 2, 3, 4, 5, "Sample 6"},
                {"Sample 2", 3, 4, 5, 6, "Sample 7"}
            }
        )
    otherwise
        #table({"zip_code", "zestimate_median", "rent_zestimate", "price_change_yoy_pct", "days_on_market_median", "month"}, {})  // Empty table on error
in
    Source