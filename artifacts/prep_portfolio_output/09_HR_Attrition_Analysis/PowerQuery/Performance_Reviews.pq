let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"EmployeeID", "ReviewYear", "PerformanceRating", "ManagerRating", "GoalsAchieved", "PromotionRecommendation"},
            {
                {"Sample 1", 2, 3, 4, 5, "Sample 6"},
                {"Sample 2", 3, 4, 5, 6, "Sample 7"}
            }
        )
    otherwise
        #table({"EmployeeID", "ReviewYear", "PerformanceRating", "ManagerRating", "GoalsAchieved", "PromotionRecommendation"}, {})  // Empty table on error
in
    Source