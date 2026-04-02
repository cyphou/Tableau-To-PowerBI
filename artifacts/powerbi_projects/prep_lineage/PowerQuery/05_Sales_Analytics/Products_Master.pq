let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"ProductID", "ProductName", "Category", "SubCategory", "UnitCost", "UnitPrice", "Margin"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, 7},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8}
            }
        )
    otherwise
        #table({"ProductID", "ProductName", "Category", "SubCategory", "UnitCost", "UnitPrice", "Margin"}, {})  // Empty table on error
in
    Source