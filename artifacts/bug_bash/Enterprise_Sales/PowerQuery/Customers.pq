let
    // Source Snowflake: acme.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("acme.snowflakecomputing.com", "COMPUTE_WH"),

            _nav = _src{[Name="ANALYTICS"]}[Data]

        in _nav

    otherwise

        #table({"customer_id", "customer_name", "segment", "city", "state", "country", "postal_code", "latitude", "longitude", "customer_email", "first_purchase_date"}, {}),
    #"PUBLIC" = Source{[Name="PUBLIC"]}[Data],
    #"Customers Table" = #"PUBLIC"{[Name="Customers"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"Customers Table", {{"customer_id", "Customer ID"}, {"customer_name", "Customer Name"}, {"segment", "Segment"}, {"city", "City"}, {"state", "State"}, {"country", "Country"}, {"postal_code", "Postal Code"}, {"latitude", "Latitude"}, {"longitude", "Longitude"}, {"customer_email", "Customer Email"}, {"first_purchase_date", "First Purchase Date"}}),
    Result = #"Renamed Columns"
in
    Result