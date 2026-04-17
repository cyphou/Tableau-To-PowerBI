let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"restaurant_id", "restaurant_name", "cuisine_type", "city", "state", "avg_rating", "prep_time_min", "active", "month"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, "Sample 9"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7, 8, 9, "Sample 10"}
            }
        )
    otherwise
        #table({"restaurant_id", "restaurant_name", "cuisine_type", "city", "state", "avg_rating", "prep_time_min", "active", "month"}, {})  // Empty table on error
in
    Source