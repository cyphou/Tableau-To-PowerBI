let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"EmployeeID", "FirstName", "LastName", "Department", "JobRole", "HireDate", "TerminationDate", "MonthlyIncome", "EducationLevel", "Gender", "Age", "OverTime", "DistanceFromHome", "YearsAtCompany", "NumCompaniesWorked", "TrainingTimesLastYear"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, 9, "Sample 10", 11, "Sample 12", 13, 14, 15, 16},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7, 8, 9, 10, "Sample 11", 12, "Sample 13", 14, 15, 16, 17}
            }
        )
    otherwise
        #table({"EmployeeID", "FirstName", "LastName", "Department", "JobRole", "HireDate", "TerminationDate", "MonthlyIncome", "EducationLevel", "Gender", "Age", "OverTime", "DistanceFromHome", "YearsAtCompany", "NumCompaniesWorked", "TrainingTimesLastYear"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "EmployeeID", Performance_Reviews, "EmployeeID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"ReviewYear", "PerformanceRating", "ManagerRating", "GoalsAchieved", "PromotionRecommendation"}),
    #"Joined Joined 2" = Table.NestedJoin(#"Expanded Joined", "EmployeeID", Avg_Survey_by_Employee, "EmployeeID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined 2" = Table.ExpandTableColumn(#"Joined Joined 2", "Joined", {"Q1_Satisfaction", "Q2_WorkLifeBalance", "Q3_Environment", "Q4_Relationship", "Q5_JobInvolvement", "SurveyDate"}),
    #"Added IsTerminated" = Table.AddColumn(#"Expanded Joined 2", "IsTerminated", each if (null = [TerminationDate]) then 0 else 1 ),
    #"Added TenureBucket" = Table.AddColumn(#"Added IsTerminated", "TenureBucket", each if [YearsAtCompany] < 2 then 'New' else if [YearsAtCompany] < 5 then 'Mid' else if [YearsAtCompany] < 10 then 'Senior' else 'Veteran' ),
    #"Added AttritionRisk" = Table.AddColumn(#"Added TenureBucket", "AttritionRisk", each if [OverTime] = 'Yes' and [AvgSurveyScore] < 3 then 'High' else if [OverTime] = 'Yes' or [AvgSurveyScore] < 3 then 'Medium' else 'Low' ),
    #"Added IncomeBracket" = Table.AddColumn(#"Added AttritionRisk", "IncomeBracket", each if [MonthlyIncome] < 3000 then 'Low' else if [MonthlyIncome] < 7000 then 'Mid' else 'High' ),
    #"Renamed Columns" = Table.RenameColumns(#"Added IncomeBracket", {{"EducationLevel", "Education"}}),
    Result = #"Renamed Columns"
in
    Result