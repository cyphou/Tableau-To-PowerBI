let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"customer_id", "first_name", "last_name", "email", "phone", "created_at", "segment", "loyalty_tier", "lifetime_value"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, "Sample 7", "Sample 8", 9},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7, "Sample 8", "Sample 9", 10}
            }
        )
    otherwise
        #table({"customer_id", "first_name", "last_name", "email", "phone", "created_at", "segment", "loyalty_tier", "lifetime_value"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "customer_id", Demographics, "customer_id", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"age_group", "income_bracket", "city", "state", "country", "postal_code"}),
    #"Renamed Columns" = Table.RenameColumns(#"Expanded Joined", {{"customer_id", "CustomerID"}}),
    #"Lowercased" = Table.TransformColumns(#"Renamed Columns", {{"email", Text.Lower}}),
    #"Replaced Nulls in loyalty_tier" = Table.ReplaceValue(#"Lowercased", null, "Bronze", Replacer.ReplaceValue, {"loyalty_tier"}),
    #"Added FullAddress" = Table.AddColumn(#"Replaced Nulls in loyalty_tier", "FullAddress", each [city] + ", " + [state] + " " + [postal_code]),
    Result = #"Added FullAddress"
in
    Result