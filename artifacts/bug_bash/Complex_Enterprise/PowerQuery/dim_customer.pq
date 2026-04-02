let
    // Source Snowflake: analytics.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("analytics.snowflakecomputing.com", "ANALYTICS_WH"),

            _nav = _src{[Name="ENTERPRISE_DW"]}[Data]

        in _nav

    otherwise

        #table({"customer_key", "customer_id", "customer_name", "email", "phone", "segment", "industry", "company_size", "first_order_date", "credit_limit", "account_manager", "is_active"}, {}),
    #"SALES" = Source{[Name="SALES"]}[Data],
    #"dim_customer Table" = #"SALES"{[Name="dim_customer"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"dim_customer Table", {{"customer_id", "Customer ID"}, {"customer_name", "Customer Name"}, {"email", "Email"}, {"phone", "Phone"}, {"segment", "Segment"}, {"industry", "Industry"}, {"company_size", "Company Size"}, {"first_order_date", "First Order"}, {"credit_limit", "Credit Limit"}, {"account_manager", "Account Manager"}, {"is_active", "Active?"}}),
    Result = #"Renamed Columns"
in
    Result