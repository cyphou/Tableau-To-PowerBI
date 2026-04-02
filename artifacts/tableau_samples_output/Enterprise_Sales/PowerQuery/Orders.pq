let
    // Source Snowflake: acme.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("acme.snowflakecomputing.com", "COMPUTE_WH"),

            _nav = _src{[Name="ANALYTICS"]}[Data]

        in _nav

    otherwise

        #table({"order_id", "order_date", "customer_id", "product_id", "region", "channel", "quantity", "unit_price", "discount", "shipping_cost", "order_status", "sales_rep", "territory"}, {}),
    #"PUBLIC" = Source{[Name="PUBLIC"]}[Data],
    #"Orders Table" = #"PUBLIC"{[Name="Orders"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"Orders Table", {{"order_id", "Order ID"}, {"order_date", "Order Date"}, {"customer_id", "Customer ID"}, {"product_id", "Product ID"}, {"region", "Region"}, {"channel", "Channel"}, {"quantity", "Quantity"}, {"unit_price", "Unit Price"}, {"discount", "Discount"}, {"shipping_cost", "Shipping Cost"}, {"order_status", "Order Status"}, {"sales_rep", "Sales Rep"}, {"territory", "Territory"}}),
    #"Added Safe Discount Rate" = Table.AddColumn(#"Renamed Columns", "Safe Discount Rate", each if ([discount] = null) then 0 else if ([discount] = null) then 0 else [discount], type number),
    #"Added Discount Category" = Table.AddColumn(#"Added Safe Discount Rate", "Discount Category", each if ([discount] = null) then "No Discount" else if [discount] = 0 then "No Discount" else if [discount] < 0.1 then "Low (<10%)" else if [discount] < 0.25 then "Medium (10-25%)" else "High (>25%)", type text),
    Result = #"Added Discount Category"
in
    Result