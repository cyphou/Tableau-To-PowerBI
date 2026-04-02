let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"OrderID", "OrderDate", "CustomerID", "ProductID", "Region", "Sales", "Revenue"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", "Sample 5", 6, 7},
                {"Sample 2", 3, "Sample 4", "Sample 5", "Sample 6", 7, 8}
            }
        )
    otherwise
        #table({"OrderID", "OrderDate", "CustomerID", "ProductID", "Region", "Sales", "Revenue"}, {})  // Empty table on error
in
    Source