let
    // TODO: Configure the data source for connector type: DATAENGINE
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Category", "Number of Records", "Order Date", "Sales Target", "Segment"},
            {
                {"Sample 1", 2, 3, 4, "Sample 5"},
                {"Sample 2", 3, 4, 5, "Sample 6"}
            }
        )
    otherwise
        #table({"Category", "Number of Records", "Order Date", "Sales Target", "Segment"}, {})  // Empty table on error
in
    Source