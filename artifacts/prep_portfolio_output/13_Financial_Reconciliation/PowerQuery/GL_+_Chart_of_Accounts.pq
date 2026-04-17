let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"AccountCode", "AccountName", "AccountType", "ParentAccount", "IsActive"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6}
            }
        )
    otherwise
        #table({"AccountCode", "AccountName", "AccountType", "ParentAccount", "IsActive"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "AccountCode", Parse_GL_Entries, "AccountCode", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"JournalID", "PostingDate", "Description", "DebitAmount", "CreditAmount", "CostCenter", "Currency", "Source", "ApprovedBy"}),
    Result = #"Expanded Joined"
in
    Result