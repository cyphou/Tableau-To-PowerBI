let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Customer_ID", "Customer_Name", "Segment", "City", "State", "Country"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7"}
            }
        )
    otherwise
        #table({"Customer_ID", "Customer_Name", "Segment", "City", "State", "Country"}, {})  // Empty table on error
in
    Source