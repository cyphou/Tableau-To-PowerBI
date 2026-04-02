let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"customer_id", "age_group", "income_bracket", "city", "state", "country", "postal_code"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7", "Sample 8"}
            }
        )
    otherwise
        #table({"customer_id", "age_group", "income_bracket", "city", "state", "country", "postal_code"}, {})  // Empty table on error
in
    Source