let
    // Source Excel: Sample - Superstore.xlsx
    Source = try

        let

            _src = Excel.Workbook(File.Contents(DataFolder & "\Sample - Superstore.xlsx"), null, true),

            _nav = _src{[Item="Returns",Kind="Sheet"]}[Data]

        in _nav

    otherwise

        #table({"Returned", "Order ID"}, {}),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Types" = Table.TransformColumnTypes(#"Promoted Headers", {
        {"Returned", type text},
        {"Order ID", type text}
    }),
    Result = #"Changed Types"
in
    Result