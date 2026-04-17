let
    // TODO: Configure the data source for connector type: excel-direct
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"EmployeeID", "Q1_Satisfaction", "Q2_WorkLifeBalance", "Q3_Environment", "Q4_Relationship", "Q5_JobInvolvement", "SurveyDate"},
            {
                {"Sample 1", 2, 3, 4, 5, 6, 7},
                {"Sample 2", 3, 4, 5, 6, 7, 8}
            }
        )
    otherwise
        #table({"EmployeeID", "Q1_Satisfaction", "Q2_WorkLifeBalance", "Q3_Environment", "Q4_Relationship", "Q5_JobInvolvement", "SurveyDate"}, {})  // Empty table on error
in
    Source