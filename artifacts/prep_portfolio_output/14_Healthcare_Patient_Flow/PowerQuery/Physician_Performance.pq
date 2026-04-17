let
    // TODO: Configure the data source for connector type: excel-direct
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"physician_id", "physician_name", "specialty", "department", "fte", "hire_date", "credential"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, "Sample 7"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, "Sample 8"}
            }
        )
    otherwise
        #table({"physician_id", "physician_name", "specialty", "department", "fte", "hire_date", "credential"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "attending_physician", RightTable, "physician_name", "Joined", JoinKind.LeftOuter),
    Result = #"Joined Joined"
in
    Result