let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"StatementID", "TransactionDate", "Reference", "PayeePayer", "Amount", "Balance", "BankAccount", "TransactionType", "CheckNumber"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", 5, 6, "Sample 7", "Sample 8", "Sample 9"},
                {"Sample 2", 3, "Sample 4", "Sample 5", 6, 7, "Sample 8", "Sample 9", "Sample 10"}
            }
        )
    otherwise
        #table({"StatementID", "TransactionDate", "Reference", "PayeePayer", "Amount", "Balance", "BankAccount", "TransactionType", "CheckNumber"}, {}),
    #"Split Reference" = Table.SplitColumn(Source, "Reference", Splitter.SplitTextByDelimiter(",", QuoteStyle.None)),
    #"Trimmed Text" = Table.TransformColumns(#"Split Reference", {{"PayeePayer", Text.Trim}}),
    #"Replaced Nulls in CheckNumber" = Table.ReplaceValue(#"Trimmed Text", null, "N/A", Replacer.ReplaceValue, {"CheckNumber"}),
    #"Added AbsAmount" = Table.AddColumn(#"Replaced Nulls in CheckNumber", "AbsAmount", each ABS([Amount])),
    #"Added BankDirection" = Table.AddColumn(#"Added AbsAmount", "BankDirection", each if [Amount] > 0 then 'Inflow' else 'Outflow' ),
    #"Joined Joined" = Table.NestedJoin(#"Added BankDirection", {"PostingDate", "NetAmount"}, GL_+_Chart_of_Accounts, {"TransactionDate", "Amount"}, "Joined", JoinKind.FullOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"AccountCode", "AccountName", "AccountType", "ParentAccount", "IsActive"}),
    #"Added MatchStatus" = Table.AddColumn(#"Expanded Joined", "MatchStatus", each if not (null = [JournalID]) and not (null = [StatementID]) then 'Matched' else if not (null = [JournalID]) then 'GL Only' else 'Bank Only' ),
    #"Added Variance" = Table.AddColumn(#"Added MatchStatus", "Variance", each if not (null = [NetAmount]) and not (null = [Amount]) then ABS([NetAmount] - [Amount]) else 0 ),
    #"Added NeedsReview" = Table.AddColumn(#"Added Variance", "NeedsReview", each if [MatchStatus] <> 'Matched' or [Variance] > 0.01 then 'Yes' else 'No' ),
    Result = #"Added NeedsReview"
in
    Result