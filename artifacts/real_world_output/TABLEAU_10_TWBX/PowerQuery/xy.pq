let
    // Source SQL Server
    Source = try

        let

            _src = Sql.Database("mssql2012.test.tsi.lan", "TestV1"),

            _nav = _src{[Schema="dbo", Item="xy"]}[Data]

        in _nav

    otherwise

        #table({"a", "x", "y"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"a", "A"}, {"x", "X"}, {"y", "Y"}}),
    Result = #"Renamed Columns"
in
    Result