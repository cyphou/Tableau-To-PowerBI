let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"order_id", "customer_id", "restaurant_id", "driver_id", "order_timestamp", "delivery_timestamp", "order_total", "delivery_fee", "tip_amount", "payment_method", "promo_code", "discount_amount", "status", "platform"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, 7, 8, 9, "Sample 10", "Sample 11", 12, "Sample 13", "Sample 14"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, 9, 10, "Sample 11", "Sample 12", 13, "Sample 14", "Sample 15"}
            }
        )
    otherwise
        #table({"order_id", "customer_id", "restaurant_id", "driver_id", "order_timestamp", "delivery_timestamp", "order_total", "delivery_fee", "tip_amount", "payment_method", "promo_code", "discount_amount", "status", "platform"}, {}),
    #"Filtered Rows" = Table.SelectRows(Source, each [status] = "Delivered" or [status] = "Completed"),
    #"Added DeliveryMinutes" = Table.AddColumn(#"Filtered Rows", "DeliveryMinutes", each DATEDIFF('minute', [order_timestamp], [delivery_timestamp])),
    #"Added NetRevenue" = Table.AddColumn(#"Added DeliveryMinutes", "NetRevenue", each [order_total] - [discount_amount] + [delivery_fee]),
    #"Added HasPromo" = Table.AddColumn(#"Added NetRevenue", "HasPromo", each if (null = [promo_code]) then 'No' else 'Yes' ),
    #"Renamed Columns" = Table.RenameColumns(#"Added HasPromo", {{"order_id", "OrderID"}, {"restaurant_id", "RestaurantID"}, {"customer_id", "CustomerID"}}),
    #"Removed Columns" = Table.RemoveColumns(#"Renamed Columns", {"status"}),
    #"Joined Joined" = Table.NestedJoin(#"Removed Columns", "RestaurantID", Deduplicate_Restaurants, "RestaurantID", "Joined", JoinKind.Inner),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"restaurant_id", "restaurant_name", "cuisine_type", "city", "state", "avg_rating", "prep_time_min", "active", "month"}),
    #"Added TotalWaitMinutes" = Table.AddColumn(#"Expanded Joined", "TotalWaitMinutes", each [prep_time_min] + [DeliveryMinutes]),
    #"Added SpeedTier" = Table.AddColumn(#"Added TotalWaitMinutes", "SpeedTier", each if [TotalWaitMinutes] <= 30 then 'Fast' else if [TotalWaitMinutes] <= 45 then 'Normal' else if [TotalWaitMinutes] <= 60 then 'Slow' else 'Very Slow' ),
    #"Added RevenuePerMinute" = Table.AddColumn(#"Added SpeedTier", "RevenuePerMinute", each [NetRevenue] / [TotalWaitMinutes]),
    Result = #"Added RevenuePerMinute"
in
    Result