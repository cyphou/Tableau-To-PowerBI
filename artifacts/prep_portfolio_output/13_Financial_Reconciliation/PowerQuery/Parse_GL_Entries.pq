let
    // TODO: Configure the data source for connector type: excel-direct
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"JournalID", "PostingDate", "AccountCode", "Description", "DebitAmount", "CreditAmount", "CostCenter", "Currency", "Source", "ApprovedBy"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", 5, 6, "Sample 7", "Sample 8", "Sample 9", "Sample 10"},
                {"Sample 2", 3, "Sample 4", "Sample 5", 6, 7, "Sample 8", "Sample 9", "Sample 10", "Sample 11"}
            }
        )
    otherwise
        #table({"JournalID", "PostingDate", "AccountCode", "Description", "DebitAmount", "CreditAmount", "CostCenter", "Currency", "Source", "ApprovedBy"}, {}),
    #"Split AccountCode" = Table.SplitColumn(Source, "AccountCode", Splitter.SplitTextByDelimiter(",", QuoteStyle.None)),
    #"Added NetAmount" = Table.AddColumn(#"Split AccountCode", "NetAmount", each [DebitAmount] - [CreditAmount]),
    #"Added TransDirection" = Table.AddColumn(#"Added NetAmount", "TransDirection", each if [NetAmount] > 0 then 'Debit' else if [NetAmount] < 0 then 'Credit' else 'Zero' ),
    #"Trimmed Text" = Table.TransformColumns(#"Added TransDirection", {{"Description", Text.Trim}}),
    #"Uppercased" = Table.TransformColumns(#"Trimmed Text", {{"CostCenter", Text.Upper}}),
    #"Added PostingMonth" = Table.AddColumn(#"Uppercased", "PostingMonth", each STR(YEAR([PostingDate])) + '-' + Text.End('0' + STR(MONTH([PostingDate])), 2)),
    #"Added FiscalQuarter" = Table.AddColumn(#"Added PostingMonth", "FiscalQuarter", each if MONTH([PostingDate]) <= 3 then 'Q1' else if MONTH([PostingDate]) <= 6 then 'Q2' else if MONTH([PostingDate]) <= 9 then 'Q3' else 'Q4' ),
    Result = #"Added FiscalQuarter"
in
    Result