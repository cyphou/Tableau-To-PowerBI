let
    // Source Snowflake: analytics.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("analytics.snowflakecomputing.com", "ANALYTICS_WH"),

            _nav = _src{[Name="ENTERPRISE_DW"]}[Data]

        in _nav

    otherwise

        #table({"sale_id", "date_key", "customer_key", "product_key", "store_key", "channel", "region", "territory", "country", "state", "city", "postal_code", "latitude", "longitude", "quantity", "unit_price", "unit_cost", "discount_pct", "tax_rate", "shipping_cost", "currency_code", "order_status", "payment_method", "sales_rep", "promotion_code", "is_returned"}, {}),
    #"SALES" = Source{[Name="SALES"]}[Data],
    #"fact_sales Table" = #"SALES"{[Name="fact_sales"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"fact_sales Table", {{"sale_id", "Sale ID"}, {"channel", "Channel"}, {"region", "Region"}, {"territory", "Territory"}, {"country", "Country"}, {"state", "State"}, {"city", "City"}, {"postal_code", "Postal Code"}, {"latitude", "Latitude"}, {"longitude", "Longitude"}, {"quantity", "Quantity"}, {"unit_price", "Unit Price"}, {"unit_cost", "Unit Cost"}, {"discount_pct", "Discount %"}, {"tax_rate", "Tax Rate"}, {"shipping_cost", "Shipping Cost"}, {"currency_code", "Currency"}, {"order_status", "Order Status"}, {"payment_method", "Payment Method"}, {"sales_rep", "Sales Rep"}, {"promotion_code", "Promotion Code"}, {"is_returned", "Returned?"}}),
    #"Added Safe Discount" = Table.AddColumn(#"Renamed Columns", "Safe Discount", each if ([discount_pct] = null) then 0 else [discount_pct], type number),
    Result = #"Added Safe Discount"
in
    Result