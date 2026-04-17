let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"transaction_id", "listing_id", "sale_price", "sale_date", "buyer_id", "financing_type", "closing_costs", "commission_pct"},
            {
                {"Sample 1", "Sample 2", 3, 4, "Sample 5", "Sample 6", 7, 8},
                {"Sample 2", "Sample 3", 4, 5, "Sample 6", "Sample 7", 8, 9}
            }
        )
    otherwise
        #table({"transaction_id", "listing_id", "sale_price", "sale_date", "buyer_id", "financing_type", "closing_costs", "commission_pct"}, {})  // Empty table on error
in
    Source