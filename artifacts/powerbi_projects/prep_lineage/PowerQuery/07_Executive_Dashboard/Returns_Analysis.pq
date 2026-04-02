let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Region", "ReasonCode", "NetRefund", "ReturnRate", "anomaly_score"},
            {
                {"Sample 1", "Sample 2", 3, 4, 5},
                {"Sample 2", "Sample 3", 4, 5, 6}
            }
        )
    otherwise
        #table({"Region", "ReasonCode", "NetRefund", "ReturnRate", "anomaly_score"}, {})  // Empty table on error
in
    Source