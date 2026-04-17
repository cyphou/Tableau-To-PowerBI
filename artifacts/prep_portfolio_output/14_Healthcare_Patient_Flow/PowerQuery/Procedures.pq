let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"procedure_id", "admission_id", "procedure_code", "procedure_name", "procedure_date", "duration_minutes", "cost", "performing_physician"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, 7, "Sample 8"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, "Sample 9"}
            }
        )
    otherwise
        #table({"procedure_id", "admission_id", "procedure_code", "procedure_name", "procedure_date", "duration_minutes", "cost", "performing_physician"}, {})  // Empty table on error
in
    Source