let
    // Source SQL Server
    Source = try

        let

            _src = Sql.Database("localhost", "SalesDB"),

            _nav = _src{[Schema="dbo", Item="Orders"]}[Data]

        in _nav

    otherwise

        #table({"OrderID", "Region", "Sales", "Profit", "CustomerEmail", "Category", "OrderDate"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"OrderID", "Order ID"}, {"CustomerEmail", "Customer Email"}, {"OrderDate", "Order Date"}}),
    Result = #"Renamed Columns"
in
    Result