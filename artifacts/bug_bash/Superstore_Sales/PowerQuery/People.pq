let
    // Source Excel: Sample - Superstore.xlsx
    Source = try

        let

            _src = Excel.Workbook(File.Contents(DataFolder & "\Sample - Superstore.xlsx"), null, true),

            _nav = _src{[Item="People",Kind="Sheet"]}[Data]

        in _nav

    otherwise

        #table({"Regional Manager", "Region"}, {}),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Types" = Table.TransformColumnTypes(#"Promoted Headers", {
        {"Regional Manager", type text},
        {"Region", type text}
    }),
    Result = #"Changed Types"
in
    Result